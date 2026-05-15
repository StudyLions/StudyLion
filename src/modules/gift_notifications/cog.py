# ============================================================
# AI-GENERATED FILE
# Created: 2026-05-15
# Purpose: Polls pending_notifications written by the LionBot
#          website's gift webhook handlers and delivers Discord
#          DMs. Two kinds:
#            user_dm        -- DM one Discord user by target_userid
#            guild_admin_dm -- DM every administrator of target_guildid
#                              (resolved from the bot's live member /
#                              permission cache, so users.email isn't
#                              needed on the website side)
#
#          Shard 0 only -- the queue is global so we need exactly one
#          poller. Other shards no-op.
#
#          Each row carries a JSONB `payload` with title / body /
#          link_url / link_label. The cog formats a Discord embed with
#          a single link button (via a discord.ui.View). The embed
#          uses gold accent color to match the website's gift surfaces.
#
#          Retry / failure model:
#            - On unknown error, increment attempts + record last_error.
#            - Rows are skipped once attempts >= MAX_ATTEMPTS so a
#              broken row doesn't loop forever.
#            - On Forbidden (user has DMs closed), we mark FAILED
#              immediately -- retrying won't help.
# ============================================================
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any, Optional

import discord
from discord.ext import tasks

from meta import LionCog, LionBot
from meta.logger import log_wrap
from utils.lib import utc_now

from . import logger

# ------------------------------------------------------------
# Tuning knobs
# ------------------------------------------------------------

POLL_INTERVAL_SECONDS = 10  # how often to scan the queue
BATCH_SIZE = 25             # rows per scan -- bounded so the loop is quick
MAX_ATTEMPTS = 5            # after this many failures, leave the row alone

# Gold accent matching the website's gift surfaces (PremiumGate, claim page).
EMBED_COLOR = discord.Color.from_rgb(245, 158, 11)

WEBSITE_BASE_URL = "https://lionbot.org"  # link_url is sometimes a relative
                                          # path; we normalise to absolute.


class GiftNotificationsCog(LionCog):
    """Pollers + senders for cross-system gift notifications."""

    def __init__(self, bot: LionBot):
        self.bot = bot
        self._processing = False

    async def cog_load(self):
        # Single global poller -- shard 0 only.
        if self.bot.shard_id != 0:
            logger.debug(
                f"Gift notifications poller skipped on shard {self.bot.shard_id}."
            )
            return
        logger.info("Gift notifications poller starting on shard 0.")
        self._poll.start()

    async def cog_unload(self):
        if self._poll.is_running():
            self._poll.cancel()

    # ── Poll loop ──────────────────────────────────────────

    @tasks.loop(seconds=POLL_INTERVAL_SECONDS)
    async def _poll(self):
        # Defensive: if a previous tick is still processing (e.g. Discord
        # API rate-limited us), don't queue up overlapping work.
        if self._processing:
            return
        self._processing = True
        try:
            await self._tick()
        except Exception:
            logger.exception("Gift notifications: unhandled error in poll tick")
        finally:
            self._processing = False

    @_poll.before_loop
    async def _before_poll(self):
        await self.bot.wait_until_ready()

    @log_wrap(action="GiftNotifications Tick")
    async def _tick(self):
        rows = await self._fetch_pending(BATCH_SIZE)
        if not rows:
            return
        for row in rows:
            try:
                await self._process_row(row)
            except Exception:
                # _process_row owns its retry bookkeeping; if it raises out
                # to here, it's a programmer bug -- log it but keep the loop
                # alive for the rest of the batch.
                logger.exception(
                    f"Gift notifications: failed to process row id={row['id']}"
                )

    # ── DB helpers (raw SQL; same pattern as serverlisting/data.py) ──

    async def _fetch_pending(self, limit: int) -> list[dict[str, Any]]:
        async with self.bot.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, kind, target_userid, target_guildid, dedup_key, payload,
                       attempts
                FROM pending_notifications
                WHERE status = 'PENDING' AND attempts < %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                [MAX_ATTEMPTS, limit],
            )
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def _mark_sent(self, row_id: int) -> None:
        async with self.bot.db.connection() as conn:
            await conn.execute(
                """
                UPDATE pending_notifications
                SET status = 'SENT',
                    sent_at = NOW(),
                    last_attempted_at = NOW()
                WHERE id = %s
                """,
                [row_id],
            )

    async def _mark_failed(self, row_id: int, error: str) -> None:
        async with self.bot.db.connection() as conn:
            await conn.execute(
                """
                UPDATE pending_notifications
                SET status = 'FAILED',
                    last_attempted_at = NOW(),
                    last_error = %s
                WHERE id = %s
                """,
                [error[:500], row_id],
            )

    async def _bump_attempt(self, row_id: int, error: Optional[str]) -> None:
        async with self.bot.db.connection() as conn:
            await conn.execute(
                """
                UPDATE pending_notifications
                SET attempts = attempts + 1,
                    last_attempted_at = NOW(),
                    last_error = %s
                WHERE id = %s
                """,
                [(error or "")[:500], row_id],
            )

    # ── Per-row dispatch ───────────────────────────────────

    async def _process_row(self, row: dict[str, Any]) -> None:
        kind = row["kind"]
        payload = row["payload"] or {}
        # psycopg returns JSONB as a parsed dict already; defensive parse if
        # it came through as a string.
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                await self._mark_failed(row["id"], "Invalid JSON payload")
                return

        if kind == "user_dm":
            await self._dispatch_user_dm(row, payload)
        elif kind == "guild_admin_dm":
            await self._dispatch_guild_admin_dm(row, payload)
        else:
            await self._mark_failed(row["id"], f"Unknown kind: {kind}")

    async def _dispatch_user_dm(
        self, row: dict[str, Any], payload: dict[str, Any]
    ) -> None:
        userid = row["target_userid"]
        if not userid:
            await self._mark_failed(row["id"], "user_dm missing target_userid")
            return

        ok, err = await self._send_dm(int(userid), payload)
        if ok:
            await self._mark_sent(row["id"])
        elif err == "FORBIDDEN":
            # User has DMs closed -- retry won't help. Mark FAILED so the
            # row isn't re-tried 5 times pointlessly.
            await self._mark_failed(row["id"], "User has DMs closed")
        else:
            await self._bump_attempt(row["id"], err)

    async def _dispatch_guild_admin_dm(
        self, row: dict[str, Any], payload: dict[str, Any]
    ) -> None:
        guildid = row["target_guildid"]
        if not guildid:
            await self._mark_failed(row["id"], "guild_admin_dm missing target_guildid")
            return

        guild = self.bot.get_guild(int(guildid))
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(int(guildid))
            except discord.HTTPException:
                guild = None
        if guild is None:
            await self._mark_failed(row["id"], "Bot not in guild")
            return

        # The bot starts with chunk_guilds_at_startup=False, so members may
        # not be loaded yet for this guild. Force a chunk so we can iterate
        # permissions reliably. Members intent is on, so this works.
        if not guild.chunked:
            try:
                await guild.chunk(cache=True)
            except (discord.HTTPException, asyncio.TimeoutError) as exc:
                logger.warning(
                    f"Gift notifications: guild.chunk failed for {guildid}: {exc}"
                )
                # Fall through -- we may still get the owner and any cached admins.

        # Resolve admins from the live cache. We DM the guild owner +
        # every member with administrator permission. Bot accounts are
        # excluded so we don't DM ourselves.
        admin_ids: set[int] = set()
        if guild.owner_id:
            admin_ids.add(guild.owner_id)
        for member in guild.members:
            if member.bot:
                continue
            if member.guild_permissions.administrator:
                admin_ids.add(member.id)

        if not admin_ids:
            # Likely the bot hasn't chunked this guild yet. Bump attempts so
            # we'll retry on the next tick; chunking happens async at startup.
            await self._bump_attempt(row["id"], "No admins resolved yet")
            return

        # Send sequentially with brief spacing so we don't immediately hit
        # Discord's per-shard DM rate-limit on bigger admin groups.
        successes = 0
        last_err: Optional[str] = None
        for uid in admin_ids:
            ok, err = await self._send_dm(uid, payload)
            if ok:
                successes += 1
            else:
                last_err = err
            await asyncio.sleep(0.4)

        if successes == 0:
            # Treat "everyone has DMs closed" as a soft FAILED -- nothing we
            # can do; the dashboard banner will still surface the gift.
            await self._mark_failed(
                row["id"], f"No admins reachable; last error: {last_err}"
            )
        else:
            await self._mark_sent(row["id"])

    # ── Discord send helper ───────────────────────────────

    async def _send_dm(
        self, userid: int, payload: dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Send the formatted embed DM. Returns (ok, error_token)."""
        try:
            user = self.bot.get_user(userid) or await self.bot.fetch_user(userid)
        except discord.NotFound:
            return False, "USER_NOT_FOUND"
        except discord.HTTPException as exc:
            return False, f"FETCH_USER_HTTP:{exc.status}"

        embed = self._build_embed(payload)
        view = self._build_view(payload)

        try:
            await user.send(embed=embed, view=view)
            return True, None
        except discord.Forbidden:
            return False, "FORBIDDEN"
        except discord.HTTPException as exc:
            return False, f"SEND_HTTP:{exc.status}"

    def _build_embed(self, payload: dict[str, Any]) -> discord.Embed:
        title = (payload.get("title") or "LionBot").strip()[:256]
        body = (payload.get("body") or "").strip()[:4000]
        embed = discord.Embed(
            title=title,
            description=body if body else discord.Embed.Empty,
            color=EMBED_COLOR,
        )
        # No author / footer noise -- restraint per the gift UI principles.
        return embed

    def _build_view(self, payload: dict[str, Any]) -> Optional[discord.ui.View]:
        url = payload.get("link_url")
        if not url:
            return None
        if url.startswith("/"):
            url = WEBSITE_BASE_URL.rstrip("/") + url
        label = (payload.get("link_label") or "Open").strip()[:80]
        view = discord.ui.View(timeout=None)
        try:
            view.add_item(discord.ui.Button(label=label, url=url))
        except (discord.InvalidArgument, ValueError):
            return None
        return view

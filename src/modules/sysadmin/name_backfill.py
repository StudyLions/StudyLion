# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-17
# Purpose: /leo backfill_names admin command -- one-time backfill
#          of NULL members.display_name and user_config.name /
#          avatar_hash from the bot's gateway member cache.
#          Idempotent (COALESCE-WHERE-NULL semantics) so it's safe
#          to re-run.  Pairs with the name_sync module which keeps
#          things fresh going forward.
# ============================================================
import asyncio
import logging
from itertools import chain
from typing import Optional

import discord
from discord import app_commands as appcmds
from discord.ext import commands as cmds
from psycopg import sql

from meta import LionBot, LionCog, LionContext
from meta.logger import log_wrap
from wards import sys_admin_ward

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def _avatar_key(user) -> Optional[str]:
    avatar = getattr(user, 'avatar', None)
    return avatar.key if avatar else None


class NameBackfill(LionCog):
    """
    Sysadmin-only cog providing `/leo backfill_names` to fill in NULL
    `members.display_name` / `user_config.name` / `user_config.avatar_hash`
    rows from the bot's in-memory gateway cache. No new rows are inserted;
    only existing rows that are missing data are touched, and only NULL
    columns are written (COALESCE), so this is idempotent and safe to
    re-run after a partial failure.

    Sharding: each shard sees only its own guilds, so this command needs
    to be run once per shard to cover the whole bot.
    """

    def __init__(self, bot: LionBot):
        self.bot = bot
        self._running = False

    async def cog_load(self):
        leo_setting_cog = self.bot.get_cog('LeoSettings')
        if leo_setting_cog is None:
            logger.warning(
                "LeoSettings not loaded; /leo backfill_names will not be crossloaded."
            )
            return
        self.crossload_group(self.leo_group, leo_setting_cog.leo_group)

    @LionCog.placeholder_group
    @cmds.hybrid_group('leo', with_app_command=False)
    async def leo_group(self, ctx: LionContext):
        ...

    @leo_group.command(
        name='backfill_names',
        description=(
            "Backfill NULL display_name / username / avatar from gateway cache. "
            "Runs only on this shard."
        ),
    )
    @appcmds.describe(
        guild_id="Optional: limit to one guild (must be on this shard).",
        dry_run="If true, just count how many rows WOULD be filled.",
    )
    @sys_admin_ward
    async def backfill_names_cmd(
        self,
        ctx: LionContext,
        guild_id: Optional[str] = None,
        dry_run: bool = False,
    ):
        if self._running:
            await ctx.reply(
                "Backfill already running on this shard; refusing to start a second one.",
                ephemeral=True,
            )
            return

        target_guild_id: Optional[int] = None
        if guild_id:
            try:
                target_guild_id = int(guild_id)
            except ValueError:
                await ctx.reply(
                    f"`{guild_id}` is not a valid guild ID.", ephemeral=True
                )
                return
            if self.bot.get_guild(target_guild_id) is None:
                await ctx.reply(
                    f"Guild `{target_guild_id}` is not on this shard "
                    f"(shard_id={self.bot.shard_id}).",
                    ephemeral=True,
                )
                return

        self._running = True
        try:
            await ctx.defer(ephemeral=True)
            await self._run_backfill(ctx, target_guild_id, dry_run)
        finally:
            self._running = False

    @log_wrap(action="NameBackfill")
    async def _run_backfill(
        self,
        ctx: LionContext,
        target_guild_id: Optional[int],
        dry_run: bool,
    ):
        guilds = (
            [self.bot.get_guild(target_guild_id)]
            if target_guild_id is not None
            else list(self.bot.guilds)
        )
        guilds = [g for g in guilds if g is not None]
        total_guilds = len(guilds)

        shard_id = self.bot.shard_id if self.bot.shard_id is not None else 0
        mode_label = "DRY RUN" if dry_run else "LIVE"
        scope_label = (
            f"guild {target_guild_id}" if target_guild_id is not None
            else f"all {total_guilds} guilds on shard {shard_id}"
        )
        logger.info(
            f"NameBackfill starting ({mode_label}) over {scope_label}."
        )

        async def update_report(msg: str):
            try:
                await ctx.interaction.edit_original_response(content=msg)
            except discord.HTTPException:
                pass

        await update_report(
            f"Backfill started ({mode_label}) over {scope_label}. Working..."
        )

        seen_userids: set[int] = set()
        totals = {
            'guilds_processed': 0,
            'members_eligible': 0,
            'members_updated': 0,
            'users_eligible': 0,
            'users_updated': 0,
            'cache_misses': 0,
        }

        last_report = 0
        for idx, guild in enumerate(guilds, start=1):
            try:
                stats = await self._backfill_one_guild(
                    guild, seen_userids, dry_run
                )
            except Exception:
                logger.exception(
                    f"NameBackfill failed inside guild <gid:{guild.id}>; continuing."
                )
                continue

            totals['guilds_processed'] += 1
            totals['members_eligible'] += stats['members_eligible']
            totals['members_updated'] += stats['members_updated']
            totals['users_eligible'] += stats['users_eligible']
            totals['users_updated'] += stats['users_updated']
            totals['cache_misses'] += stats['cache_misses']

            await asyncio.sleep(0)

            now = asyncio.get_running_loop().time()
            if now - last_report > 5.0 or idx == total_guilds:
                last_report = now
                await update_report(
                    self._format_progress(mode_label, idx, total_guilds, totals)
                )

        final = self._format_progress(
            mode_label, totals['guilds_processed'], total_guilds, totals,
            done=True,
        )
        logger.info(
            f"NameBackfill finished ({mode_label}). "
            f"guilds={totals['guilds_processed']}/{total_guilds} "
            f"members_updated={totals['members_updated']} "
            f"users_updated={totals['users_updated']} "
            f"cache_misses={totals['cache_misses']}"
        )
        await update_report(final)

    @staticmethod
    def _format_progress(mode, processed, total, t, done=False):
        prefix = "Backfill complete" if done else "Backfill running"
        return (
            f"**{prefix}** ({mode})\n"
            f"Guilds: `{processed}/{total}`\n"
            f"`members.display_name`  eligible=`{t['members_eligible']}`  updated=`{t['members_updated']}`\n"
            f"`user_config` rows      eligible=`{t['users_eligible']}`  updated=`{t['users_updated']}`\n"
            f"Gateway cache misses (member left guild before we got here): `{t['cache_misses']}`"
        )

    async def _backfill_one_guild(
        self,
        guild: discord.Guild,
        seen_userids: set[int],
        dry_run: bool,
    ) -> dict:
        """
        Fill in NULL display_name rows for `guild`, and any NULL user_config
        rows for those same users (skipping users already touched on this run).
        """
        async with self.bot.db.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT userid FROM members "
                "WHERE guildid = %s AND display_name IS NULL AND last_left IS NULL",
                (guild.id,),
            )
            rows = await cur.fetchall()
        candidate_userids = [row['userid'] for row in rows]

        if not candidate_userids:
            return {
                'members_eligible': 0,
                'members_updated': 0,
                'users_eligible': 0,
                'users_updated': 0,
                'cache_misses': 0,
            }

        member_rows: list[tuple[int, int, str]] = []
        user_rows: list[tuple[int, str, Optional[str]]] = []
        cache_misses = 0

        for uid in candidate_userids:
            member = guild.get_member(uid)
            if member is None:
                cache_misses += 1
                continue

            display = member.display_name
            if display:
                member_rows.append((guild.id, uid, display))

            if uid not in seen_userids:
                seen_userids.add(uid)
                user_rows.append((uid, member.name, _avatar_key(member)))

        members_updated = 0
        users_updated = 0
        if not dry_run:
            for batch in _chunked(member_rows, BATCH_SIZE):
                members_updated += await self._bulk_update_members(batch)
                await asyncio.sleep(0)
            for batch in _chunked(user_rows, BATCH_SIZE):
                users_updated += await self._bulk_update_user_config(batch)
                await asyncio.sleep(0)

        return {
            'members_eligible': len(member_rows),
            'members_updated': members_updated,
            'users_eligible': len(user_rows),
            'users_updated': users_updated,
            'cache_misses': cache_misses,
        }

    async def _bulk_update_members(
        self, batch: list[tuple[int, int, str]]
    ) -> int:
        """
        Bulk UPDATE members SET display_name = COALESCE(..., new) WHERE NULL.
        Returns the number of rows actually modified.
        """
        if not batch:
            return 0
        values_clause = sql.SQL(', ').join(
            sql.SQL('({}, {}, {})').format(
                sql.Placeholder(), sql.Placeholder(), sql.Placeholder(),
            )
            for _ in batch
        )
        query = sql.SQL(
            """
            UPDATE members AS m
            SET display_name = v.display_name
            FROM (VALUES {}) AS v(guildid, userid, display_name)
            WHERE m.guildid = v.guildid
              AND m.userid = v.userid
              AND m.display_name IS NULL
            """
        ).format(values_clause)
        async with self.bot.db.pool.connection() as conn:
            cur = await conn.execute(query, tuple(chain.from_iterable(batch)))
            return cur.rowcount or 0

    async def _bulk_update_user_config(
        self, batch: list[tuple[int, str, Optional[str]]]
    ) -> int:
        """
        Bulk UPDATE user_config, only writing columns that are still NULL.
        Returns the number of rows actually modified.
        """
        if not batch:
            return 0
        values_clause = sql.SQL(', ').join(
            sql.SQL('({}, {}, {})').format(
                sql.Placeholder(), sql.Placeholder(), sql.Placeholder(),
            )
            for _ in batch
        )
        query = sql.SQL(
            """
            UPDATE user_config AS u
            SET name = COALESCE(u.name, v.name),
                avatar_hash = COALESCE(u.avatar_hash, v.avatar_hash)
            FROM (VALUES {}) AS v(userid, name, avatar_hash)
            WHERE u.userid = v.userid
              AND (u.name IS NULL OR u.avatar_hash IS NULL)
            """
        ).format(values_clause)
        async with self.bot.db.pool.connection() as conn:
            cur = await conn.execute(query, tuple(chain.from_iterable(batch)))
            return cur.rowcount or 0


def _chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]

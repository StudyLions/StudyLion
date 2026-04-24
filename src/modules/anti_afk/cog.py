# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-06
# Purpose: Anti AFK System cog -- periodic activity checks for
#          voice channel users. Premium-only, website-configured.
#          No slash commands or admin config commands.
# ============================================================
import asyncio
import enum
import random
import time as _time
from collections import defaultdict
from typing import Optional, Dict, Set

import discord

from meta import LionBot, LionCog
from meta.logger import log_wrap
from utils.lib import utc_now

from . import logger, babel
from .data import AntiAfkData
from .ui import AntiAfkConfirmView, CUSTOM_ID_PREFIX

_p = babel._p


class CheckState(enum.Enum):
    IDLE = 'idle'
    PENDING = 'pending'
    ACTED = 'acted'


class TrackedUser:
    """In-memory state for a single user being tracked by Anti AFK."""
    __slots__ = (
        'guildid', 'userid', 'channelid', 'state',
        'last_check_at', 'last_prompt_sent_at', 'miss_count',
        'dm_fail_count', 'prompt_delivered', 'timeout_task',
        'prompt_message', 'lock',
    )

    def __init__(self, guildid: int, userid: int, channelid: int):
        self.guildid = guildid
        self.userid = userid
        self.channelid = channelid
        self.state = CheckState.IDLE
        self.last_check_at = _time.monotonic()
        self.last_prompt_sent_at: Optional[float] = None
        self.miss_count = 0
        self.dm_fail_count = 0
        self.prompt_delivered = False
        self.timeout_task: Optional[asyncio.Task] = None
        self.prompt_message: Optional[discord.Message] = None
        self.lock = asyncio.Lock()

    def reset_timer(self):
        self.state = CheckState.IDLE
        self.last_check_at = _time.monotonic()
        self.miss_count = 0
        self.dm_fail_count = 0
        self.prompt_delivered = False
        self.prompt_message = None
        if self.timeout_task and not self.timeout_task.done():
            self.timeout_task.cancel()
            self.timeout_task = None

    def cancel(self):
        if self.timeout_task and not self.timeout_task.done():
            self.timeout_task.cancel()
            self.timeout_task = None


STARTUP_GRACE_SECONDS = 120
CONFIG_CACHE_TTL = 60.0
LOOP_TICK_SECONDS = 30
MAX_MESSAGES_PER_MINUTE = 30
MAX_PROMPTS_PER_GUILD_PER_TICK = 10
VALID_ACTIONS = ('kick', 'pause', 'move_afk')
RECENTLY_ACTED_COOLDOWN = 300  # 5 minutes


class AntiAfkCog(LionCog):

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data: AntiAfkData = bot.db.load_registry(AntiAfkData())

        self._config_cache: dict[int, tuple[float, object]] = {}

        # {guildid: {userid: TrackedUser}}
        self._tracked: dict[int, dict[int, TrackedUser]] = defaultdict(dict)

        self._main_loop_task: Optional[asyncio.Task] = None
        self._loop_lock = asyncio.Lock()
        self._started_at: Optional[float] = None

        # Per-shard message rate limiter (sliding window)
        self._msg_timestamps: list[float] = []

        # Per-guild action counts: {guildid: [(timestamp, count)]}
        self._action_counts: dict[int, list[float]] = defaultdict(list)

        # Notification cooldowns: {guildid: last_notification_time}
        self._notif_cooldowns: dict[int, float] = {}

        # Recently acted-upon users: {(guildid, userid): monotonic_time}
        # Prevents re-tracking a user immediately after they were
        # moved/kicked (on_voice_state_update fires when they join AFK)
        self._recently_acted: dict[tuple[int, int], float] = {}

    # ─── Lifecycle ───────────────────────────────────────────

    async def cog_load(self):
        self._main_loop_task = asyncio.create_task(self._main_loop())
        logger.info(
            f"AntiAfkCog loaded on shard {self.bot.shard_id}. "
            f"Main loop started."
        )

    @LionCog.listener('on_interaction')
    async def on_anti_afk_interaction(self, interaction: discord.Interaction):
        """Handle anti-afk confirm button presses via on_interaction.

        Uses on_interaction (not bot.add_view) because each button has
        a dynamic custom_id containing the guild ID and target user ID.
        Static persistent views require exact custom_id match and can't
        handle this. Same pattern as LionGotchi family invites.
        """
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = ''
        if interaction.data:
            custom_id = interaction.data.get('custom_id', '')

        if not custom_id.startswith(CUSTOM_ID_PREFIX + ':'):
            return

        parts = custom_id.split(':')
        guildid = interaction.guild_id
        if not guildid and len(parts) >= 3:
            try:
                guildid = int(parts[2])
            except (ValueError, IndexError):
                pass

        if not guildid:
            await interaction.response.send_message(
                "Could not identify the server for this check.",
                ephemeral=True,
            )
            return

        # --- AI-MODIFIED (2026-04-24) ---
        # Purpose: Only the target user can confirm their own check.
        # The custom_id now encodes the target userid as the 4th part
        # (anti_afk:confirm:{guildid}:{userid}). If someone else
        # clicks the button, reject them with an ephemeral message.
        # Backwards-compatible: old buttons without a userid part
        # still work (fall back to interaction.user.id).
        target_userid = None
        if len(parts) >= 4:
            try:
                target_userid = int(parts[3])
            except (ValueError, IndexError):
                pass

        clicker_id = interaction.user.id
        if target_userid is not None and clicker_id != target_userid:
            try:
                await interaction.response.send_message(
                    f"This activity check is for <@{target_userid}>. "
                    f"Only they can confirm it.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass
            return

        userid = target_userid if target_userid is not None else clicker_id
        # --- END AI-MODIFIED ---
        handled, prompt_msg = await self.handle_confirm(guildid, userid)

        # --- AI-MODIFIED (2026-04-13) ---
        # Purpose: Show check_interval in confirmation so users know when the next check will be
        if handled:
            confirm_desc = (
                "\u2705 Confirmed! Your check timer has been reset. "
                "Stay productive!"
            )
            config = await self._get_config(guildid)
            if config and config.check_interval:
                confirm_desc += (
                    f"\n\n\u23f0 Next check in approximately "
                    f"**{config.check_interval} minute{'s' if config.check_interval != 1 else ''}**."
                )
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=confirm_desc,
            )
        else:
            embed = discord.Embed(
                colour=discord.Colour.greyple(),
                description=(
                    "This check has already been resolved. "
                    "No action needed."
                ),
            )
        # --- END AI-MODIFIED ---

        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

        if handled and prompt_msg:
            await self._edit_prompt_confirmed(prompt_msg, userid)
        # --- AI-MODIFIED (2026-04-24) ---
        # Purpose: Remove button from stale prompts but keep the message
        # visible instead of auto-deleting it.
        # --- Original code (commented out for rollback) ---
        # elif not handled and interaction.message:
        #     try:
        #         resolved_embed = discord.Embed(
        #             colour=discord.Colour.greyple(),
        #             title="\U0001f6e1\ufe0f Anti AFK Check \u2014 Resolved",
        #             description=f"<@{userid}> \u2014 this check has been resolved.",
        #         )
        #         await interaction.message.edit(
        #             embed=resolved_embed, view=None,
        #         )
        #         asyncio.create_task(
        #             self._delete_message_after(interaction.message, 10)
        #         )
        #     except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        #         pass
        # --- End original code ---
        elif not handled and interaction.message:
            try:
                resolved_embed = discord.Embed(
                    colour=discord.Colour.greyple(),
                    title="\U0001f6e1\ufe0f Anti AFK Check \u2014 Resolved",
                    description=f"<@{userid}> \u2014 this check has been resolved.",
                )
                await interaction.message.edit(
                    embed=resolved_embed, view=None,
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        # --- END AI-MODIFIED ---

    async def cog_unload(self):
        if self._main_loop_task and not self._main_loop_task.done():
            self._main_loop_task.cancel()

        for guild_users in self._tracked.values():
            for tu in guild_users.values():
                tu.cancel()
        self._tracked.clear()
        logger.info("AntiAfkCog unloaded. All tasks cancelled.")

    # ─── Config Cache ────────────────────────────────────────

    async def _get_config(self, guildid: int):
        now = _time.monotonic()
        cached = self._config_cache.get(guildid)
        if cached and (now - cached[0]) < CONFIG_CACHE_TTL:
            return cached[1]

        config = await self.data.Config.fetch_config(guildid)
        self._config_cache[guildid] = (now, config)
        return config

    def _invalidate_config(self, guildid: int):
        self._config_cache.pop(guildid, None)

    # ─── Premium Check ───────────────────────────────────────

    async def _is_premium(self, guildid: int) -> bool:
        premcog = self.bot.get_cog('PremiumCog')
        if not premcog:
            return False
        try:
            return await premcog.is_premium_guild(guildid)
        except Exception:
            return False

    # ─── Rate Limiting ───────────────────────────────────────

    def _can_send_message(self) -> bool:
        """Check per-shard message rate limit (sliding window)."""
        now = _time.monotonic()
        self._msg_timestamps = [
            t for t in self._msg_timestamps if now - t < 60
        ]
        return len(self._msg_timestamps) < MAX_MESSAGES_PER_MINUTE

    def _record_message_sent(self):
        self._msg_timestamps.append(_time.monotonic())

    def _count_actions_this_hour(self, guildid: int) -> int:
        now = _time.monotonic()
        timestamps = self._action_counts[guildid]
        self._action_counts[guildid] = [
            t for t in timestamps if now - t < 3600
        ]
        return len(self._action_counts[guildid])

    def _record_action(self, guildid: int):
        self._action_counts[guildid].append(_time.monotonic())

    # ─── Blacklist / Exemption Checks ────────────────────────

    def _is_blacklisted(self, userid: int) -> bool:
        blacklists = self.bot.get_cog('Blacklists')
        if blacklists and userid in blacklists.user_blacklist:
            return True
        return False

    def _is_in_pomodoro(self, channelid: int) -> bool:
        pomo_cog = self.bot.get_cog('TimerCog')
        if not pomo_cog:
            return False
        for guild_timers in pomo_cog.timers.values():
            for timer in guild_timers.values():
                if timer.data and timer.data.channelid == channelid:
                    return True
        return False

    def _has_exempt_role(self, member: discord.Member, config) -> bool:
        exempt = set(config.exempt_roles_list)
        if not exempt:
            return False
        return bool(exempt & {r.id for r in member.roles})

    # --- AI-MODIFIED (2026-04-24) ---
    # Purpose: Support category IDs in target_channels and exclude_channels.
    # If a category ID is in excludes, all voice channels under it are excluded.
    # If a category ID is in targets, all voice channels under it match.
    # Accepts either a channel object or a plain channel ID for backwards compat.
    def _is_channel_applicable(self, channel, config) -> bool:
        targets = set(config.target_channels_list)
        excludes = set(config.exclude_channels_list)

        if isinstance(channel, int):
            channelid = channel
            category_id = None
        else:
            channelid = channel.id
            category_id = getattr(channel, 'category_id', None)

        if channelid in excludes:
            return False
        if category_id and category_id in excludes:
            return False

        if targets:
            if channelid in targets:
                return True
            if category_id and category_id in targets:
                return True
            return False

        return True
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-19) ---
    # Purpose: Bug fix -- AFK checks were firing in voice channels under
    # untracked categories (user-reported). The AFK module had its own
    # exclude_channels list but ignored the guild-wide untracked_channels
    # list (which is what users configure in the dashboard's voice tracker
    # to mark hangout/chat-only categories). Reuse the voice tracker's
    # is_untracked() method which already handles both individual channel
    # IDs and category IDs.
    def _is_guild_untracked(self, channel) -> bool:
        """Return True if the channel (or its parent category) is in the
        guild's voice-tracker untracked_channels list.

        This keeps AFK behaviour consistent with study-time tracking: if
        time isn't tracked in a channel, AFK checks shouldn't fire there
        either. Falls back to False when the voice tracker cog isn't
        loaded so we don't accidentally block all checks on bot startup.
        """
        voice_cog = self.bot.get_cog('VoiceTrackerCog')
        if voice_cog is None:
            return False
        try:
            return voice_cog.is_untracked(channel)
        except (ValueError, AttributeError):
            return False
    # --- END AI-MODIFIED ---

    def _channel_user_count(self, channel: discord.VoiceChannel) -> int:
        return sum(1 for m in channel.members if not m.bot)

    # ─── Event Listeners ─────────────────────────────────────

    @LionCog.listener('on_voice_state_update')
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return
        if self._is_blacklisted(member.id):
            return

        guildid = member.guild.id
        userid = member.id

        left_channel = before.channel if before.channel else None
        joined_channel = after.channel if after.channel else None

        # User left a channel
        if left_channel and (not joined_channel or joined_channel.id != left_channel.id):
            self._remove_user(guildid, userid)

        # User joined or moved to a channel
        if joined_channel:
            guild_users = self._tracked.get(guildid, {})
            existing = guild_users.get(userid)

            if existing and existing.channelid != joined_channel.id:
                # --- AI-MODIFIED (2026-04-19) ---
                # Purpose: If the user moved into an untracked channel,
                # stop tracking them entirely instead of just resetting
                # the timer. Otherwise we'd keep firing checks on someone
                # in a hangout/chat-only category.
                if self._is_guild_untracked(joined_channel):
                    self._remove_user(guildid, userid)
                    return
                # --- END AI-MODIFIED ---

                # Channel switch: cancel pending check, reset timer (activity proof)
                async with existing.lock:
                    existing.cancel()
                    existing.channelid = joined_channel.id
                    existing.state = CheckState.IDLE
                    existing.last_check_at = _time.monotonic()
                    existing.miss_count = 0
                    existing.prompt_delivered = False

            if not existing:
                await self._maybe_start_tracking(member, joined_channel)

    async def _maybe_start_tracking(
        self, member: discord.Member, channel: discord.abc.GuildChannel
    ):
        guildid = member.guild.id

        # Don't re-track users who were just acted upon
        key = (guildid, member.id)
        acted_at = self._recently_acted.get(key)
        if acted_at is not None:
            if _time.monotonic() - acted_at < RECENTLY_ACTED_COOLDOWN:
                return
            else:
                del self._recently_acted[key]

        if not await self._is_premium(guildid):
            return

        config = await self._get_config(guildid)
        if not config or not config.enabled:
            return

        if not self._is_channel_applicable(channel, config):
            return

        # --- AI-MODIFIED (2026-04-19) ---
        # Purpose: Skip AFK tracking for channels in the guild's
        # untracked_channels list (handles category IDs too). See
        # _is_guild_untracked() for context.
        if self._is_guild_untracked(channel):
            return
        # --- END AI-MODIFIED ---

        if self._is_in_pomodoro(channel.id):
            return

        tu = TrackedUser(guildid, member.id, channel.id)
        self._tracked[guildid][member.id] = tu

    def _remove_user(self, guildid: int, userid: int):
        guild_users = self._tracked.get(guildid)
        if guild_users:
            tu = guild_users.pop(userid, None)
            if tu:
                tu.cancel()
            if not guild_users:
                self._tracked.pop(guildid, None)

    @LionCog.listener('on_voice_session_end')
    async def on_voice_session_end(self, data, now):
        guildid = data.guildid
        userid = data.userid
        self._remove_user(guildid, userid)

    # ─── Button Confirm Handler ──────────────────────────────

    async def handle_confirm(
        self, guildid: int, userid: int,
    ) -> tuple[bool, Optional[discord.Message]]:
        guild_users = self._tracked.get(guildid)
        if not guild_users:
            return False, None

        tu = guild_users.get(userid)
        if not tu:
            return False, None

        async with tu.lock:
            if tu.state == CheckState.ACTED:
                return False, None

            if tu.state != CheckState.PENDING:
                return False, None

            prompt_msg = tu.prompt_message
            tu.reset_timer()
            logger.debug(
                f"Anti AFK confirm: <uid:{userid}> in <gid:{guildid}> "
                f"confirmed presence."
            )
            return True, prompt_msg

    # ─── Prompt Message Editing ────────────────────────────────

    # --- AI-MODIFIED (2025-04-07) ---
    # Purpose: Delete AFK check prompts after a short delay so they don't
    # stay permanently in channels (user feedback: stale buttons are confusing)
    async def _delete_message_after(self, message: discord.Message, delay: float):
        """Delete a message after a delay. Fire-and-forget via create_task."""
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        except asyncio.CancelledError:
            pass
    # --- END AI-MODIFIED ---

    async def _edit_prompt_confirmed(
        self, message: discord.Message, userid: int,
    ):
        """Edit the original prompt to show the user confirmed."""
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            title="\U0001f6e1\ufe0f Anti AFK Check \u2014 Confirmed",
            description=f"<@{userid}> confirmed they're still active. \u2705",
        )
        try:
            # --- AI-MODIFIED (2026-04-24) ---
            # Purpose: Keep the confirmed prompt visible (don't auto-delete) so
            # users and mods have a record that the check happened. The mention
            # in content is also preserved.
            # --- Original code (commented out for rollback) ---
            # await message.edit(embed=embed, view=None)
            # asyncio.create_task(self._delete_message_after(message, 10))
            # --- End original code ---
            await message.edit(embed=embed, view=None)
            # --- END AI-MODIFIED ---
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    async def _edit_prompt_expired(
        self, message: discord.Message, userid: int, action_label: str,
    ):
        """Edit the original prompt to show the check expired and action taken."""
        embed = discord.Embed(
            colour=discord.Colour.red(),
            title="\U0001f6e1\ufe0f Anti AFK Check \u2014 Expired",
            description=(
                f"<@{userid}> did not respond in time.\n"
                f"**Action taken:** {action_label}"
            ),
        )
        try:
            # --- AI-MODIFIED (2026-04-24) ---
            # Purpose: Keep the @mention content so users can still see who was
            # pinged. Previously content was cleared to None which lost the ping.
            # The embed description already contains <@userid> for display, but
            # the content mention is what users see in their notification history.
            # --- Original code (commented out for rollback) ---
            # await message.edit(content=None, embed=embed, view=None)
            # --- End original code ---
            await message.edit(embed=embed, view=None)
            # --- END AI-MODIFIED ---
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    # ─── Main Loop ───────────────────────────────────────────

    async def _main_loop(self):
        try:
            await self.bot.wait_until_ready()
            self._started_at = _time.monotonic()
            logger.info(
                f"Anti AFK main loop waiting {STARTUP_GRACE_SECONDS}s "
                f"startup grace period..."
            )
            await asyncio.sleep(STARTUP_GRACE_SECONDS)

            await self._initialize_tracking()

            while True:
                try:
                    if self._loop_lock.locked():
                        logger.warning(
                            "Anti AFK loop overlap detected, skipping tick."
                        )
                        await asyncio.sleep(LOOP_TICK_SECONDS)
                        continue

                    async with self._loop_lock:
                        await self._process_tick()

                except Exception:
                    logger.error(
                        "Anti AFK loop iteration error", exc_info=True
                    )

                await asyncio.sleep(LOOP_TICK_SECONDS)

        except asyncio.CancelledError:
            return
        except Exception:
            logger.error("Fatal error in Anti AFK main loop", exc_info=True)

    async def _initialize_tracking(self):
        """Scan all VCs on this shard and initialize tracking."""
        import itertools

        count = 0
        for guild in self.bot.guilds:
            config = await self._get_config(guild.id)
            if not config or not config.enabled:
                continue

            if not await self._is_premium(guild.id):
                continue

            for channel in itertools.chain(
                guild.voice_channels, guild.stage_channels
            ):
                if not self._is_channel_applicable(channel, config):
                    continue
                # --- AI-MODIFIED (2026-04-19) ---
                # Purpose: Skip channels in the guild's untracked_channels
                # list (incl. category matches). See _is_guild_untracked().
                if self._is_guild_untracked(channel):
                    continue
                # --- END AI-MODIFIED ---
                if self._is_in_pomodoro(channel.id):
                    continue

                for member in channel.members:
                    if member.bot:
                        continue
                    if self._is_blacklisted(member.id):
                        continue
                    if self._has_exempt_role(member, config):
                        continue
                    if member.id in self._tracked.get(guild.id, {}):
                        continue

                    tu = TrackedUser(guild.id, member.id, channel.id)
                    self._tracked[guild.id][member.id] = tu
                    count += 1

        logger.info(
            f"Anti AFK initialized: tracking {count} users across "
            f"{len(self._tracked)} guilds."
        )

    async def _process_tick(self):
        """Process one tick of the main loop."""
        now_mono = _time.monotonic()

        # Clean up expired recently-acted entries
        expired = [
            k for k, t in self._recently_acted.items()
            if now_mono - t > RECENTLY_ACTED_COOLDOWN
        ]
        for k in expired:
            del self._recently_acted[k]

        guild_ids = list(self._tracked.keys())

        random.shuffle(guild_ids)

        for guildid in guild_ids:
            try:
                await self._process_guild_tick(guildid, now_mono)
            except Exception:
                logger.error(
                    f"Anti AFK error processing guild <gid:{guildid}>",
                    exc_info=True,
                )

    async def _process_guild_tick(self, guildid: int, now_mono: float):
        config = await self._get_config(guildid)

        if not config or not config.enabled:
            self._cancel_guild(guildid)
            return

        if not await self._is_premium(guildid):
            self._cancel_guild(guildid)
            return

        guild = self.bot.get_guild(guildid)
        if not guild:
            self._cancel_guild(guildid)
            return

        guild_users = self._tracked.get(guildid)
        if not guild_users:
            return

        check_interval_sec = config.check_interval * 60
        grace_period_sec = config.grace_period * 60
        max_warnings = max(config.max_warnings, 1)
        min_users = max(config.min_users, 1)

        prompts_this_tick = 0

        # Batch prompts by channel for VC text mode
        channel_prompts: dict[int, list[TrackedUser]] = defaultdict(list)

        user_list = list(guild_users.values())
        for tu in user_list:
            if tu.state == CheckState.ACTED:
                continue

            if tu.state == CheckState.PENDING:
                continue

            # IDLE: check if due
            if tu.state == CheckState.IDLE:
                elapsed = now_mono - tu.last_check_at
                if elapsed < check_interval_sec:
                    continue

                # Hard-reject: never send a prompt within grace_period
                # of the last one, even if the state machine has a bug
                if tu.last_prompt_sent_at is not None:
                    since_last = now_mono - tu.last_prompt_sent_at
                    if since_last < grace_period_sec:
                        continue

                # Check channel still exists and user is in it
                channel = guild.get_channel(tu.channelid)
                if not channel or not isinstance(
                    channel, (discord.VoiceChannel, discord.StageChannel)
                ):
                    self._remove_user(guildid, tu.userid)
                    continue

                member = guild.get_member(tu.userid)
                if not member or not member.voice or (
                    member.voice.channel and member.voice.channel.id != tu.channelid
                ):
                    self._remove_user(guildid, tu.userid)
                    continue

                # --- AI-MODIFIED (2026-04-19) ---
                # Purpose: Catch the case where the guild added this
                # channel/category to untracked_channels after the user
                # was already being tracked. Drop them so we don't keep
                # firing AFK prompts in a now-untracked channel.
                if self._is_guild_untracked(channel):
                    self._remove_user(guildid, tu.userid)
                    continue
                # --- END AI-MODIFIED ---

                # Exempt role check
                if self._has_exempt_role(member, config):
                    tu.last_check_at = now_mono
                    continue

                # Pomodoro channel check
                if self._is_in_pomodoro(tu.channelid):
                    tu.last_check_at = now_mono
                    continue

                # Streaming/camera exemption
                if config.skip_streaming and member.voice:
                    if member.voice.self_stream or member.voice.self_video:
                        tu.last_check_at = now_mono
                        continue

                # Min users check
                user_count = self._channel_user_count(channel)
                if user_count < min_users:
                    continue

                # Rate limiting
                if not self._can_send_message():
                    logger.warning(
                        f"Anti AFK shard rate limit hit, deferring."
                    )
                    break

                if prompts_this_tick >= MAX_PROMPTS_PER_GUILD_PER_TICK:
                    break

                channel_prompts[tu.channelid].append(tu)
                prompts_this_tick += 1

        # Send batched prompts
        for channelid, users in channel_prompts.items():
            try:
                await self._send_prompts(
                    guild, config, channelid, users,
                    grace_period_sec, max_warnings,
                )
            except Exception:
                logger.error(
                    f"Anti AFK prompt error in <cid:{channelid}>",
                    exc_info=True,
                )

    def _cancel_guild(self, guildid: int):
        guild_users = self._tracked.pop(guildid, None)
        if guild_users:
            for tu in guild_users.values():
                tu.cancel()

    # ─── Prompt Sending ──────────────────────────────────────

    async def _send_prompts(
        self,
        guild: discord.Guild,
        config,
        channelid: int,
        users: list[TrackedUser],
        grace_period_sec: int,
        max_warnings: int,
    ):
        channel = guild.get_channel(channelid)
        if not channel:
            return

        userids = [tu.userid for tu in users]

        # --- AI-MODIFIED (2026-04-07) ---
        # Purpose: Add custom channel delivery mode. If prompt_channelid
        # is set, all prompts go to that one text channel with @mentions
        # instead of each user's VC text chat.
        prompt_ch = None
        if getattr(config, 'prompt_channelid', None):
            prompt_ch = guild.get_channel(config.prompt_channelid)

        if prompt_ch:
            await self._send_vc_text_prompt(
                guild, config, prompt_ch, users,
                grace_period_sec, max_warnings,
            )
        elif config.use_dms:
            await self._send_dm_prompts(
                guild, config, users, grace_period_sec, max_warnings,
            )
        else:
            await self._send_vc_text_prompt(
                guild, config, channel, users,
                grace_period_sec, max_warnings,
            )
        # --- END AI-MODIFIED ---

    async def _send_vc_text_prompt(
        self,
        guild: discord.Guild,
        config,
        channel,
        users: list[TrackedUser],
        grace_period_sec: int,
        max_warnings: int,
    ):
        warning_text = config.warning_message or "Are you still studying?"

        for tu in users:
            description_parts = [
                f"<@{tu.userid}>\n\n{warning_text}",
                f"\nClick the button below within **{config.grace_period} minute{'s' if config.grace_period != 1 else ''}** to confirm.",
            ]

            if max_warnings > 1:
                current = tu.miss_count + 1
                if current < max_warnings:
                    description_parts.append(
                        f"\n\u26a0\ufe0f This is check {current} of {max_warnings}."
                    )

            # --- AI-MODIFIED (2026-04-13) ---
            # Purpose: Show check_interval so users know when the next check will be
            description_parts.append(
                f"\n\n\u23f0 Next check: **{config.check_interval} minute{'s' if config.check_interval != 1 else ''}** after confirming."
            )
            # --- END AI-MODIFIED ---

            embed = discord.Embed(
                colour=discord.Colour.gold(),
                title="\U0001f6e1\ufe0f Anti AFK Check",
                description=''.join(description_parts),
            )

            # --- AI-MODIFIED (2026-04-24) ---
            # Purpose: Pass userid to view so button custom_id encodes the target
            view = AntiAfkConfirmView(guild.id, tu.userid)
            # --- END AI-MODIFIED ---

            try:
                # --- AI-MODIFIED (2026-04-07) ---
                # Purpose: Mention user in content so Discord delivers an actual
                # ping notification. Mentions inside embeds do not trigger pings.
                msg = await channel.send(
                    content=f"<@{tu.userid}>",
                    embed=embed,
                    view=view,
                )
                # --- END AI-MODIFIED ---
                self._record_message_sent()

                async with tu.lock:
                    tu.state = CheckState.PENDING
                    tu.last_prompt_sent_at = _time.monotonic()
                    tu.prompt_delivered = True
                    tu.prompt_message = msg
                    tu.timeout_task = asyncio.create_task(
                        self._handle_timeout(
                            tu, config, guild, grace_period_sec, max_warnings,
                        )
                    )

            except discord.Forbidden:
                logger.warning(
                    f"Anti AFK: Missing Send Messages permission in "
                    f"<cid:{channel.id}> <gid:{guild.id}>"
                )
                break
            except discord.HTTPException:
                logger.warning(
                    f"Anti AFK: Failed to send VC text prompt in "
                    f"<cid:{channel.id}> <gid:{guild.id}>",
                    exc_info=True,
                )

            if len(users) > 1:
                await asyncio.sleep(0.5)

    async def _send_dm_prompts(
        self,
        guild: discord.Guild,
        config,
        users: list[TrackedUser],
        grace_period_sec: int,
        max_warnings: int,
    ):
        for tu in users:
            member = guild.get_member(tu.userid)
            if not member:
                self._remove_user(guild.id, tu.userid)
                continue

            if tu.dm_fail_count >= 3:
                await self._send_fallback_mention(
                    guild, config, [tu], grace_period_sec, max_warnings,
                )
                continue

            warning_text = config.warning_message or "Are you still studying?"
            current_warning = tu.miss_count + 1

            desc = f"{warning_text}\n\n"
            desc += (
                f"Click the button below within "
                f"**{config.grace_period} minute{'s' if config.grace_period != 1 else ''}** "
                f"to confirm you're still active in **{guild.name}**."
            )
            if max_warnings > 1:
                desc += f"\n\n\u26a0\ufe0f Warning {current_warning} of {max_warnings}."
            # --- AI-MODIFIED (2026-04-13) ---
            # Purpose: Show check_interval so users know when the next check will be
            desc += (
                f"\n\n\u23f0 Next check: **{config.check_interval} minute{'s' if config.check_interval != 1 else ''}** "
                f"after confirming."
            )
            # --- END AI-MODIFIED ---

            embed = discord.Embed(
                colour=discord.Colour.gold(),
                title="\U0001f6e1\ufe0f Anti AFK Check",
                description=desc,
            )
            embed.set_footer(text=f"Server: {guild.name}")

            # --- AI-MODIFIED (2026-04-24) ---
            # Purpose: Pass userid to view so button custom_id encodes the target
            view = AntiAfkConfirmView(guild.id, tu.userid)
            # --- END AI-MODIFIED ---

            try:
                msg = await member.send(embed=embed, view=view)
                self._record_message_sent()

                async with tu.lock:
                    tu.state = CheckState.PENDING
                    tu.last_prompt_sent_at = _time.monotonic()
                    tu.prompt_delivered = True
                    tu.prompt_message = msg
                    tu.dm_fail_count = 0
                    tu.timeout_task = asyncio.create_task(
                        self._handle_timeout(
                            tu, config, guild, grace_period_sec, max_warnings,
                        )
                    )

            except discord.Forbidden:
                tu.dm_fail_count += 1
                logger.debug(
                    f"Anti AFK: DM blocked for <uid:{tu.userid}> "
                    f"in <gid:{guild.id}> (fail #{tu.dm_fail_count})"
                )
                if tu.dm_fail_count >= 3:
                    await self._send_fallback_mention(
                        guild, config, [tu], grace_period_sec, max_warnings,
                    )
            except discord.HTTPException:
                tu.dm_fail_count += 1
                logger.warning(
                    f"Anti AFK: DM send error for <uid:{tu.userid}>",
                    exc_info=True,
                )

            await asyncio.sleep(1)

    async def _send_fallback_mention(
        self,
        guild: discord.Guild,
        config,
        users: list[TrackedUser],
        grace_period_sec: int,
        max_warnings: int,
    ):
        fallback_id = config.fallback_channelid
        if not fallback_id:
            for tu in users:
                logger.debug(
                    f"Anti AFK: No fallback channel for <gid:{guild.id}>, "
                    f"skipping <uid:{tu.userid}>"
                )
                tu.last_check_at = _time.monotonic()
            return

        channel = guild.get_channel(fallback_id)
        if not channel:
            return

        warning_text = config.warning_message or "Are you still studying?"

        for tu in users:
            # --- AI-MODIFIED (2026-04-13) ---
            # Purpose: Show check_interval so users know when the next check will be
            embed = discord.Embed(
                colour=discord.Colour.gold(),
                title="\U0001f6e1\ufe0f Anti AFK Check",
                description=(
                    f"<@{tu.userid}>\n\n{warning_text}\n\n"
                    f"Click the button below within "
                    f"**{config.grace_period} minute{'s' if config.grace_period != 1 else ''}** to confirm."
                    f"\n\n\u23f0 Next check: **{config.check_interval} minute{'s' if config.check_interval != 1 else ''}** after confirming."
                ),
            )
            # --- END AI-MODIFIED ---

            # --- AI-MODIFIED (2026-04-24) ---
            # Purpose: Pass userid to view so button custom_id encodes the target
            view = AntiAfkConfirmView(guild.id, tu.userid)
            # --- END AI-MODIFIED ---

            try:
                # --- AI-MODIFIED (2026-04-07) ---
                # Purpose: Mention user in content so Discord delivers an actual
                # ping notification. Mentions inside embeds do not trigger pings.
                msg = await channel.send(
                    content=f"<@{tu.userid}>",
                    embed=embed,
                    view=view,
                )
                # --- END AI-MODIFIED ---
                self._record_message_sent()

                async with tu.lock:
                    tu.state = CheckState.PENDING
                    tu.last_prompt_sent_at = _time.monotonic()
                    tu.prompt_delivered = True
                    tu.prompt_message = msg
                    tu.timeout_task = asyncio.create_task(
                        self._handle_timeout(
                            tu, config, guild, grace_period_sec, max_warnings,
                        )
                    )
            except (discord.Forbidden, discord.HTTPException):
                logger.warning(
                    f"Anti AFK: Fallback channel send failed in <gid:{guild.id}>",
                    exc_info=True,
                )

    # ─── Timeout Handling ────────────────────────────────────

    async def _handle_timeout(
        self,
        tu: TrackedUser,
        config,
        guild: discord.Guild,
        grace_period_sec: int,
        max_warnings: int,
    ):
        try:
            await asyncio.sleep(grace_period_sec)

            async with tu.lock:
                if tu.state != CheckState.PENDING:
                    return

                if not tu.prompt_delivered:
                    tu.state = CheckState.IDLE
                    tu.last_check_at = _time.monotonic()
                    return

                tu.miss_count += 1

                fresh_config = await self._get_config(tu.guildid)
                if not fresh_config or not fresh_config.enabled:
                    tu.state = CheckState.IDLE
                    tu.last_check_at = _time.monotonic()
                    return

                if not await self._is_premium(tu.guildid):
                    tu.state = CheckState.IDLE
                    tu.last_check_at = _time.monotonic()
                    return

                effective_max = max(fresh_config.max_warnings, 1)

                if tu.miss_count < effective_max:
                    tu.state = CheckState.IDLE
                    tu.last_check_at = _time.monotonic()
                    tu.prompt_delivered = False
                    # --- AI-MODIFIED (2026-04-24) ---
                    # Purpose: Edit the old prompt to show "Missed" with no
                    # button, instead of deleting it. Keeps the ping visible
                    # so the user can see they were checked.
                    # --- Original code (commented out for rollback) ---
                    # old_prompt = tu.prompt_message
                    # tu.prompt_message = None
                    # if old_prompt:
                    #     asyncio.create_task(
                    #         self._delete_message_after(old_prompt, 5)
                    #     )
                    # --- End original code ---
                    old_prompt = tu.prompt_message
                    tu.prompt_message = None
                    if old_prompt:
                        missed_embed = discord.Embed(
                            colour=discord.Colour.orange(),
                            title="\U0001f6e1\ufe0f Anti AFK Check \u2014 Missed",
                            description=(
                                f"<@{tu.userid}> did not respond. "
                                f"Warning {tu.miss_count} of {effective_max}."
                            ),
                        )
                        try:
                            asyncio.create_task(
                                old_prompt.edit(embed=missed_embed, view=None)
                            )
                        except Exception:
                            pass
                    # --- END AI-MODIFIED ---
                    logger.debug(
                        f"Anti AFK: <uid:{tu.userid}> missed check "
                        f"{tu.miss_count}/{effective_max} in <gid:{tu.guildid}>"
                    )
                    return

                action_count = self._count_actions_this_hour(tu.guildid)
                hourly_cap = fresh_config.max_actions_per_hour or 100
                if action_count >= hourly_cap:
                    logger.warning(
                        f"Anti AFK: Action cap ({hourly_cap}/hr) reached "
                        f"for <gid:{tu.guildid}>, skipping action on "
                        f"<uid:{tu.userid}>"
                    )
                    await self._send_cap_warning(guild, fresh_config)
                    tu.state = CheckState.IDLE
                    tu.last_check_at = _time.monotonic()
                    return

                await self._apply_consequence(
                    tu, fresh_config, guild,
                )

        except asyncio.CancelledError:
            return
        except Exception:
            logger.error(
                f"Anti AFK timeout handler error for <uid:{tu.userid}>",
                exc_info=True,
            )

    # ─── Consequence Execution ───────────────────────────────

    # --- AI-REPLACED (2026-04-07) ---
    # Reason: Race condition -- moving/disconnecting a user fires
    # on_voice_state_update which calls tu.cancel(), killing the timeout
    # task before post-action cleanup (edit prompt, notifications) runs.
    # What the new code does better: Pre-sets _recently_acted so the voice
    # state handler won't re-track the user, and uses asyncio.create_task
    # for all post-action Discord API calls so they survive task cancellation.
    # --- Original code (commented out for rollback) ---
    # async def _apply_consequence(
    #     self,
    #     tu: TrackedUser,
    #     config,
    #     guild: discord.Guild,
    # ):
    #     member = guild.get_member(tu.userid)
    #     if not member:
    #         self._remove_user(tu.guildid, tu.userid)
    #         return
    #
    #     action = config.action if config.action in VALID_ACTIONS else 'kick'
    #     success = False
    #
    #     try:
    #         if action == 'move_afk':
    #             afk_channel = guild.afk_channel
    #             if afk_channel:
    #                 await member.move_to(
    #                     afk_channel,
    #                     reason="Anti AFK: User did not respond to activity check",
    #                 )
    #                 success = True
    #             else:
    #                 await member.edit(
    #                     voice_channel=None,
    #                     reason="Anti AFK: No AFK channel, disconnecting instead",
    #                 )
    #                 success = True
    #         elif action == 'pause':
    #             await member.edit(
    #                 voice_channel=None,
    #                 reason="Anti AFK: Session paused due to inactivity",
    #             )
    #             success = True
    #         else:
    #             await member.edit(
    #                 voice_channel=None,
    #                 reason="Anti AFK: User did not respond to activity check",
    #             )
    #             success = True
    #
    #     except discord.Forbidden:
    #         logger.warning(
    #             f"Anti AFK: Missing Move Members permission in "
    #             f"<gid:{guild.id}> for <uid:{tu.userid}>"
    #         )
    #         await self._notify_permission_error(guild, config, member)
    #     except discord.HTTPException:
    #         logger.warning(
    #             f"Anti AFK: Failed to apply consequence to "
    #             f"<uid:{tu.userid}> in <gid:{guild.id}>",
    #             exc_info=True,
    #         )
    #
    #     if success:
    #         tu.state = CheckState.ACTED
    #         self._record_action(tu.guildid)
    #         self._recently_acted[(tu.guildid, tu.userid)] = _time.monotonic()
    #         logger.info(
    #             f"Anti AFK: Applied '{action}' to <uid:{tu.userid}> "
    #             f"in <gid:{guild.id}> after {tu.miss_count} missed checks."
    #         )
    #
    #         action_labels = {
    #             'kick': 'Disconnected',
    #             'pause': 'Session paused',
    #             'move_afk': 'Moved to AFK channel',
    #         }
    #         action_label = action_labels.get(action, action)
    #
    #         # Edit the original prompt to show what happened
    #         if tu.prompt_message:
    #             await self._edit_prompt_expired(
    #                 tu.prompt_message, tu.userid, action_label,
    #             )
    #
    #         # Notify in the AFK channel's text chat when moved there
    #         if action == 'move_afk' and guild.afk_channel:
    #             await self._send_afk_channel_notice(
    #                 guild, guild.afk_channel, member,
    #             )
    #
    #         await self._send_action_notification(
    #             guild, config, member, action, tu.miss_count,
    #         )
    #         self._remove_user(tu.guildid, tu.userid)
    # --- End original code ---
    # --- AI-MODIFIED (2026-04-13) ---
    # Purpose: Fix race condition where disconnecting the user triggers
    # on_voice_state_update -> _remove_user -> tu.cancel(), which cancels
    # THIS running task before the prompt can be edited to "Expired".
    # Fix: clear tu.timeout_task before the disconnect so tu.cancel() is
    # a no-op, and mark state as ACTED immediately.
    async def _apply_consequence(
        self,
        tu: TrackedUser,
        config,
        guild: discord.Guild,
    ):
        member = guild.get_member(tu.userid)
        if not member:
            self._remove_user(tu.guildid, tu.userid)
            return

        action = config.action if config.action in VALID_ACTIONS else 'kick'
        success = False
        prompt_msg = tu.prompt_message
        miss_count = tu.miss_count

        tu.state = CheckState.ACTED
        tu.timeout_task = None

        self._recently_acted[(tu.guildid, tu.userid)] = _time.monotonic()

        try:
            if action == 'move_afk':
                afk_channel = guild.afk_channel
                if afk_channel:
                    await member.move_to(
                        afk_channel,
                        reason="Anti AFK: User did not respond to activity check",
                    )
                    success = True
                else:
                    await member.edit(
                        voice_channel=None,
                        reason="Anti AFK: No AFK channel, disconnecting instead",
                    )
                    success = True
            elif action == 'pause':
                await member.edit(
                    voice_channel=None,
                    reason="Anti AFK: Session paused due to inactivity",
                )
                success = True
            else:
                await member.edit(
                    voice_channel=None,
                    reason="Anti AFK: User did not respond to activity check",
                )
                success = True

        except discord.Forbidden:
            logger.warning(
                f"Anti AFK: Missing Move Members permission in "
                f"<gid:{guild.id}> for <uid:{tu.userid}>"
            )
            self._recently_acted.pop((tu.guildid, tu.userid), None)
            asyncio.create_task(
                self._notify_permission_error(guild, config, member)
            )
            return
        except discord.HTTPException:
            logger.warning(
                f"Anti AFK: Failed to apply consequence to "
                f"<uid:{tu.userid}> in <gid:{guild.id}>",
                exc_info=True,
            )
            self._recently_acted.pop((tu.guildid, tu.userid), None)
            return

        if success:
            self._record_action(tu.guildid)
            logger.info(
                f"Anti AFK: Applied '{action}' to <uid:{tu.userid}> "
                f"in <gid:{guild.id}> after {miss_count} missed checks."
            )

            action_labels = {
                'kick': 'Disconnected',
                'pause': 'Session paused',
                'move_afk': 'Moved to AFK channel',
            }
            action_label = action_labels.get(action, action)

            if prompt_msg:
                asyncio.create_task(
                    self._edit_prompt_expired(
                        prompt_msg, tu.userid, action_label,
                    )
                )

            if action == 'move_afk' and guild.afk_channel:
                asyncio.create_task(
                    self._send_afk_channel_notice(
                        guild, guild.afk_channel, member,
                    )
                )

            asyncio.create_task(
                self._send_action_notification(
                    guild, config, member, action, miss_count,
                )
            )
            self._remove_user(tu.guildid, tu.userid)
    # --- END AI-MODIFIED ---
    # --- END AI-REPLACED ---

    # ─── Notifications ───────────────────────────────────────

    async def _send_afk_channel_notice(
        self,
        guild: discord.Guild,
        afk_channel: discord.VoiceChannel,
        member: discord.Member,
    ):
        """Send a notice in the AFK channel's text chat."""
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            description=(
                f"{member.mention} You were moved to the AFK channel "
                f"because you didn't respond to the activity check."
            ),
        )

        try:
            # --- AI-MODIFIED (2026-04-13) ---
            # Purpose: Ping user in content so they get a notification in the AFK
            # channel. Mentions inside embeds don't trigger Discord pings.
            # --- Original code (commented out for rollback) ---
            # await afk_channel.send(embed=embed)
            # --- End original code ---
            await afk_channel.send(content=member.mention, embed=embed)
            # --- END AI-MODIFIED ---
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _send_action_notification(
        self,
        guild: discord.Guild,
        config,
        member: discord.Member,
        action: str,
        miss_count: int,
    ):
        if not config.notify_on_action:
            return

        notif_channel_id = config.notification_channelid
        if not notif_channel_id:
            return

        now_mono = _time.monotonic()
        last_notif = self._notif_cooldowns.get(guild.id, 0)
        if now_mono - last_notif < 30:
            return

        channel = guild.get_channel(notif_channel_id)
        if not channel:
            return

        action_labels = {
            'kick': 'Disconnected',
            'pause': 'Session paused',
            'move_afk': 'Moved to AFK',
        }
        action_label = action_labels.get(action, action)

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title="\U0001f6e1\ufe0f Anti AFK Action",
            description=(
                f"**{action_label}**: {member.mention}\n"
                f"Missed {miss_count} activity check{'s' if miss_count != 1 else ''}."
            ),
            timestamp=utc_now(),
        )

        try:
            await channel.send(embed=embed)
            self._notif_cooldowns[guild.id] = now_mono
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _send_cap_warning(self, guild: discord.Guild, config):
        if not config.notification_channelid:
            return

        now_mono = _time.monotonic()
        last_notif = self._notif_cooldowns.get(guild.id, 0)
        if now_mono - last_notif < 300:
            return

        channel = guild.get_channel(config.notification_channelid)
        if not channel:
            return

        embed = discord.Embed(
            colour=discord.Colour.red(),
            title="\u26a0\ufe0f Anti AFK Limit Reached",
            description=(
                f"The hourly action limit ({config.max_actions_per_hour}) "
                f"has been reached. Anti AFK actions are paused until the "
                f"limit resets.\n\n"
                f"If your server needs a higher limit, please contact bot support."
            ),
        )

        try:
            await channel.send(embed=embed)
            self._notif_cooldowns[guild.id] = now_mono
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _notify_permission_error(
        self, guild: discord.Guild, config, member: discord.Member
    ):
        if not config.notification_channelid:
            return

        channel = guild.get_channel(config.notification_channelid)
        if not channel:
            return

        embed = discord.Embed(
            colour=discord.Colour.red(),
            title="\u26a0\ufe0f Anti AFK Permission Error",
            description=(
                f"Could not remove {member.mention} from voice — "
                f"the bot is missing the **Move Members** permission."
            ),
        )

        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

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
from .ui import AntiAfkConfirmView, AntiAfkPersistentView, CUSTOM_ID_PREFIX

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
        'lock',
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
        self.lock = asyncio.Lock()

    def reset_timer(self):
        self.state = CheckState.IDLE
        self.last_check_at = _time.monotonic()
        self.miss_count = 0
        self.dm_fail_count = 0
        self.prompt_delivered = False
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

    # ─── Lifecycle ───────────────────────────────────────────

    async def cog_load(self):
        self.bot.add_view(AntiAfkPersistentView(self.bot))
        self._main_loop_task = asyncio.create_task(self._main_loop())
        logger.info(
            f"AntiAfkCog loaded on shard {self.bot.shard_id}. "
            f"Main loop started."
        )

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

    def _is_channel_applicable(self, channelid: int, config) -> bool:
        targets = config.target_channels_list
        excludes = set(config.exclude_channels_list)

        if channelid in excludes:
            return False
        if targets and channelid not in targets:
            return False
        return True

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

        if not await self._is_premium(guildid):
            return

        config = await self._get_config(guildid)
        if not config or not config.enabled:
            return

        if not self._is_channel_applicable(channel.id, config):
            return

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

    async def handle_confirm(self, guildid: int, userid: int) -> bool:
        guild_users = self._tracked.get(guildid)
        if not guild_users:
            return False

        tu = guild_users.get(userid)
        if not tu:
            return False

        async with tu.lock:
            if tu.state == CheckState.ACTED:
                return False

            tu.reset_timer()
            logger.debug(
                f"Anti AFK confirm: <uid:{userid}> in <gid:{guildid}> "
                f"confirmed presence."
            )
            return True

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
                if not self._is_channel_applicable(channel.id, config):
                    continue
                if self._is_in_pomodoro(channel.id):
                    continue

                for member in channel.members:
                    if member.bot:
                        continue
                    if self._is_blacklisted(member.id):
                        continue
                    if self._has_exempt_role(member, config):
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

        if config.use_dms:
            await self._send_dm_prompts(
                guild, config, users, grace_period_sec, max_warnings,
            )
        else:
            await self._send_vc_text_prompt(
                guild, config, channel, users,
                grace_period_sec, max_warnings,
            )

    async def _send_vc_text_prompt(
        self,
        guild: discord.Guild,
        config,
        channel,
        users: list[TrackedUser],
        grace_period_sec: int,
        max_warnings: int,
    ):
        mentions = ' '.join(f'<@{tu.userid}>' for tu in users)
        warning_text = config.warning_message or "Are you still studying?"

        description_parts = [
            f"{mentions}\n\n{warning_text}",
            f"\nClick the button below within **{config.grace_period} minute{'s' if config.grace_period != 1 else ''}** to confirm.",
        ]

        if max_warnings > 1:
            for tu in users:
                current = tu.miss_count + 1
                if current < max_warnings:
                    description_parts.append(
                        f"\n\u26a0\ufe0f This is check {current} of {max_warnings}."
                    )
                    break

        embed = discord.Embed(
            colour=discord.Colour.gold(),
            title="\U0001f6e1\ufe0f Anti AFK Check",
            description=''.join(description_parts),
        )

        view = AntiAfkConfirmView(self.bot, guild.id, [tu.userid for tu in users])

        try:
            await channel.send(embed=embed, view=view)
            self._record_message_sent()

            for tu in users:
                async with tu.lock:
                    tu.state = CheckState.PENDING
                    tu.last_prompt_sent_at = _time.monotonic()
                    tu.prompt_delivered = True
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
        except discord.HTTPException:
            logger.warning(
                f"Anti AFK: Failed to send VC text prompt in "
                f"<cid:{channel.id}> <gid:{guild.id}>",
                exc_info=True,
            )

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

            embed = discord.Embed(
                colour=discord.Colour.gold(),
                title="\U0001f6e1\ufe0f Anti AFK Check",
                description=desc,
            )
            embed.set_footer(text=f"Server: {guild.name}")

            view = AntiAfkConfirmView(self.bot, guild.id, [tu.userid])

            try:
                await member.send(embed=embed, view=view)
                self._record_message_sent()

                async with tu.lock:
                    tu.state = CheckState.PENDING
                    tu.last_prompt_sent_at = _time.monotonic()
                    tu.prompt_delivered = True
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

        mentions = ' '.join(f'<@{tu.userid}>' for tu in users)
        warning_text = config.warning_message or "Are you still studying?"

        embed = discord.Embed(
            colour=discord.Colour.gold(),
            title="\U0001f6e1\ufe0f Anti AFK Check",
            description=(
                f"{mentions}\n\n{warning_text}\n\n"
                f"Click the button below within "
                f"**{config.grace_period} minutes** to confirm."
            ),
        )

        view = AntiAfkConfirmView(self.bot, guild.id, [tu.userid for tu in users])

        try:
            await channel.send(embed=embed, view=view)
            self._record_message_sent()

            for tu in users:
                async with tu.lock:
                    tu.state = CheckState.PENDING
                    tu.last_prompt_sent_at = _time.monotonic()
                    tu.prompt_delivered = True
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
            await self._notify_permission_error(guild, config, member)
        except discord.HTTPException:
            logger.warning(
                f"Anti AFK: Failed to apply consequence to "
                f"<uid:{tu.userid}> in <gid:{guild.id}>",
                exc_info=True,
            )

        if success:
            tu.state = CheckState.ACTED
            self._record_action(tu.guildid)
            logger.info(
                f"Anti AFK: Applied '{action}' to <uid:{tu.userid}> "
                f"in <gid:{guild.id}> after {tu.miss_count} missed checks."
            )
            await self._send_action_notification(
                guild, config, member, action, tu.miss_count,
            )
            self._remove_user(tu.guildid, tu.userid)

    # ─── Notifications ───────────────────────────────────────

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

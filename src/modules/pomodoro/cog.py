from typing import Optional
from collections import defaultdict
from datetime import datetime, timedelta, date as _date
import asyncio

import discord
from discord.ext import commands as cmds
from discord.ext.commands.errors import CheckFailure
from discord import app_commands as appcmds
import psycopg.errors

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.sharding import THIS_SHARD
from meta.monitor import ComponentMonitor, ComponentStatus, StatusLevel
from utils.lib import utc_now
from utils.ratelimits import limit_concurrency

from wards import low_management_ward

from . import babel, logger
from .data import TimerData
from .lib import TimerRole, FOCUS_MODE_URL, DASHBOARD_SESSION_URL, POMODORO_PRESETS, WEBSITE_BASE_URL
from .settings import TimerSettings
from .settingui import TimerConfigUI
from .timer import Timer
from .options import TimerOptions
from .ui.config import TimerOptionsUI

_p = babel._p

_param_options = {
    'focus_length': (TimerOptions.FocusLength, TimerRole.MANAGER),
    'break_length': (TimerOptions.BreakLength, TimerRole.MANAGER),
    'notification_channel': (TimerOptions.NotificationChannel, TimerRole.ADMIN),
    'inactivity_threshold': (TimerOptions.InactivityThreshold, TimerRole.OWNER),
    'manager_role': (TimerOptions.ManagerRole, TimerRole.ADMIN),
    'voice_alerts': (TimerOptions.VoiceAlerts, TimerRole.OWNER),
    'name': (TimerOptions.BaseName, TimerRole.OWNER),
    'channel_name': (TimerOptions.ChannelFormat, TimerRole.OWNER),
}


class TimerCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(TimerData())
        self.settings = TimerSettings()
        self.monitor = ComponentMonitor('TimerCog', self._monitor)

        self.timer_options = TimerOptions()

        self.ready = False
        self.timers: dict[int, dict[int, Timer]] = defaultdict(dict)
        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Track when members join timer channels for session summaries
        self._session_joins: dict[tuple[int, int], 'datetime'] = {}
        # --- END AI-MODIFIED ---

    async def _monitor(self):
        timers = [timer for tguild in self.timers.values() for timer in tguild.values()]
        state = (
            "<TimerState"
            " loaded={loaded}"
            " guilds={guilds}"
            " members={members}"
            " running={running}"
            " launched={launched}"
            " looping={looping}"
            " locked={locked}"
            " voice_locked={voice_locked}"
            ">"
        )
        data = dict(
            loaded=len(timers),
            guilds=len(set(timer.data.guildid for timer in timers)),
            members=sum(len(timer.members) for timer in timers),
            running=sum(1 for timer in timers if timer.running),
            launched=sum(1 for timer in timers if timer._run_task and not timer._run_task.done()),
            looping=sum(1 for timer in timers if timer._loop_task and not timer._loop_task.done()),
            locked=sum(1 for timer in timers if timer._lock.locked()),
            voice_locked=sum(1 for timer in timers if timer.voice_lock.locked()),
        )
        if not self.ready:
            level = StatusLevel.STARTING
            info = f"(STARTING) Not ready. {state}"
        else:
            level = StatusLevel.OKAY
            info = f"(OK) Ready. {state}"
        return ComponentStatus(level, info, info, data)

    async def cog_load(self):
        self.bot.system_monitor.add_component(self.monitor)
        await self.data.init()

        self.bot.core.guild_config.register_model_setting(self.settings.PomodoroChannel)

        configcog = self.bot.get_cog('ConfigCog')
        self.crossload_group(self.configure_group, configcog.config_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        """
        Detach TimerCog and unload components.

        Clears caches and stops run-tasks for each active timer.
        Does not exist until all timers have completed background tasks.
        """
        timers = [timer for tguild in self.timers.values() for timer in tguild.values()]
        self.timers.clear()

        if timers:
            await self._unload_timers(timers)

    async def cog_check(self, ctx: LionContext):
        if not self.ready:
            raise CheckFailure(
                self.bot.translator.t(_p(
                    'cmd_check:ready|failed',
                    "I am currently restarting! "
                    "The Pomodoro timers will be unavailable until I have restarted. "
                    "Thank you for your patience!"
                ))
            )
        else:
            return True

    @log_wrap(action='Unload Timers')
    async def _unload_timers(self, timers: list[Timer]):
        """
        Unload all active timers.
        """
        tasks = [asyncio.create_task(timer.unload()) for timer in timers]
        for timer, task in zip(timers, tasks):
            try:
                await task
            except Exception:
                logger.exception(
                    f"Unexpected exception while unloading timer {timer!r}"
                )

    async def _load_timers(self, timer_data: list[TimerData.Timer]):
        """
        Factored method to load a list of timers from data rows.
        """
        guildids = set()
        to_delete = []
        to_create = []
        to_unload = []
        for row in timer_data:
            channel = self.bot.get_channel(row.channelid)
            if not channel:
                to_delete.append(row.channelid)
            else:
                guildids.add(row.guildid)
                to_create.append(row)
            if row.guildid in self.timers:
                if row.channelid in self.timers[row.guildid]:
                    to_unload.append(self.timers[row.guildid].pop(row.channelid))

        if to_unload:
            await self._unload_timers(to_unload)

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Guard against CoreCog not being loaded yet during on_ready race
        if guildids:
            core = self.bot.core
            if core is None:
                logger.warning("CoreCog not available during timer load, skipping timer initialization.")
                return
            lguilds = await core.lions.fetch_guilds(*guildids)
        else:
            lguilds = []
        # --- END AI-MODIFIED ---

        now = utc_now()
        to_launch = []
        to_update = []
        timer_reg = defaultdict(dict)
        for row in to_create:
            timer = Timer(self.bot, row, lguilds[row.guildid])
            if timer.running:
                to_launch.append(timer)
            else:
                to_update.append(timer)
            timer_reg[row.guildid][row.channelid] = timer
            timer.last_seen = {member.id: now for member in timer.members}

        # Delete non-existent timers
        if to_delete:
            await self.data.Timer.table.delete_where(channelid=to_delete)
            idstr = ', '.join(map(str, to_delete))
            logger.info(
                f"Destroyed {len(to_delete)} timers with missing voice channels: {idstr}"
            )

        # Re-launch and update running timers
        for timer in to_launch:
            timer.launch()

        coros = [timer.update_status_card() for timer in to_launch]
        if coros:
            i = 0
            async for task in limit_concurrency(coros, 10):
                try:
                    await task
                except discord.HTTPException:
                    timer = to_launch[i]
                    logger.warning(
                        f"Unhandled discord exception while updating timer status for {timer!r}",
                        exc_info=True
                    )
                except Exception:
                    timer = to_launch[i]
                    logger.exception(
                        f"Unexpected exception while updating timer status for {timer!r}",
                        exc_info=True
                    )
                i += 1
        logger.info(
            f"Updated and launched {len(to_launch)} running timers."
        )

        # Update stopped timers
        coros = [timer.update_status_card(render=False) for timer in to_update]
        if coros:
            i = 0
            async for task in limit_concurrency(coros, 10):
                try:
                    await task
                except discord.HTTPException:
                    timer = to_update[i]
                    logger.warning(
                        f"Unhandled discord exception while updating timer status for {timer!r}",
                        exc_info=True
                    )
                except Exception:
                    timer = to_update[i]
                    logger.exception(
                        f"Unexpected exception while updating timer status for {timer!r}",
                        exc_info=True
                    )
                i += 1
        logger.info(
            f"Updated {len(to_update)} stopped timers."
        )

        # Update timer registry
        for gid, gtimers in timer_reg.items():
            self.timers[gid].update(gtimers)

    @LionCog.listener('on_ready')
    @log_wrap(action='Init Timers')
    async def initialise(self):
        """
        Restore timers.
        """
        self.ready = False
        self.timers = defaultdict(dict)
        if self.timers:
            timers = [timer for tguild in self.timers.values() for timer in tguild.values()]
            await self._unload_timers(timers)
            self.timers.clear()

        # Fetch timers in guilds on this shard
        guildids = [guild.id for guild in self.bot.guilds]
        timer_data = await self.data.Timer.fetch_where(guildid=guildids)
        await self._load_timers(timer_data)

        # Ready to handle events
        self.ready = True
        logger.info("Timer system ready to process events.")

    # ----- Event Handlers -----
    @LionCog.listener('on_voice_state_update')
    @log_wrap(action='Timer Voice Events')
    async def timer_voice_events(self, member, before, after):
        if not self.ready:
            # Trust initialise to trigger update status
            return
        if member.bot:
            return

        # If a member is leaving or joining a running timer, trigger a status update
        if before.channel != after.channel:
            leaving = self.get_channel_timer(before.channel.id) if before.channel else None
            joining = self.get_channel_timer(after.channel.id) if after.channel else None

            tasks = []
            if leaving is not None:
                tasks.append(asyncio.create_task(leaving.update_status_card()))
                # --- AI-MODIFIED (2026-03-16) ---
                # Purpose: Send session summary when member leaves a running timer
                tasks.append(asyncio.create_task(
                    self._send_leave_summary(member, leaving)
                ))
                # --- END AI-MODIFIED ---
            if joining is not None:
                joining.last_seen[member.id] = utc_now()
                # --- AI-MODIFIED (2026-03-16) ---
                # Purpose: Track member join time for session summary
                self._session_joins[(joining.data.channelid, member.id)] = utc_now()
                # --- END AI-MODIFIED ---
                if not joining.running and joining.auto_restart:
                    tasks.append(asyncio.create_task(joining.start()))
                else:
                    tasks.append(asyncio.create_task(joining.update_status_card()))

            # --- AI-MODIFIED (2026-03-18) ---
            # Purpose: Premium hooks as fire-and-forget background tasks (auto-role, economy, gamification)
            if leaving is not None:
                asyncio.create_task(self._premium_on_leave(member, leaving))
            if joining is not None:
                asyncio.create_task(self._premium_on_join(member, joining))
            # --- END AI-MODIFIED ---

            if tasks:
                try:
                    await asyncio.gather(*tasks)
                except Exception:
                    logger.exception(
                        "Exception occurred while handling timer voice event. "
                        f"Leaving: {leaving!r} "
                        f"Joining: {joining!r}"
                    )

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Send a session summary when a member leaves a pomodoro timer
    async def _send_leave_summary(self, member: discord.Member, timer: Timer):
        try:
            if not timer.running or timer.destroyed:
                return

            # --- AI-MODIFIED (2026-03-25) ---
            # Purpose: Respect guild toggle for session leave summaries (default off)
            if not timer.lguild.data.session_leave_summary:
                return
            # --- END AI-MODIFIED ---

            join_key = (timer.data.channelid, member.id)
            join_time = self._session_joins.pop(join_key, None)
            if join_time is None:
                return

            now = utc_now()
            duration_seconds = (now - join_time).total_seconds()
            min_duration = timer.data.focus_length
            if duration_seconds < min_duration:
                return

            interval = timer.data.focus_length + timer.data.break_length
            cycles_completed = int(duration_seconds // interval)

            hours = int(duration_seconds) // 3600
            minutes = (int(duration_seconds) % 3600) // 60
            if hours > 0:
                duration_str = f"**{hours}h {minutes}m**"
            else:
                duration_str = f"**{minutes}m**"

            t = self.bot.translator.t
            description = t(_p(
                'timer|leave_summary|desc',
                "Great session, {mention}! You were productive for {duration} and completed "
                "**{cycles}** focus cycle(s). Keep it up!"
            )).format(
                mention=member.mention,
                duration=duration_str,
                cycles=cycles_completed
            )

            embed = discord.Embed(
                colour=discord.Colour.green(),
                description=description
            )

            link_view = discord.ui.View()
            link_view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=DASHBOARD_SESSION_URL,
                label="Continue on the web"
            ))

            notify_hook = await timer.get_notification_webhook()
            if notify_hook:
                await notify_hook.send(embed=embed, view=link_view)
        except discord.HTTPException:
            logger.debug(
                f"Failed to send leave summary for member {member.id} in timer {timer!r}"
            )
        except Exception:
            logger.exception(
                f"Unexpected error sending leave summary for member {member.id} in timer {timer!r}"
            )
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-18) ---
    # Purpose: Premium on-leave and on-join handlers (auto-role, focus power reset, economy bonus)
    async def _premium_on_leave(self, member: discord.Member, timer: Timer):
        try:
            if not await timer._check_premium():
                return

            config = await timer.premium_config()
            if config and config.focus_roleid:
                try:
                    role = member.guild.get_role(config.focus_roleid)
                    if role and role in member.roles:
                        await member.remove_roles(role, reason="Left pomodoro timer")
                except discord.Forbidden:
                    logger.debug(f"Missing MANAGE_ROLES for focus role removal in guild {timer.data.guildid}")
                except Exception:
                    logger.debug(f"Focus role removal failed for {member.id}, non-critical")

            stage = timer.current_stage
            if stage and stage.focused:
                try:
                    from .gamification import reset_focus_power
                    await reset_focus_power(self.bot, member.id)
                except Exception:
                    logger.debug(f"Focus power reset failed for {member.id}, non-critical")

            join_key = (timer.data.channelid, member.id)
            join_time = self._session_joins.get(join_key)
            if join_time:
                session_minutes = (utc_now() - join_time).total_seconds() / 60
                await self._apply_focus_bonus(member, timer, session_minutes)
                await self._apply_liongotchi_bonus(member, timer, session_minutes)

                # --- AI-MODIFIED (2026-04-06) ---
                # Purpose: Respect guild-level session_leave_summary as master switch.
                # If the guild toggle is OFF, skip premium summaries too,
                # so admins have one clear way to disable all session messages.
                guild_summaries_enabled = getattr(timer.lguild.data, 'session_leave_summary', True)
                if config and config.session_summary and guild_summaries_enabled:
                # --- END AI-MODIFIED ---
                    try:
                        from .summary import generate_individual_summary, send_summary_embed
                        summary = await generate_individual_summary(
                            self.bot, timer, member.id, session_minutes, session_minutes * 0.7
                        )
                        if summary:
                            notif_channel = timer.notification_channel
                            if notif_channel:
                                await send_summary_embed(self.bot, notif_channel.id, summary)
                    except Exception:
                        logger.debug(f"Premium session summary failed for {member.id}, non-critical")
        except Exception:
            logger.debug(f"Premium leave handler failed for {member.id}, non-critical")

    async def _premium_on_join(self, member: discord.Member, timer: Timer):
        try:
            if not await timer._check_premium():
                return

            config = await timer.premium_config()
            stage = timer.current_stage
            if config and config.focus_roleid and stage and stage.focused:
                try:
                    role = member.guild.get_role(config.focus_roleid)
                    if role and role not in member.roles:
                        await member.add_roles(role, reason="Joined pomodoro timer during focus")
                except discord.Forbidden:
                    logger.debug(f"Missing MANAGE_ROLES for focus role add in guild {timer.data.guildid}")
                except Exception:
                    logger.debug(f"Focus role add failed for {member.id}, non-critical")
        except Exception:
            logger.debug(f"Premium join handler failed for {member.id}, non-critical")

    async def _apply_focus_bonus(self, member: discord.Member, timer: Timer, session_minutes: float):
        try:
            if not await timer._check_premium():
                return
            config = await timer.premium_config()
            if not config or not config.coin_multiplier:
                return

            from .gamification import get_streak_data, get_focus_power_multiplier
            streak = await get_streak_data(self.bot, member.id)
            fp_mult = get_focus_power_multiplier(streak.get('focus_power', 0))

            guild_config = await self.bot.core.data.Guild.fetch(timer.data.guildid)
            coins_per_centixp = getattr(guild_config, 'coins_per_centixp', None) or 100
            base_coins = int((session_minutes / 60) * coins_per_centixp * 0.01)
            bonus = int(base_coins * 0.5 * fp_mult)
            bonus = min(bonus, 1000)

            if bonus > 0:
                connector = self.data.Timer.table.connector
                async with connector.connection() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            "INSERT INTO coin_transactions (guildid, userid, amount, bonus, from_account) "
                            "VALUES (%s, %s, %s, TRUE, FALSE)",
                            (timer.data.guildid, member.id, bonus)
                        )
                logger.debug(f"Awarded {bonus} pomodoro bonus coins to {member.id}")
        except Exception:
            logger.debug(f"Focus bonus failed for {member.id}, non-critical")

    async def _apply_liongotchi_bonus(self, member: discord.Member, timer: Timer, session_minutes: float):
        try:
            lg_cog = self.bot.get_cog('LionGotchiCog')
            if not lg_cog or not await timer._check_premium():
                return
            if hasattr(lg_cog, 'apply_pomodoro_bonus'):
                await lg_cog.apply_pomodoro_bonus(member.id, timer.data.guildid, session_minutes)
        except Exception:
            logger.debug(f"LionGotchi pomodoro bonus failed for {member.id}, non-critical")
    # --- END AI-MODIFIED ---

    @LionCog.listener('on_guild_remove')
    @log_wrap(action='Unload Guild Timers')
    async def _unload_guild_timers(self, guild: discord.Guild):
        """
        When we leave a guild, perform an unload for all timers in the Guild.
        """
        if not self.ready:
            # Trust initialiser to ignore the guild
            return

        timers = self.timers.pop(guild.id, {})
        tasks = []
        for timer in timers.values():
            tasks.append(asyncio.create_task(timer.unload()))
        if tasks:
            try:
                await asyncio.gather(*tasks)
            except Exception:
                logger.warning(
                    "Exception occurred while unloading timers for removed guild.",
                    exc_info=True
                )
        logger.info(
            f"Unloaded {len(timers)} from removed guild <gid: {guild.id}>."
        )

    @LionCog.listener('on_guild_join')
    @log_wrap(action='Load Guild Timers')
    async def _load_guild_timers(self, guild: discord.Guild):
        """
        When we join a guild, reload any saved timers for this guild.
        """
        timer_data = await self.data.Timer.fetch_where(guildid=guild.id)
        if timer_data:
            await self._load_timers(timer_data)

    @LionCog.listener('on_guild_channel_delete')
    @log_wrap(action='Destroy Channel Timer')
    async def _destroy_channel_timer(self, channel: discord.abc.GuildChannel):
        """
        If a voice channel with a timer was deleted, destroy the timer.
        """
        # --- AI-MODIFIED (2026-03-27) ---
        # Purpose: Pass guild_id to bypass unreliable bot.get_channel cache lookup
        timer = self.get_channel_timer(channel.id, guild_id=channel.guild.id)
        # --- END AI-MODIFIED ---
        if timer is not None:
            await timer.destroy(reason="Voice Channel Deleted")

    @LionCog.listener('on_guildset_pomodoro_channel')
    @log_wrap(action='Update Pomodoro Channels')
    async def _update_pomodoro_channels(self, guildid: int, setting: TimerSettings.PomodoroChannel):
        """
        Request a send_status for all guild timers which need to move channel.
        """
        timers = self.get_guild_timers(guildid).values()
        tasks = []
        for timer in timers:
            current_channel = timer.notification_channel
            current_hook = timer._hook
            if current_channel and (not current_hook or current_hook.channelid != current_channel.id):
                tasks.append(asyncio.create_task(timer.send_status()))

        if tasks:
            try:
                await asyncio.gather(*tasks)
            except Exception:
                logger.warning(
                    "Exception occurred which refreshing status for timers with new notification_channel.",
                    exc_info=True
                )

    # ----- Timer API -----
    def get_guild_timers(self, guildid: int) -> dict[int, Timer]:
        """
        Get all timers in the given guild as a map channelid -> Timer.
        """
        return self.timers[guildid]

    # --- AI-REPLACED (2026-03-27) ---
    # Reason: bot.get_channel() can miss the Discord cache, returning None even when
    #   the timer exists in self.timers. This caused false negatives allowing duplicate INSERTs.
    # What the new code does better: accepts an optional guild_id to bypass the unreliable cache lookup.
    # --- Original code (commented out for rollback) ---
    # def get_channel_timer(self, channelid: int) -> Optional[Timer]:
    #     """
    #     Get the timer bound to the given channel, or None if it does not exist.
    #     """
    #     channel = self.bot.get_channel(channelid)
    #     if channel:
    #         return self.timers[channel.guild.id].get(channelid, None)
    # --- End original code ---
    def get_channel_timer(self, channelid: int, guild_id: int = None) -> Optional[Timer]:
        """
        Get the timer bound to the given channel, or None if it does not exist.
        """
        if guild_id is not None:
            return self.timers[guild_id].get(channelid, None)
        channel = self.bot.get_channel(channelid)
        if channel:
            return self.timers[channel.guild.id].get(channelid, None)
        return None
    # --- END AI-REPLACED ---

    async def create_timer(self, **kwargs):
        timer_data = await self.data.Timer.create(**kwargs)
        lguild = await self.bot.core.lions.fetch_guild(timer_data.guildid)
        timer = Timer(self.bot, timer_data, lguild)
        self.timers[timer_data.guildid][timer_data.channelid] = timer

        return timer

    async def destroy_timer(self, timer: Timer, **kwargs):
        """
        Destroys the provided timer and removes it from the registry.
        """
        self.timers[timer.data.guildid].pop(timer.data.channelid, None)
        await timer.destroy(**kwargs)

    # ----- Timer Commands -----

    # -- User Display Commands --
    @cmds.hybrid_command(
        name=_p('cmd:timer', "timer"),
        description=_p('cmd:timer|desc', "Show your current (or selected) pomodoro timer.")
    )
    @appcmds.rename(
        channel=_p('cmd:timer|param:channel', "timer_channel")
    )
    @appcmds.describe(
        channel=_p(
            'cmd:timer|param:channel|desc',
            "Select a timer to display (by selecting the timer voice channel)"
        )
    )
    @cmds.guild_only()
    async def cmd_timer(self, ctx: LionContext,
                        channel: Optional[discord.VoiceChannel] = None):
        t = self.bot.translator.t

        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        timers: list[Timer] = list(self.get_guild_timers(ctx.guild.id).values())
        error: Optional[discord.Embed] = None

        if not timers:
            # Guild has no timers
            error = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:timer|error:no_timers|desc',
                    "**This server has no timers set up!**\n"
                    "Ask an admin to set up and configure a timer with {create_cmd} first, "
                    "or rent a private room with {room_cmd} and create one yourself!"
                )).format(create_cmd=self.bot.core.mention_cmd('pomodoro create'),
                          room_cmd=self.bot.core.mention_cmd('rooms rent'))
            )
        elif channel is None:
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
            else:
                error = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=t(_p(
                        'cmd:timer|error:no_channel|desc',
                        "**I don't know what timer to show you.**\n"
                        "No channel selected and you are not in a voice channel! "
                        "Use {timers_cmd} to list the available timers in this server."
                    )).format(timers_cmd=self.bot.core.mention_cmd('timers'))
                )

        if channel is not None:
            # --- AI-MODIFIED (2026-03-27) ---
            # Purpose: Pass guild_id to bypass unreliable bot.get_channel cache lookup
            timer = self.get_channel_timer(channel.id, guild_id=channel.guild.id)
            # --- END AI-MODIFIED ---
            if timer is None:
                error = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=t(_p(
                        'cmd:timer|error:no_timer_in_channel',
                        "The channel {channel} is not a pomodoro timer room!\n"
                        "Use {timers_cmd} to list the available timers in this server."
                    )).format(
                        channel=channel.mention,
                        timers_cmd=self.bot.core.mention_cmd('timers')
                    )
                )
            else:
                # Display the timer status ephemerally
                await ctx.interaction.response.defer(thinking=True, ephemeral=True)
                status = await timer.current_status(with_notify=False, with_warnings=False)
                await ctx.interaction.edit_original_response(**status.edit_args)

        if error is not None:
            await ctx.reply(embed=error, ephemeral=True)

    @cmds.hybrid_command(
        name=_p('cmd:timers', "timers"),
        description=_p('cmd:timers|desc', "List the available pomodoro timer rooms.")
    )
    @cmds.guild_only()
    async def cmd_timers(self, ctx: LionContext):
        t = self.bot.translator.t

        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        timers = list(self.get_guild_timers(ctx.guild.id).values())

        # Extra filter here to exclude owned timers, but include ones the author is a member of
        visible_timers = [
            timer for timer in timers
            if timer.channel and timer.channel.permissions_for(ctx.author).connect
            and (not timer.owned or (ctx.author in timer.channel.overwrites))
        ]

        if not timers:
            # No timers in the guild
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:timer|error:no_timers|desc',
                    "**This server has no timers set up!**\n"
                    "Ask an admin to set up and configure a timer with {create_cmd} first, "
                    "or rent a private room with {room_cmd} and create one yourself!"
                )).format(create_cmd=self.bot.core.mention_cmd('pomodoro create'),
                          room_cmd=self.bot.core.mention_cmd('rooms rent'))
            )
            await ctx.reply(embed=embed, ephemeral=True)
        elif not visible_timers:
            # Timers exist, but the member can't see any
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:timer|error:no_visible_timers|desc',
                    "**There are no available pomodoro timers!**\n"
                    "Ask an admin to set up a new timer with {create_cmd}, "
                    "or rent a private room with {room_cmd} and create one yourself!"
                )).format(create_cmd=self.bot.core.mention_cmd('pomodoro create'),
                          room_cmd=self.bot.core.mention_cmd('rooms rent'))
            )
            await ctx.reply(embed=embed, ephemeral=True)
        else:
            # Timers exist and are visible!
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                title=t(_p(
                    'cmd:timers|embed:timer_list|title',
                    "Pomodoro Timer Rooms in **{guild}**"
                )).format(guild=ctx.guild.name),
            )
            for timer in visible_timers:
                stage = timer.current_stage
                if stage is None:
                    if timer.auto_restart:
                        lazy_status = _p(
                            'cmd:timers|status:stopped_auto',
                            "`{pattern}` timer is stopped with no members!\n"
                            "Join {channel} to restart it."
                        )
                    else:
                        lazy_status = _p(
                            'cmd:timers|status:stopped_manual',
                            "`{pattern}` timer is stopped with `{members}` members!\n"
                            "Join {channel} and press `Start` to start it!"
                        )
                else:
                    if stage.focused:
                        lazy_status = _p(
                            'cmd:timers|status:running_focus',
                            "`{pattern}` timer is running with `{members}` members!\n"
                            "Currently **focusing**, with break starting {timestamp}"
                        )
                    else:
                        lazy_status = _p(
                            'cmd:timers|status:running_break',
                            "`{pattern}` timer is running with `{members}` members!\n"
                            "Currently **resting**, with focus starting {timestamp}"
                        )
                status = t(lazy_status).format(
                    pattern=timer.pattern,
                    channel=timer.channel.mention,
                    members=len(timer.members),
                    timestamp=f"<t:{int(stage.end.timestamp())}:R>" if stage else None
                )
                embed.add_field(name=timer.channel.mention, value=status, inline=False)
            # --- AI-MODIFIED (2026-03-16) ---
            # Purpose: Add website link buttons to timer list response
            link_view = discord.ui.View()
            link_view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=FOCUS_MODE_URL,
                label="Focus Mode"
            ))
            link_view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=DASHBOARD_SESSION_URL,
                label="Dashboard"
            ))
            await ctx.reply(embed=embed, view=link_view, ephemeral=False)
            # --- END AI-MODIFIED ---

    # -- Admin Commands --
    @cmds.hybrid_group(
        name=_p('cmd:pomodoro', "pomodoro"),
        description=_p('cmd:pomodoro|desc', "Create and configure pomodoro timer rooms.")
    )
    @cmds.guild_only()
    async def pomodoro_group(self, ctx: LionContext):
        ...

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Add preset parameter and make focus/break optional for quick-start
    @pomodoro_group.command(
        name=_p('cmd:pomodoro_create', "create"),
        description=_p(
            'cmd:pomodoro_create|desc',
            "Create a new Pomodoro timer. Requires manage channel permissions."
        )
    )
    @appcmds.rename(
        channel=_p('cmd:pomodoro_create|param:channel', "timer_channel"),
        preset=_p('cmd:pomodoro_create|param:preset', "preset"),
        **{param: option._display_name for param, (option, _) in _param_options.items()}
    )
    @appcmds.describe(
        channel=_p(
            'cmd:pomodoro_create|param:channel|desc',
            "Voice channel to create the timer in. (Defaults to your current channel, or makes a new one.)"
        ),
        preset=_p(
            'cmd:pomodoro_create|param:preset|desc',
            "Quick-start preset. Overridden by explicit focus/break values."
        ),
        **{param: option._desc for param, (option, _) in _param_options.items()}
    )
    @appcmds.choices(preset=[
        appcmds.Choice(name="Classic (25/5)", value="classic"),
        appcmds.Choice(name="Long Focus (50/10)", value="long_focus"),
        appcmds.Choice(name="Short Sprint (15/3)", value="short_sprint"),
        appcmds.Choice(name="Lecture (45/10)", value="lecture"),
    ])
    async def cmd_pomodoro_create(self, ctx: LionContext,
                                  channel: Optional[discord.VoiceChannel] = None,
                                  preset: Optional[appcmds.Choice[str]] = None,
                                  focus_length: Optional[appcmds.Range[int, 1, 24*60]] = None,
                                  break_length: Optional[appcmds.Range[int, 1, 24*60]] = None,
                                  notification_channel: Optional[discord.TextChannel | discord.VoiceChannel] = None,
                                  inactivity_threshold: Optional[appcmds.Range[int, 0, 127]] = None,
                                  manager_role: Optional[discord.Role] = None,
                                  voice_alerts: Optional[bool] = None,
                                  name: Optional[appcmds.Range[str, 0, 100]] = None,
                                  channel_name: Optional[appcmds.Range[str, 0, 100]] = None,
                                  ):
    # --- END AI-MODIFIED ---
        t = self.bot.translator.t

        # Type guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Resolve focus/break from preset when not explicitly provided
        preset_value = preset.value if isinstance(preset, appcmds.Choice) else preset
        if preset_value and preset_value in POMODORO_PRESETS:
            preset_focus, preset_break = POMODORO_PRESETS[preset_value]
            if focus_length is None:
                focus_length = preset_focus
            if break_length is None:
                break_length = preset_break

        if focus_length is None or break_length is None:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:pomodoro_create|error:no_lengths',
                    "Please provide a **preset** or explicit **focus_length** and **break_length** values!"
                ))
            )
            await ctx.reply(embed=embed, ephemeral=True)
            return
        # --- END AI-MODIFIED ---

        # Get private room if applicable
        room_cog = self.bot.get_cog('RoomCog')
        if room_cog is None:
            logger.warning("Running pomodoro create without private room cog loaded!")
            private_room = None
        else:
            rooms = room_cog.get_rooms(ctx.guild.id, ctx.author.id)
            cid = next((cid for cid, room in rooms.items() if room.data.ownerid == ctx.author.id), None)
            private_room = ctx.guild.get_channel(cid) if cid is not None else None

        # If a voice channel was not given, attempt to resolve it or make one
        if channel is None:
            # Resolving order: command channel, author voice channel, new channel
            if ctx.channel.type is discord.ChannelType.voice:
                channel = ctx.channel
            elif ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
            elif not ctx.author.guild_permissions.manage_channels:
                embed = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'cmd:pomodoro_create|new_channel|error:your_insufficient_perms|title',
                        "Could not create pomodoro voice channel!"
                    )),
                    description=t(_p(
                        'cmd:pomodoro_create|new_channel|error:your_insufficient_perms',
                        "No `timer_channel` was provided, and you lack the 'Manage Channels` permission "
                        "required to create a new timer room!"
                    ))
                )
                await ctx.reply(embed=embed, ephemeral=True)
            elif not ctx.guild.me.guild_permissions.manage_channels:
                # Error
                embed = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'cmd:pomodoro_create|new_channel|error:my_insufficient_perms|title',
                        "Could not create pomodoro voice channel!"
                    )),
                    description=t(_p(
                        'cmd:pomodoro_create|new_channel|error:my_insufficient_perms|desc',
                        "No `timer_channel` was provided, and I lack the 'Manage Channels' permission "
                        "required to create a new voice channel."
                    ))
                )
                await ctx.reply(embed=embed, ephemeral=True)
            else:
                # Attempt to create new channel in current category
                try:
                    channel = await ctx.guild.create_voice_channel(
                        name=name or t(_p(
                            'cmd:pomodoro_create|new_channel|default_name',
                            "Timer"
                        )),
                        reason=t(_p(
                            'cmd:pomodoro_create|new_channel|audit_reason',
                            "Creating Pomodoro Voice Channel"
                        )),
                        category=ctx.channel.category
                    )
                except discord.HTTPException:
                    embed = discord.Embed(
                        colour=discord.Colour.brand_red(),
                        title=t(_p(
                            'cmd:pomodoro_create|new_channel|error:channel_create_failed|title',
                            "Could not create pomodoro voice channel!"
                        )),
                        description=t(_p(
                            'cmd:pomodoro_create|new_channel|error:channel_create_failed|desc',
                            "Failed to create a new pomodoro voice channel due to an unknown "
                            "Discord communication error. "
                            "Please try creating the channel manually and pass it to the "
                            "`timer_channel` argument of this command."
                        ))
                    )
                    await ctx.reply(embed=embed, ephemeral=True)

        if not channel:
            # Already handled the creation error
            pass
        # --- AI-MODIFIED (2026-03-27) ---
        # Purpose: Pass guild_id to bypass unreliable bot.get_channel cache lookup
        elif (self.get_channel_timer(channel.id, guild_id=channel.guild.id)) is not None:
        # --- END AI-MODIFIED ---
            # A timer already exists in the resolved channel
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:pomodoro_create|add_timer|error:timer_exists',
                    "A timer already exists in {channel}! "
                    "Reconfigure it with {edit_cmd}."
                )).format(
                    channel=channel.mention,
                    edit_cmd=self.bot.core.mention_cmd('pomodoro edit')
                )
            )
            await ctx.reply(embed=embed, ephemeral=True)
        elif not channel.permissions_for(ctx.author).manage_channels:
            # Note that this takes care of private room owners as well
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:pomodoro_create|add_timer|error:your_insufficient_perms',
                    "You must have the 'Manage Channel' permission in {channel} "
                    "in order to add a timer there!"
                ))
            )
            await ctx.reply(embed=embed, ephemeral=True)
        else:
            # Finally, we are sure they can create a timer here
            # Build the creation arguments from the rest of the provided args
            provided = {
                'focus_length': focus_length * 60,
                'break_length': break_length * 60,
                'inactivity_threshold': inactivity_threshold,
                'voice_alerts': voice_alerts,
                'name': name or channel.name,
                'channel_name': channel_name or None,
            }
            create_args = {'channelid': channel.id, 'guildid': channel.guild.id}

            owned = (private_room and (channel == private_room))
            if owned:
                provided['manager_role'] = manager_role or ctx.guild.default_role
                create_args['notification_channelid'] = channel.id
                create_args['ownerid'] = ctx.author.id
            else:
                provided['notification_channel'] = notification_channel
                provided['manager_role'] = manager_role

            for param, value in provided.items():
                if value is not None:
                    setting, _ = _param_options[param]
                    create_args[setting._column] = setting._data_from_value(channel.id, value)

            # Permission checks and input checking done
            await ctx.interaction.response.defer(thinking=True)

            # --- AI-MODIFIED (2026-03-27) ---
            # Purpose: Catch DB-level duplicate key if timer exists in DB but not in memory,
            #   and recover state by loading the orphan timer into self.timers
            # What the new code does better: after catching UniqueViolation, fetches the
            #   existing timer from DB and loads it into memory so /pomodoro edit works
            # --- Original code (commented out for rollback) ---
            # # --- AI-MODIFIED (2026-03-22) ---
            # try:
            #     timer = await self.create_timer(**create_args)
            # except psycopg.errors.UniqueViolation:
            #     logger.warning(
            #         "UniqueViolation creating timer for channel %s (guild %s) -- already exists in DB",
            #         channel.id, channel.guild.id
            #     )
            #     embed = discord.Embed(
            #         colour=discord.Colour.brand_red(),
            #         description=t(_p(
            #             'cmd:pomodoro_create|add_timer|error:timer_exists',
            #             "A timer already exists in {channel}! "
            #             "Reconfigure it with {edit_cmd}."
            #         )).format(
            #             channel=channel.mention,
            #             edit_cmd=self.bot.core.mention_cmd('pomodoro edit')
            #         )
            #     )
            #     await ctx.interaction.followup.send(embed=embed, ephemeral=True)
            #     return
            # # --- END AI-MODIFIED ---
            # --- End original code ---
            try:
                timer = await self.create_timer(**create_args)
            except psycopg.errors.UniqueViolation:
                logger.warning(
                    "UniqueViolation creating timer for channel %s (guild %s) -- already exists in DB",
                    channel.id, channel.guild.id
                )
                try:
                    existing = await self.data.Timer.fetch_where(channelid=channel.id)
                    if existing:
                        await self._load_timers(existing)
                except Exception:
                    logger.warning(
                        "Failed to recover orphan timer for channel %s", channel.id, exc_info=True
                    )
                embed = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=t(_p(
                        'cmd:pomodoro_create|add_timer|error:timer_exists',
                        "A timer already exists in {channel}! "
                        "Reconfigure it with {edit_cmd}."
                    )).format(
                        channel=channel.mention,
                        edit_cmd=self.bot.core.mention_cmd('pomodoro edit')
                    )
                )
                await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                return
            # --- END AI-MODIFIED ---

            # Start timer
            await timer.start()

            # Ack with a config UI
            ui = TimerOptionsUI(
                self.bot, timer, TimerRole.ADMIN if not owned else TimerRole.OWNER, callerid=ctx.author.id
            )
            await ui.run(
                ctx.interaction,
                content=t(_p(
                    'cmd:pomodoro_create|response:success|content',
                    "Timer created successfully! Use the panel below to reconfigure."
                ))
            )
            await ui.wait()

    @pomodoro_group.command(
        name=_p('cmd:pomodoro_destroy', "destroy"),
        description=_p(
            'cmd:pomodoro_destroy|desc',
            "Remove a pomodoro timer from a voice channel."
        )
    )
    @appcmds.rename(
        channel=_p('cmd:pomodoro_destroy|param:channel', "timer_channel"),
    )
    @appcmds.describe(
        channel=_p('cmd:pomodoro_destroy|param:channel', "Select a timer voice channel to remove the timer from."),
    )
    async def cmd_pomodoro_delete(self, ctx: LionContext, channel: discord.VoiceChannel):
        t = self.bot.translator.t

        # Type guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # Check the timer actually exists
        # --- AI-MODIFIED (2026-03-27) ---
        # Purpose: Pass guild_id to bypass unreliable bot.get_channel cache lookup
        timer = self.get_channel_timer(channel.id, guild_id=channel.guild.id)
        # --- END AI-MODIFIED ---
        if timer is None:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:pomodoro_destroy|error:no_timer',
                    "This channel doesn't have an attached pomodoro timer!"
                ))
            )
            await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Check the user has sufficient permissions to delete the timer
        timer_role = timer.get_member_role(ctx.author)
        if timer.owned and timer_role < TimerRole.OWNER:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:pomodoro_destroy|error:insufficient_perms|owned',
                    "You need to be an administrator or own this channel to remove this timer!"
                ))
            )
            await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
        elif timer_role is not TimerRole.ADMIN and not channel.permissions_for(ctx.author).manage_channels:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:pomodoro_destroy|error:insufficient_perms|notowned',
                    "You need to have the `Manage Channels` permission in {channel} to remove this timer!"
                )).format(channel=channel.mention)
            )
            await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.interaction.response.defer(thinking=True)
            await self.destroy_timer(timer, reason="Deleted by command")
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:pomdoro_destroy|response:success|description',
                    "Timer successfully removed from {channel}."
                )).format(channel=channel.mention)
            )
            await ctx.interaction.edit_original_response(embed=embed)

    @pomodoro_group.command(
        name=_p('cmd:pomodoro_edit', "edit"),
        description=_p(
            'cmd:pomodoro_edit|desc',
            "Reconfigure a pomodoro timer."
        )
    )
    @appcmds.rename(
        channel=_p('cmd:pomodoro_edit|param:channel', "timer_channel"),
        **{param: option._display_name for param, (option, _) in _param_options.items()}
    )
    @appcmds.describe(
        channel=_p(
            'cmd:pomodoro_edit|param:channel|desc',
            "Select a timer voice channel to reconfigure."
        ),
        **{param: option._desc for param, (option, _) in _param_options.items()}
    )
    async def cmd_pomodoro_edit(self, ctx: LionContext,
                                channel: discord.VoiceChannel,
                                focus_length: Optional[appcmds.Range[int, 1, 24*60]] = None,
                                break_length: Optional[appcmds.Range[int, 1, 24*60]] = None,
                                notification_channel: Optional[discord.TextChannel | discord.VoiceChannel] = None,
                                inactivity_threshold: Optional[appcmds.Range[int, 0, 127]] = None,
                                manager_role: Optional[discord.Role] = None,
                                voice_alerts: Optional[bool] = None,
                                name: Optional[appcmds.Range[str, 0, 100]] = None,
                                channel_name: Optional[appcmds.Range[str, 0, 100]] = None,
                                ):
        t = self.bot.translator.t
        provided = {
            'focus_length': focus_length * 60 if focus_length else None,
            'break_length': break_length * 60 if break_length else None,
            'notification_channel': notification_channel,
            'inactivity_threshold': inactivity_threshold,
            'manager_role': manager_role,
            'voice_alerts': voice_alerts,
            'name': name or None,
            'channel_name': channel_name or None,
        }
        modified = set(param for param, value in provided.items() if value is not None)

        # Type guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # Check the timer actually exists
        # --- AI-MODIFIED (2026-03-27) ---
        # Purpose: Pass guild_id to bypass unreliable bot.get_channel cache lookup
        timer = self.get_channel_timer(channel.id, guild_id=channel.guild.id)
        # --- END AI-MODIFIED ---
        if timer is None:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:pomodoro_edit|error:no_timer',
                    "This channel doesn't have an attached pomodoro timer to edit!"
                ))
            )
            await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Check that the author has sufficient permissions to update the timer at all
        timer_role = timer.get_member_role(ctx.author)
        if timer_role is TimerRole.OTHER:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:pomodoro_edit|error:insufficient_perms|role:other',
                    "Insufficient permissions to modifiy this timer!\n"
                    "You need to be a server administrator, own this channel, or have the timer manager role."
                ))
            )
            await ctx.reply(embed=embed, ephemeral=True)
            return

        # Check that the author has sufficient permissions to modify the requested items
        # And build the list of arguments to write
        update_args = {}
        for param in modified:
            setting, required = _param_options[param]
            # --- AI-MODIFIED (2026-04-23) ---
            # Reason: Bug Report #0041 -- a mod with Manage Channels could create a
            # pomodoro timer with ANY parameter (focus/break/voice_alerts/name/etc.),
            # but /pomodoro edit blocked them from changing those same settings later
            # because most params required OWNER (and OWNER falls back to ADMIN on
            # unowned guild timers). This caused user-visible asymmetry between
            # /pomodoro create and /pomodoro edit.
            # What the new code does better: For UNOWNED timers (regular guild VC
            # pomodoros where ownerid is NULL) we collapse the requirement down to
            # MANAGER, matching the only check /pomodoro create performs (channel
            # Manage Channels permission). Owned timers (private study rooms) keep
            # the original stricter OWNER/ADMIN requirements so room owners are not
            # overridden by random mods.
            if not timer.owned and required > TimerRole.MANAGER:
                required = TimerRole.MANAGER
            # --- END AI-MODIFIED ---
            if timer_role < required:
                if required is TimerRole.OWNER and not timer.owned:
                    required = TimerRole.ADMIN
                elif required is TimerRole.MANAGER and timer.data.manager_roleid is None:
                    required = TimerRole.ADMIN

                if required is TimerRole.ADMIN:
                    error = t(_p(
                        'cmd:pomodoro_edit|error:insufficient_permissions|role_needed:admin',
                        "You need to be a guild admin to modify this option!"
                    ))
                elif required is TimerRole.OWNER:
                    error = t(_p(
                        'cmd:pomodoro_edit|error:insufficient_permissions|role_needed:owner',
                        "You need to be a channel owner or guild admin to modify this option!"
                    ))
                elif required is TimerRole.MANAGER:
                    error = t(_p(
                        'cmd:pomodoro_edit|error:insufficient_permissions|role_needed:manager',
                        "You need to be a guild admin or have the manager role to modify this option!"
                    ))

                embed = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=error
                )
                await ctx.reply(embed=embed, ephemeral=True)
                return
            update_args[setting._column] = setting._data_from_value(channel.id, provided[param])

        await ctx.interaction.response.defer(thinking=True)

        if update_args:
            # Update the timer data
            await timer.data.update(**update_args)
            # Regenerate or refresh the timer
            if ('focus_length' in modified) or ('break_length' in modified):
                await timer.start()
            elif ('notification_channel' in modified):
                await timer.send_status()
            else:
                await timer.update_status_card()

        # Show the config UI
        ui = TimerOptionsUI(self.bot, timer, timer_role, callerid=ctx.author.id)
        await ui.run(ctx.interaction)
        await ui.wait()

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Add /pomodoro stats command for personal and server study statistics
    @pomodoro_group.command(
        name=_p('cmd:pomodoro_stats', "stats"),
        description=_p('cmd:pomodoro_stats|desc', "View your Pomodoro productivity statistics.")
    )
    @appcmds.describe(
        server=_p(
            'cmd:pomodoro_stats|param:server|desc',
            "Show server-wide stats instead of personal stats (admin only)."
        )
    )
    async def cmd_pomodoro_stats(self, ctx: LionContext,
                                 server: Optional[bool] = False):
        t = self.bot.translator.t

        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        connector = self.data.Timer.table.connector

        def format_duration(seconds):
            if seconds is None or seconds <= 0:
                return "0m"
            hours = int(seconds) // 3600
            minutes = (int(seconds) % 3600) // 60
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"

        try:
            if server:
                if not ctx.author.guild_permissions.administrator:
                    embed = discord.Embed(
                        colour=discord.Colour.brand_red(),
                        description=t(_p(
                            'cmd:pomodoro_stats|error:not_admin',
                            "Server stats require administrator permissions!"
                        ))
                    )
                    await ctx.interaction.edit_original_response(embed=embed)
                    return

                gid = ctx.guild.id
                async with connector.connection() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            "WITH combined AS ("
                            "  SELECT userid, start_time, duration FROM voice_sessions WHERE guildid = %s"
                            "  UNION ALL"
                            "  SELECT userid, start_time,"
                            "    EXTRACT(EPOCH FROM (NOW() - start_time))::INTEGER"
                            "  FROM voice_sessions_ongoing WHERE guildid = %s"
                            ") SELECT"
                            "  COUNT(*) as total_sessions,"
                            "  COALESCE(SUM(duration), 0) as total_seconds,"
                            "  COUNT(DISTINCT userid) as unique_users"
                            " FROM combined"
                            " WHERE start_time >= NOW() - INTERVAL '30 days'",
                            (gid, gid)
                        )
                        server_row = await cursor.fetchone()

                        await cursor.execute(
                            "WITH combined AS ("
                            "  SELECT userid, start_time, duration FROM voice_sessions WHERE guildid = %s"
                            "  UNION ALL"
                            "  SELECT userid, start_time,"
                            "    EXTRACT(EPOCH FROM (NOW() - start_time))::INTEGER"
                            "  FROM voice_sessions_ongoing WHERE guildid = %s"
                            ") SELECT userid, SUM(duration) as total_seconds"
                            " FROM combined"
                            " WHERE start_time >= NOW() - INTERVAL '30 days'"
                            " GROUP BY userid ORDER BY total_seconds DESC LIMIT 5",
                            (gid, gid)
                        )
                        top_users = await cursor.fetchall()

                active_timers = sum(
                    1 for timer in self.get_guild_timers(ctx.guild.id).values()
                    if timer.running
                )

                embed = discord.Embed(
                    colour=discord.Colour.orange(),
                    title=t(_p(
                        'cmd:pomodoro_stats|server|title',
                        "Server Productivity Stats \u2014 Last 30 Days"
                    ))
                )
                embed.add_field(
                    name=t(_p('cmd:pomodoro_stats|server|field:hours', "Total Productive Time")),
                    value=format_duration(server_row['total_seconds']),
                    inline=True
                )
                embed.add_field(
                    name=t(_p('cmd:pomodoro_stats|server|field:sessions', "Total Sessions")),
                    value=str(server_row['total_sessions']),
                    inline=True
                )
                embed.add_field(
                    name=t(_p('cmd:pomodoro_stats|server|field:users', "Active Students")),
                    value=str(server_row['unique_users']),
                    inline=True
                )
                embed.add_field(
                    name=t(_p('cmd:pomodoro_stats|server|field:timers', "Running Timers")),
                    value=str(active_timers),
                    inline=True
                )

                if top_users:
                    leaderboard = "\n".join(
                        f"**{i+1}.** <@{row['userid']}> \u2014 {format_duration(row['total_seconds'])}"
                        for i, row in enumerate(top_users)
                    )
                    embed.add_field(
                        name=t(_p('cmd:pomodoro_stats|server|field:top', "Top Studiers")),
                        value=leaderboard,
                        inline=False
                    )

                embed.set_footer(text=ctx.guild.name)

                analytics_url = f"{WEBSITE_BASE_URL}/dashboard/servers/{ctx.guild.id}/pomodoro"
                link_view = discord.ui.View()
                link_view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    url=analytics_url,
                    label="View Full Analytics"
                ))
                await ctx.interaction.edit_original_response(embed=embed, view=link_view)

            else:
                uid = ctx.author.id
                gid = ctx.guild.id
                async with connector.connection() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            "WITH combined AS ("
                            "  SELECT start_time, duration FROM voice_sessions"
                            "    WHERE userid = %s AND guildid = %s"
                            "  UNION ALL"
                            "  SELECT start_time,"
                            "    EXTRACT(EPOCH FROM (NOW() - start_time))::INTEGER"
                            "  FROM voice_sessions_ongoing"
                            "    WHERE userid = %s AND guildid = %s"
                            ") SELECT"
                            "  COUNT(*) as total_sessions,"
                            "  COALESCE(SUM(duration), 0) as total_seconds,"
                            "  COALESCE(MAX(duration), 0) as longest_session,"
                            "  COALESCE(SUM(CASE WHEN start_time::date = CURRENT_DATE"
                            "    THEN duration ELSE 0 END), 0) as today_seconds,"
                            "  COALESCE(SUM(CASE WHEN start_time >= NOW() - INTERVAL '7 days'"
                            "    THEN duration ELSE 0 END), 0) as week_seconds,"
                            "  COALESCE(SUM(CASE WHEN start_time >= NOW() - INTERVAL '30 days'"
                            "    THEN duration ELSE 0 END), 0) as month_seconds"
                            " FROM combined",
                            (uid, gid, uid, gid)
                        )
                        stats_row = await cursor.fetchone()

                        await cursor.execute(
                            "SELECT DISTINCT start_time::date as session_date"
                            " FROM voice_sessions"
                            " WHERE userid = %s AND guildid = %s"
                            "   AND start_time >= NOW() - INTERVAL '365 days'"
                            " ORDER BY session_date DESC",
                            (uid, gid)
                        )
                        date_rows = await cursor.fetchall()

                today = utc_now().date()
                session_dates = [row['session_date'] for row in date_rows]
                streak = 0
                if session_dates:
                    check = today
                    if session_dates[0] == today or session_dates[0] == today - timedelta(days=1):
                        for d in session_dates:
                            if d == check:
                                streak += 1
                                check -= timedelta(days=1)
                            elif d < check:
                                break

                if stats_row['total_sessions'] == 0:
                    embed = discord.Embed(
                        colour=discord.Colour.orange(),
                        description=t(_p(
                            'cmd:pomodoro_stats|personal|no_data',
                            "You haven't been productive in this server yet! "
                            "Join a voice channel or pomodoro timer to start tracking."
                        ))
                    )
                else:
                    embed = discord.Embed(
                        colour=discord.Colour.orange(),
                        title=t(_p(
                            'cmd:pomodoro_stats|personal|title',
                            "Your Study Stats in {guild}"
                        )).format(guild=ctx.guild.name)
                    )
                    embed.add_field(
                        name=t(_p('cmd:pomodoro_stats|personal|field:sessions', "Total Sessions")),
                        value=str(stats_row['total_sessions']),
                        inline=True
                    )
                    embed.add_field(
                        name=t(_p('cmd:pomodoro_stats|personal|field:hours', "Total Productive Time")),
                        value=format_duration(stats_row['total_seconds']),
                        inline=True
                    )
                    embed.add_field(
                        name=t(_p('cmd:pomodoro_stats|personal|field:longest', "Longest Session")),
                        value=format_duration(stats_row['longest_session']),
                        inline=True
                    )
                    embed.add_field(
                        name=t(_p('cmd:pomodoro_stats|personal|field:streak', "Current Streak")),
                        value=t(_p(
                            'cmd:pomodoro_stats|personal|streak_value',
                            "{days} day(s)"
                        )).format(days=streak),
                        inline=True
                    )
                    embed.add_field(name="\u200b", value="\u200b", inline=True)
                    embed.add_field(name="\u200b", value="\u200b", inline=True)
                    embed.add_field(
                        name=t(_p('cmd:pomodoro_stats|personal|field:today', "Today")),
                        value=format_duration(stats_row['today_seconds']),
                        inline=True
                    )
                    embed.add_field(
                        name=t(_p('cmd:pomodoro_stats|personal|field:week', "This Week")),
                        value=format_duration(stats_row['week_seconds']),
                        inline=True
                    )
                    embed.add_field(
                        name=t(_p('cmd:pomodoro_stats|personal|field:month', "This Month")),
                        value=format_duration(stats_row['month_seconds']),
                        inline=True
                    )
                    embed.set_footer(text=ctx.guild.name)

                link_view = discord.ui.View()
                link_view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    url=DASHBOARD_SESSION_URL,
                    label="View Full Stats"
                ))
                await ctx.interaction.edit_original_response(embed=embed, view=link_view)

        except Exception:
            logger.exception("Exception occurred while fetching pomodoro stats.")
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=t(_p(
                    'cmd:pomodoro_stats|error:query_failed',
                    "Failed to load productivity statistics. Please try again later."
                ))
            )
            await ctx.interaction.edit_original_response(embed=embed)
    # --- END AI-MODIFIED ---

    # ----- Guild Config Commands -----
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        ...

    @configure_group.command(
        name=_p('cmd:configure_pomodoro', "pomodoro"),
        description=_p('cmd:configure_pomodoro|desc', "Configure Pomodoro Timer System")
    )
    @appcmds.rename(
        pomodoro_channel=TimerSettings.PomodoroChannel._display_name
    )
    @appcmds.describe(
        pomodoro_channel=TimerSettings.PomodoroChannel._desc
    )
    @low_management_ward
    async def configure_pomodoro_command(self, ctx: LionContext,
                                         pomodoro_channel: Optional[discord.VoiceChannel | discord.TextChannel] = None):
        # Type checking guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True)

        pomodoro_channel_setting = await self.settings.PomodoroChannel.get(ctx.guild.id)

        if pomodoro_channel is not None:
            # VALIDATE PERMISSIONS!
            pomodoro_channel_setting.value = pomodoro_channel
            await pomodoro_channel_setting.write()
            modified = True
        else:
            modified = False

        if modified:
            line = pomodoro_channel_setting.update_message
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=f"{self.bot.config.emojis.tick} {line}"
            )
            await ctx.reply(embed=embed)

        if ctx.channel.id not in TimerConfigUI._listening or not modified:
            ui = TimerConfigUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()

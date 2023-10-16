from typing import Optional
from collections import defaultdict
import asyncio

import discord
from discord.ext import commands as cmds
from discord.ext.commands.errors import CheckFailure
from discord import app_commands as appcmds

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.sharding import THIS_SHARD
from meta.monitor import ComponentMonitor, ComponentStatus, StatusLevel
from utils.lib import utc_now
from utils.ratelimits import limit_concurrency

from wards import low_management_ward

from . import babel, logger
from .data import TimerData
from .lib import TimerRole
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

        if guildids:
            lguilds = await self.bot.core.lions.fetch_guilds(*guildids)
        else:
            lguilds = []

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
            if joining is not None:
                joining.last_seen[member.id] = utc_now()
                if not joining.running and joining.auto_restart:
                    tasks.append(asyncio.create_task(joining.start()))
                else:
                    tasks.append(asyncio.create_task(joining.update_status_card()))

            if tasks:
                try:
                    await asyncio.gather(*tasks)
                except Exception:
                    logger.exception(
                        "Exception occurred while handling timer voice event. "
                        f"Leaving: {leaving!r} "
                        f"Joining: {joining!r}"
                    )

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
        timer = self.get_channel_timer(channel.id)
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

    def get_channel_timer(self, channelid: int) -> Optional[Timer]:
        """
        Get the timer bound to the given channel, or None if it does not exist.
        """
        channel = self.bot.get_channel(channelid)
        if channel:
            return self.timers[channel.guild.id].get(channelid, None)

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
            timer = self.get_channel_timer(channel.id)
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
            await ctx.reply(embed=embed, ephemeral=False)

    # -- Admin Commands --
    @cmds.hybrid_group(
        name=_p('cmd:pomodoro', "pomodoro"),
        description=_p('cmd:pomodoro|desc', "Create and configure pomodoro timer rooms.")
    )
    @cmds.guild_only()
    async def pomodoro_group(self, ctx: LionContext):
        ...

    @pomodoro_group.command(
        name=_p('cmd:pomodoro_create', "create"),
        description=_p(
            'cmd:pomodoro_create|desc',
            "Create a new Pomodoro timer. Requires manage channel permissions."
        )
    )
    @appcmds.rename(
        channel=_p('cmd:pomodoro_create|param:channel', "timer_channel"),
        **{param: option._display_name for param, (option, _) in _param_options.items()}
    )
    @appcmds.describe(
        channel=_p(
            'cmd:pomodoro_create|param:channel|desc',
            "Voice channel to create the timer in. (Defaults to your current channel, or makes a new one.)"
        ),
        **{param: option._desc for param, (option, _) in _param_options.items()}
    )
    async def cmd_pomodoro_create(self, ctx: LionContext,
                                  focus_length: appcmds.Range[int, 1, 24*60],
                                  break_length: appcmds.Range[int, 1, 24*60],
                                  channel: Optional[discord.VoiceChannel] = None,
                                  notification_channel: Optional[discord.TextChannel | discord.VoiceChannel] = None,
                                  inactivity_threshold: Optional[appcmds.Range[int, 0, 127]] = None,
                                  manager_role: Optional[discord.Role] = None,
                                  voice_alerts: Optional[bool] = None,
                                  name: Optional[appcmds.Range[str, 0, 100]] = None,
                                  channel_name: Optional[appcmds.Range[str, 0, 100]] = None,
                                  ):
        t = self.bot.translator.t

        # Type guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

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
        elif (self.get_channel_timer(channel.id)) is not None:
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

            # Create timer
            timer = await self.create_timer(**create_args)

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
        timer = self.get_channel_timer(channel.id)
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
        timer = self.get_channel_timer(channel.id)
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

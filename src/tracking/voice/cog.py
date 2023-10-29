from typing import Optional
import asyncio
import itertools
import datetime as dt

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from data import Condition
from meta import LionBot, LionCog, LionContext
from meta.logger import log_wrap
from meta.sharding import THIS_SHARD
from meta.monitor import ComponentMonitor, ComponentStatus, StatusLevel
from utils.lib import utc_now
from core.lion_guild import VoiceMode

from wards import low_management_ward, moderator_ctxward

from . import babel, logger
from .data import VoiceTrackerData
from .settings import VoiceTrackerSettings, VoiceTrackerConfigUI

from .session import VoiceSession, TrackedVoiceState, SessionState

_p = babel._p


class VoiceTrackerCog(LionCog):
    """
    LionCog module controlling and configuring the voice tracking subsystem.
    """

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(VoiceTrackerData())
        self.settings = VoiceTrackerSettings()
        self.babel = babel
        self.monitor = ComponentMonitor('VoiceTracker', self._monitor)

        # State
        # Flag indicating whether local voice sessions have been initialised
        self.initialised = asyncio.Event()
        self.handle_events = False
        self.tracking_lock = asyncio.Lock()

        self.untracked_channels = self.settings.UntrackedChannels._cache

        self.active_sessions = VoiceSession._active_sessions_

    async def _monitor(self):
        state = (
            "<"
                "VoiceTracker"
                " initialised={initialised}"
                " active={active}"
                " pending={pending}"
                " ongoing={ongoing}"
                " locked={locked}"
                " actual={actual}"
                " channels={channels}"
                " cached={cached}"
                " initial_event={initial_event}"
                " lock={lock}"
                ">"
        )
        data = dict(
            initialised=self.initialised.is_set(),
            active=0,
            pending=0,
            ongoing=0,
            locked=0,
            actual=0,
            channels=0,
            cached=sum(len(gsessions) for gsessions in VoiceSession._sessions_.values()),
            initial_event=self.initialised,
            lock=self.tracking_lock
        )
        channels = set()
        for tguild in self.active_sessions.values():
            for session in tguild.values():
                data['active'] += 1
                if session.activity is SessionState.ONGOING:
                    data['ongoing'] += 1
                elif session.activity is SessionState.PENDING:
                    data['pending'] += 1

                if session.lock.locked():
                    data['locked'] += 1

                if session.state:
                    channels.add(session.state.channelid)
        data['channels'] = len(channels)

        for guild in self.bot.guilds:
            for channel in itertools.chain(guild.voice_channels, guild.stage_channels):
                if not self.is_untracked(channel):
                    for member in channel.members:
                        if member.voice and not member.bot:
                            data['actual'] += 1

        if not self.initialised.is_set():
            level = StatusLevel.STARTING
            info = f"(STARTING) Not initialised. {state}"
        elif self.tracking_lock.locked():
            level = StatusLevel.WAITING
            info = f"(WAITING) Waiting for tracking lock. {state}"
        elif data['actual'] != data['active']:
            level = StatusLevel.UNSURE
            info = f"(UNSURE) Actual sessions do not match active. {state}"
        else:
            level = StatusLevel.OKAY
            info = f"(OK) Voice tracking operational. {state}"

        return ComponentStatus(level, info, info, data)


    async def cog_load(self):
        self.bot.system_monitor.add_component(self.monitor)
        await self.data.init()

        self.bot.core.guild_config.register_model_setting(self.settings.HourlyReward)
        self.bot.core.guild_config.register_model_setting(self.settings.HourlyLiveBonus)
        self.bot.core.guild_config.register_model_setting(self.settings.DailyVoiceCap)
        self.bot.core.guild_config.register_setting(self.settings.UntrackedChannels)

        # Update the tracked voice channel cache
        await self.settings.UntrackedChannels.setup(self.bot)

        configcog = self.bot.get_cog('ConfigCog')
        if configcog is None:
            logger.critical(
                "Attempting to load VoiceTrackerCog before ConfigCog! Cannot crossload configuration group."
            )
        else:
            self.crossload_group(self.configure_group, configcog.config_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        # TODO: Shutdown task to trigger updates on all ongoing sessions
        # Simultaneously!
        ...

    # ----- Cog API -----
    def get_session(self, guildid, userid, **kwargs):
        """
        Get the VoiceSession for the given member.

        Creates it if it does not exist.
        """
        return VoiceSession.get(self.bot, guildid, userid, **kwargs)

    def is_untracked(self, channel) -> bool:
        if not channel.guild:
            raise ValueError("Untracked check invalid for private channels.")
        untracked = self.untracked_channels.get(channel.guild.id, ())
        if channel.id in untracked:
            untracked = True
        elif channel.category_id and channel.category_id in untracked:
            untracked = True
        else:
            untracked = False
        return untracked

    @log_wrap(action='load sessions')
    async def _load_sessions(self,
                             states: dict[tuple[int, int], TrackedVoiceState],
                             ongoing: list[VoiceTrackerData.VoiceSessionsOngoing]):
        """
        Load voice sessions from provided states and ongoing data.

        Provided data may cross multiple guilds.
        Assumes all states which do not have data should be started.
        Assumes all ongoing data which does not have states should be ended.
        Assumes untracked channel data is up to date.
        """
        OngoingData = VoiceTrackerData.VoiceSessionsOngoing

        # Compute time to end complete sessions
        now = utc_now()
        last_update = max((row.last_update for row in ongoing), default=now)
        end_at = min(last_update + dt.timedelta(seconds=3600), now)

        # Bulk fetches for voice-active members and guilds
        active_memberids = list(states.keys())
        active_guildids = set(gid for gid, _ in states)

        if states:
            lguilds = await self.bot.core.lions.fetch_guilds(*active_guildids)
            await self.bot.core.lions.fetch_members(*active_memberids)
            tracked_today_data = await self.data.VoiceSessions.multiple_voice_tracked_since(
                *((guildid, userid, lguilds[guildid].today) for guildid, userid in active_memberids)
            )
            tracked_today = {(row['guildid'], row['userid']): row['tracked'] for row in tracked_today_data}
        else:
            lguilds = {}
            tracked_today = {}

        # Zip session information together by memberid keys
        sessions: dict[tuple[int, int], tuple[Optional[TrackedVoiceState], Optional[OngoingData]]] = {}
        for row in ongoing:
            key = (row.guildid, row.userid)
            sessions[key] = (states.pop(key, None), row)
        for key, state in states.items():
            sessions[key] = (state, None)

        # Now split up session information to fill action maps
        close_ongoing = []
        update_ongoing = []
        create_ongoing = []
        expiries = {}
        load_sessions = []
        schedule_sessions = {}

        for (gid, uid), (state, data) in sessions.items():
            if state is not None:
                # Member is active
                if data is not None and data.channelid != state.channelid:
                    # Ongoing session does not match active state
                    # Close the session, but still create/schedule the state
                    close_ongoing.append((gid, uid, end_at))
                    data = None

                # Now create/update/schedule active session
                # Also create/update data if required
                lguild = lguilds[gid]
                tomorrow = lguild.today + dt.timedelta(days=1)
                cap = lguild.config.get('daily_voice_cap').value
                tracked = tracked_today[gid, uid]
                hourly_rate = await self._calculate_rate(gid, uid, state)

                if tracked >= cap:
                    # Active session is already over cap
                    # Stop ongoing if it exists, and schedule next session start
                    delay = (tomorrow - now).total_seconds()
                    start_time = tomorrow
                    expiry = tomorrow + dt.timedelta(seconds=cap)
                    schedule_sessions[(gid, uid)] = (delay, start_time, expiry, state, hourly_rate)
                    if data is not None:
                        close_ongoing.append((
                            gid, uid,
                            max(now - dt.timedelta(seconds=tracked - cap), data.last_update)
                        ))
                else:
                    # Active session, update/create data
                    expiry = now + dt.timedelta(seconds=(cap - tracked))
                    if expiry > tomorrow:
                        expiry = tomorrow + dt.timedelta(seconds=cap)
                    expiries[(gid, uid)] = expiry
                    if data is not None:
                        update_ongoing.append((gid, uid, now, state.stream, state.video, hourly_rate))
                    else:
                        create_ongoing.append((
                            gid, uid, state.channelid, now, now, state.stream, state.video, hourly_rate
                        ))
            elif data is not None:
                # Ongoing data has no state, close the session
                close_ongoing.append((gid, uid, end_at))

        # Close data that needs closing
        if close_ongoing:
            logger.info(
                f"Ending {len(close_ongoing)} ongoing voice sessions with no matching voice state."
            )
            await self.data.VoiceSessionsOngoing.close_voice_sessions_at(*close_ongoing)

        # Update data that needs updating
        if update_ongoing:
            logger.info(
                f"Continuing {len(update_ongoing)} ongoing voice sessions with matching voice state."
            )
            rows = await self.data.VoiceSessionsOngoing.update_voice_sessions_at(*update_ongoing)
            load_sessions.extend(rows)

        # Create data that needs creating
        if create_ongoing:
            logger.info(
                f"Creating {len(create_ongoing)} voice sessions from new voice states."
            )
            # First ensure the tracked channels exist
            cids = set((item[2], item[0]) for item in create_ongoing)
            await self.data.TrackedChannel.fetch_multiple(*cids)

            # Then create the sessions
            rows = await self.data.VoiceSessionsOngoing.table.insert_many(
                ('guildid', 'userid', 'channelid', 'start_time', 'last_update', 'live_stream',
                 'live_video', 'hourly_coins'),
                *create_ongoing
            ).with_adapter(self.data.VoiceSessionsOngoing._make_rows)
            load_sessions.extend(rows)

        # Create sessions from ongoing, with expiry
        for row in load_sessions:
            VoiceSession.from_ongoing(self.bot, row, expiries[(row.guildid, row.userid)])

        # Schedule starting sessions
        for (gid, uid), args in schedule_sessions.items():
            session = VoiceSession.get(self.bot, gid, uid)
            await session.schedule_start(*args)

        logger.info(
            f"Successfully loaded {len(load_sessions)} and scheduled {len(schedule_sessions)} voice sessions."
        )

    @log_wrap(action='refresh guild sessions')
    async def refresh_guild_sessions(self, guild: discord.Guild):
        """
        Idempotently refresh all guild voice sessions in the given guild.

        Essentially a lighter version of `initialise`.
        """
        # TODO: There is a very small potential window for a race condition here
        # Since we do not have a version of 'handle_events' for the guild
        # We may actually handle events before starting refresh
        # Causing sessions to have invalid state.
        # If this becomes an actual problem, implement an `ignore_guilds` set flag of some form...
        logger.debug(f"Beginning voice state refresh for <gid: {guild.id}>")

        async with self.tracking_lock:
            # TODO: Add a 'lock holder' attribute which is readable by the monitor
            logger.debug(f"Voice state refresh for <gid: {guild.id}> is past lock")

            # Deactivate any ongoing session tasks in this guild
            active = self.active_sessions.pop(guild.id, {}).values()
            for session in active:
                session.cancel()
            # Clear registry
            VoiceSession._sessions_.pop(guild.id, None)

            # Update untracked channel information for this guild
            self.untracked_channels.pop(guild.id, None)
            await self.settings.UntrackedChannels.get(guild.id)

            # Read tracked voice states
            states = {}
            for channel in itertools.chain(guild.voice_channels, guild.stage_channels):
                if not self.is_untracked(channel):
                    for member in channel.members:
                        if member.voice and not member.bot:
                            state = TrackedVoiceState.from_voice_state(member.voice)
                            states[(guild.id, member.id)] = state
            logger.debug(f"Loaded {len(states)} tracked voice states for <gid: {guild.id}>.")

            # Read ongoing session data
            ongoing = await self.data.VoiceSessionsOngoing.fetch_where(guildid=guild.id)
            logger.debug(
                f"Loaded {len(ongoing)} ongoing voice sessions from data for <gid: {guild.id}>. Beginning reload."
            )

            await self._load_sessions(states, ongoing)
            logger.info(
                f"Completed guild voice session reload for <gid: {guild.id}> "
                f"with '{len(self.active_sessions[guild.id])}' active sessions."
            )


    # ----- Event Handlers -----
    @LionCog.listener('on_ready')
    @log_wrap(action='Init Voice Sessions')
    async def initialise(self):
        """
        (Re)-initialise voice tracking using current voice channel members as source of truth.

        Ends ongoing sessions for members who are not in the given voice channel.
        """
        logger.info("Beginning voice session state initialisation. Disabling voice event handling.")
        # If `on_ready` is called, that means we are initialising
        # or we missed events and need to re-initialise.
        # Start ignoring events because they may be working on stale or partial state
        self.handle_events = False

        # Services which read our cache should wait for initialisation before taking the lock
        self.initialised.clear()

        # Wait for running events to complete
        # And make sure future events will be processed after initialisation
        # Note only events occurring after our voice state snapshot will be processed
        async with self.tracking_lock:
            # Deactivate all ongoing sessions
            active = [session for gsessions in self.active_sessions.values() for session in gsessions.values()]
            for session in active:
                session.cancel()
            self.active_sessions.clear()

            # Also clear the session registry cache
            VoiceSession._sessions_.clear()

            # Refresh untracked information for all guilds we are in
            await self.settings.UntrackedChannels.setup(self.bot)

            # Read and save the tracked voice states of all visible voice channels
            states = {}
            for guild in self.bot.guilds:
                for channel in itertools.chain(guild.voice_channels, guild.stage_channels):
                    if not self.is_untracked(channel):
                        for member in channel.members:
                            if member.voice and not member.bot:
                                state = TrackedVoiceState.from_voice_state(member.voice)
                                states[(guild.id, member.id)] = state

            logger.info(
                f"Saved voice snapshot with {len(states)} tracked states. Re-enabling voice event handling."
            )
            self.handle_events = True

            # Load ongoing session data for the entire shard
            ongoing = await self.data.VoiceSessionsOngoing.fetch_where(THIS_SHARD)
            logger.info(
                f"Retrieved {len(ongoing)} ongoing voice sessions from data. Beginning reload."
            )

            await self._load_sessions(states, ongoing)

            self.initialised.set()

    @LionCog.listener("on_voice_state_update")
    @log_wrap(action='Voice Track')
    async def session_voice_tracker(self, member, before, after):
        """
        Spawns the correct tasks from members joining, leaving, and changing live state.
        """
        if not self.handle_events:
            # Rely on initialisation to handle current state
            return

        if member.bot:
            return

        # Check user blacklist
        blacklists = self.bot.get_cog('Blacklists')
        if member.id in blacklists.user_blacklist:
            # TODO: Make sure we cancel user sessions when they get blacklisted
            # Should we dispatch an event for the blacklist?
            return

        # Serialise state before waiting on the lock
        bstate = TrackedVoiceState.from_voice_state(before)
        astate = TrackedVoiceState.from_voice_state(after)
        if bstate == astate:
            # If tracked state did not change, ignore event
            return

        bchannel = before.channel if before else None
        achannel = after.channel if after else None

        # Take tracking lock
        async with self.tracking_lock:
            # Fetch tracked member session state
            session = self.get_session(member.guild.id, member.id)
            tstate = session.state
            # This usually pulls from cache, but don't rely on it
            untracked = (await self.settings.UntrackedChannels.get(member.guild.id)).data

            if (bstate.channelid != astate.channelid):
                # Leaving/Moving/Joining channels
                if (leaving := bstate.channelid):
                    # Leaving channel
                    if session.activity:
                        # Leaving channel during active session
                        if tstate.channelid != leaving:
                            # Active session channel does not match leaving channel
                            logger.warning(
                                "Voice event does not match session information! "
                                f"Member '{member.name}' <uid:{member.id}> "
                                f"of guild '{member.guild.name}' <gid:{member.guild.id}> "
                                f"left channel '{bchannel}' <cid:{leaving}> "
                                f"during voice session in channel <cid:{tstate.channelid}>!"
                            )
                        # Close (or cancel) active session
                        logger.info(
                            f"Closing session for member `{member.name}' <uid:{member.id}> "
                            f"in guild '{member.guild.name}' <gid: {member.guild.id}> "
                            " because they left the channel."
                        )
                        await session.close()
                    elif not self.is_untracked(bchannel):
                        # Leaving tracked channel without an active session?
                        logger.warning(
                            "Voice event does not match session information! "
                            f"Member '{member.name}' <uid:{member.id}> "
                            f"of guild '{member.guild.name}' <gid:{member.guild.id}> "
                            f"left tracked channel '{bchannel}' <cid:{leaving}> "
                            f"with no matching voice session!"
                        )

                if (joining := astate.channelid):
                    # Joining channel
                    if session.activity:
                        # Member has an active voice session, should be impossible!
                        logger.warning(
                            "Voice event does not match session information! "
                            f"Member '{member.name}' <uid:{member.id}> "
                            f"of guild '{member.guild.name}' <gid:{member.guild.id}> "
                            f"joined channel '{achannel}' <cid:{joining}> "
                            f"during voice session in channel <cid:{tstate.channelid}>!"
                        )
                        await session.close()
                    if not self.is_untracked(achannel):
                        # If the channel they are joining is tracked, schedule a session start for them
                        delay, start, expiry = await self._session_boundaries_for(member.guild.id, member.id)
                        hourly_rate = await self._calculate_rate(member.guild.id, member.id, astate)

                        logger.debug(
                            f"Scheduling voice session for member `{member.name}' <uid:{member.id}> "
                            f"in guild '{member.guild.name}' <gid: member.guild.id> "
                            f"in channel '{achannel}' <cid: {achannel.id}>. "
                            f"Session will start at {start}, expire at {expiry}, and confirm in {delay}."
                        )
                        await session.schedule_start(delay, start, expiry, astate, hourly_rate)

                        t = self.bot.translator.t
                        lguild = await self.bot.core.lions.fetch_guild(member.guild.id)
                        lguild.log_event(
                            t(_p(
                                'eventlog|event:voice_session_start|title',
                                "Member Joined Tracked Voice Channel"
                            )),
                            t(_p(
                                'eventlog|event:voice_session_start|desc',
                                "{member} joined {channel}."
                            )).format(
                                member=member.mention, channel=achannel.mention,
                            ),
                            start=discord.utils.format_dt(start, 'F'),
                            expiry=discord.utils.format_dt(expiry, 'R'),
                        )
            elif session.activity:
                # If the channelid did not change, the live state must have
                # Recalculate the economy rate, and update the session
                # Touch the ongoing session with the new state
                hourly_rate = await self._calculate_rate(member.guild.id, member.id, astate)
                await session.update(new_state=astate, new_rate=hourly_rate)

    @LionCog.listener("on_guildset_untracked_channels")
    @LionCog.listener("on_guildset_hourly_reward")
    @LionCog.listener("on_guildset_hourly_live_bonus")
    @LionCog.listener("on_guildset_daily_voice_cap")
    @LionCog.listener("on_guildset_timezone")
    async def _event_refresh_guild(self, guildid: int, setting):
        if not self.handle_events:
            return
        guild = self.bot.get_guild(guildid)
        if guild is None:
            logger.warning(
                f"Voice tracker discarding '{setting.setting_id}' event for unknown guild <gid: {guildid}>."
            )
        else:
            logger.debug(
                f"Voice tracker handling '{setting.setting_id}' event for guild <gid: {guildid}>."
            )
            await self.refresh_guild_sessions(guild)

    async def _calculate_rate(self, guildid, userid, state):
        """
        Calculate the economy hourly rate for the given member in the given state.

        Takes into account economy bonuses.
        """
        lguild = await self.bot.core.lions.fetch_guild(guildid)
        hourly_rate = lguild.config.get('hourly_reward').value
        if state.live:
            hourly_rate += lguild.config.get('hourly_live_bonus').value

        economy = self.bot.get_cog('Economy')
        if economy is not None:
            bonus = await economy.fetch_economy_bonus(guildid, userid)
            hourly_rate *= bonus
        else:
            logger.warning("Economy cog not loaded! Voice tracker cannot account for economy bonuses.")

        return hourly_rate

    async def _session_boundaries_for(self, guildid: int, userid: int) -> tuple[float, dt.datetime, dt.datetime]:
        """
        Compute when the next session for this member should start and expire.

        Assumes the member does not have a currently active session!
        Takes into account the daily voice cap, and the member's study time so far today.
        Days are based on the guild timezone, not the member timezone.
        (Otherwise could be abused through timezone-shifting.)

        Returns
        -------
        tuple[int, dt.datetime, dt.datetime]:
            (start delay, start time, expiry time)

        """
        lguild = await self.bot.core.lions.fetch_guild(guildid)
        now = lguild.now
        tomorrow = lguild.today + dt.timedelta(days=1)

        studied_today = await self.fetch_tracked_today(guildid, userid)
        cap = lguild.config.get('daily_voice_cap').value

        if studied_today >= cap - 90:
            start_time = tomorrow
            delay = (tomorrow - now).total_seconds()
        else:
            start_time = now
            delay = 20

        remaining = cap - studied_today
        expiry = start_time + dt.timedelta(seconds=remaining)
        if expiry > tomorrow:
            expiry = tomorrow + dt.timedelta(seconds=cap)

        return (delay, start_time, expiry)

    async def fetch_tracked_today(self, guildid, userid) -> int:
        """
        Fetch how long the given member has tracked on voice today, using the guild timezone.

        Applies cache wherever possible.
        """
        # TODO: Design caching scheme for this.
        lguild = await self.bot.core.lions.fetch_guild(guildid)
        return await self.data.VoiceSessions.study_time_since(guildid, userid, lguild.today)

    @LionCog.listener("on_guild_join")
    @log_wrap(action='Join Guild Voice Sessions')
    async def join_guild_sessions(self, guild: discord.Guild):
        """
        Initialise and start required new sessions from voice channel members when we join a guild.
        """
        if not self.handle_events:
            # Initialisation will take care of it for us
            return
        await self.refresh_guild_sessions(guild)

    @LionCog.listener("on_guild_remove")
    @log_wrap(action='Leave Guild Voice Sessions')
    async def leave_guild_sessions(self, guild):
        """
        Terminate ongoing sessions when we leave a guild.
        """
        if not self.handle_events:
            return

        async with self.tracking_lock:
            sessions = VoiceSession._active_sessions_.pop(guild.id, {})
            VoiceSession._sessions_.pop(guild.id, None)
            now = utc_now()
            to_close = []  # (guildid, userid, _at)
            for session in sessions.values():
                session.cancel()
                to_close.append((session.guildid, session.userid, now))
            if to_close:
                await self.data.VoiceSessionsOngoing.close_voice_sessions_at(*to_close)
            logger.info(
                f"Closed {len(to_close)} voice sessions after leaving guild '{guild.name}' <gid:{guild.id}>"
            )

    # ----- Commands -----
    @cmds.hybrid_command(
        name=_p('cmd:now', "now"),
        description=_p(
            'cmd:now|desc',
            "Describe what you are working on, or see what your friends are working on!"
        )
    )
    @appcmds.rename(
        tag=_p('cmd:now|param:tag', "tag"),
        user=_p('cmd:now|param:user', "user"),
        clear=_p('cmd:now|param:clear', "clear"),
    )
    @appcmds.describe(
        tag=_p(
            'cmd:now|param:tag|desc',
            "Describe what you are working on in 10 characters or less!"
        ),
        user=_p(
            'cmd:now|param:user|desc',
            "Check what a friend is working on."
        ),
        clear=_p(
            'cmd:now|param:clear|desc',
            "Unset your activity tag (or the target user's tag, for moderators)."
        )
    )
    @appcmds.guild_only
    async def now_cmd(self, ctx: LionContext,
                      tag: Optional[appcmds.Range[str, 0, 10]] = None,
                      user: Optional[discord.Member] = None,
                      clear: Optional[bool] = None
                      ):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)
        is_moderator = await moderator_ctxward(ctx)
        target = user if user is not None else ctx.author
        session = self.get_session(ctx.guild.id, target.id, create=False)

        # Handle case where target is not active
        if (session is None) or session.activity is SessionState.INACTIVE:
            if target == ctx.author:
                error = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=t(_p(
                        'cmd:now|target:self|error:target_inactive',
                        "You have no running session! "
                        "Join a tracked voice channel to start a session."
                    )).format(mention=target.mention)
                )
            else:
                error = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=t(_p(
                        'cmd:now|target:other|error:target_inactive',
                        "{mention} has no running session!"
                    )).format(mention=target.mention)
                )
            await ctx.interaction.edit_original_response(embed=error)
            return

        if clear:
            # Clear activity tag mode
            if target == ctx.author:
                # Clear the author's tag
                await session.set_tag(None)
                ack = discord.Embed(
                    colour=discord.Colour.brand_green(),
                    title=t(_p(
                        'cmd:now|target:self|mode:clear|success|title',
                        "Session Tag Cleared"
                    )),
                    description=t(_p(
                        'cmd:now|target:self|mode:clear|success|desc',
                        "Successfully unset your session tag."
                    ))
                )
            elif not is_moderator:
                # Trying to clear someone else's tag without being a moderator
                ack = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'cmd:now|target:other|mode:clear|error:perms|title',
                        "You can't do that!"
                    )),
                    description=t(_p(
                        'cmd:now|target:other|mode:clear|error:perms|desc',
                        "You need to be a moderator to set or clear someone else's session tag."
                    ))
                )
            else:
                # Clearing someone else's tag as a moderator
                await session.set_tag(None)
                ack = discord.Embed(
                    colour=discord.Colour.brand_green(),
                    title=t(_p(
                        'cmd:now|target:other|mode:clear|success|title',
                        "Session Tag Cleared!"
                    )),
                    description=t(_p(
                        'cmd:now|target:other|mode:clear|success|desc',
                        "Cleared {target}'s session tag."
                    )).format(target=target.mention)
                )
        elif tag:
            # Tag setting mode
            if target == ctx.author:
                # Set the author's tag
                await session.set_tag(tag)
                ack = discord.Embed(
                    colour=discord.Colour.brand_green(),
                    title=t(_p(
                        'cmd:now|target:self|mode:set|success|title',
                        "Session Tag Set!"
                    )),
                    description=t(_p(
                        'cmd:now|target:self|mode:set|success|desc',
                        "You are now working on `{new_tag}`. Good luck!"
                    )).format(new_tag=tag)
                )
            elif not is_moderator:
                # Trying the set someone else's tag without being a moderator
                ack = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'cmd:now|target:other|mode:set|error:perms|title',
                        "You can't do that!"
                    )),
                    description=t(_p(
                        'cmd:now|target:other|mode:set|error:perms|desc',
                        "You need to be a moderator to set or clear someone else's session tag!"
                    ))
                )
            else:
                # Setting someone else's tag as a moderator
                await session.set_tag(tag)
                ack = discord.Embed(
                    colour=discord.Colour.brand_green(),
                    title=t(_p(
                        'cmd:now|target:other|mode:set|success|title',
                        "Session Tag Set!"
                    )),
                    description=t(_p(
                        'cmd:now|target:other|mode:set|success|desc',
                        "Set {target}'s session tag to `{new_tag}`."
                    )).format(target=target.mention, new_tag=tag)
                )
        else:
            # Display tag and voice time
            if target == ctx.author:
                if session.tag:
                    desc = t(_p(
                        'cmd:now|target:self|mode:show_with_tag|desc',
                        "You have been working on **`{tag}`** in {channel} since {time}!"
                    ))
                else:
                    desc = t(_p(
                        'cmd:now|target:self|mode:show_without_tag|desc',
                        "You have been working in {channel} since {time}!\n\n"
                        "Use `/now <tag>` to set what you are working on."
                    ))
            else:
                if session.tag:
                    desc = t(_p(
                        'cmd:now|target:other|mode:show_with_tag|desc',
                        "{target} is current working in {channel}!\n"
                        "They have been working on **{tag}** since {time}."
                    ))
                else:
                    desc = t(_p(
                        'cmd:now|target:other|mode:show_without_tag|desc',
                        "{target} has been working in {channel} since {time}!"
                    ))
            desc = desc.format(
                tag=session.tag,
                channel=f"<#{session.state.channelid}>",
                time=discord.utils.format_dt(session.start_time, 't'),
                target=target.mention,
            )
            ack = discord.Embed(
                colour=discord.Colour.orange(),
                description=desc,
                timestamp=utc_now()
            )
        await ctx.interaction.edit_original_response(embed=ack)

    # ----- Configuration Commands -----
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        # Placeholder group method, not used.
        pass

    @configure_group.command(
        name=_p('cmd:configure_voice_rates', "voice_rewards"),
        description=_p(
            'cmd:configure_voice_rates|desc',
            "Configure Voice tracking rewards and experience"
        )
    )
    @appcmds.rename(
        hourly_reward=VoiceTrackerSettings.HourlyReward._display_name,
        hourly_live_bonus=VoiceTrackerSettings.HourlyLiveBonus._display_name,
        daily_voice_cap=VoiceTrackerSettings.DailyVoiceCap._display_name,
    )
    @appcmds.describe(
        hourly_reward=VoiceTrackerSettings.HourlyReward._desc,
        hourly_live_bonus=VoiceTrackerSettings.HourlyLiveBonus._desc,
        daily_voice_cap=VoiceTrackerSettings.DailyVoiceCap._desc,
    )
    @low_management_ward
    async def configure_voice_tracking_cmd(self, ctx: LionContext,
                                           hourly_reward: Optional[int] = None,  # TODO: Change these to Ranges
                                           hourly_live_bonus: Optional[int] = None,
                                           daily_voice_cap: Optional[int] = None):
        """
        Guild configuration command to control the voice tracking configuration.
        """
        # TODO: daily_voice_cap could technically be a string, but simplest to represent it as hours
        t = self.bot.translator.t

        # Type checking guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # Retrieve settings, initialising from cache where possible
        setting_hourly_reward = ctx.lguild.config.get('hourly_reward')
        setting_hourly_live_bonus = ctx.lguild.config.get('hourly_live_bonus')
        setting_daily_voice_cap = ctx.lguild.config.get('daily_voice_cap')

        modified = []
        if hourly_reward is not None and hourly_reward != setting_hourly_reward._data:
            setting_hourly_reward.data = hourly_reward
            await setting_hourly_reward.write()
            modified.append(setting_hourly_reward)

        if hourly_live_bonus is not None and hourly_live_bonus != setting_hourly_live_bonus._data:
            setting_hourly_live_bonus.data = hourly_live_bonus
            await setting_hourly_live_bonus.write()
            modified.append(setting_hourly_live_bonus)

        if daily_voice_cap is not None and daily_voice_cap * 3600 != setting_daily_voice_cap._data:
            setting_daily_voice_cap.data = daily_voice_cap * 3600
            await setting_daily_voice_cap.write()
            modified.append(setting_daily_voice_cap)

        # Send update ack
        if modified:
            if ctx.lguild.guild_mode.voice is VoiceMode.VOICE:
                description = t(_p(
                    'cmd:configure_voice_tracking|mode:voice|resp:success|desc',
                    "Members will now be rewarded {coin}**{base} (+ {bonus})** per hour they spend (live) "
                    "in a voice channel, up to a total of **{cap}** hours per server day."
                )).format(
                    coin=self.bot.config.emojis.coin,
                    base=setting_hourly_reward.value,
                    bonus=setting_hourly_live_bonus.value,
                    cap=int(setting_daily_voice_cap.value // 3600)
                )
            else:
                description = t(_p(
                    'cmd:configure_voice_tracking|mode:study|resp:success|desc',
                    "Members will now be rewarded {coin}**{base}** per hour of study "
                    "in this server, with a bonus of {coin}**{bonus}** if they stream of display video, "
                    "up to a total of **{cap}** hours per server day."
                )).format(
                    coin=self.bot.config.emojis.coin,
                    base=setting_hourly_reward.value,
                    bonus=setting_hourly_live_bonus.value,
                    cap=int(setting_daily_voice_cap.value // 3600)
                )
            await ctx.reply(
                embed=discord.Embed(
                    colour=discord.Colour.brand_green(),
                    description=description
                )
            )

        if ctx.channel.id not in VoiceTrackerConfigUI._listening or not modified:
            # Launch setting group UI
            configui = VoiceTrackerConfigUI(self.bot, ctx.guild.id, ctx.channel.id)
            await configui.run(ctx.interaction)
            await configui.wait()

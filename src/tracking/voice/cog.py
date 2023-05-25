from typing import Optional
import asyncio
import datetime as dt
from collections import defaultdict

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from meta import LionBot, LionCog, LionContext
from meta.errors import UserInputError
from meta.logger import log_wrap, logging_context
from meta.sharding import THIS_SHARD
from utils.lib import utc_now, error_embed
from core.lion_guild import VoiceMode

from wards import low_management

from . import babel, logger
from .data import VoiceTrackerData
from .settings import VoiceTrackerSettings, VoiceTrackerConfigUI

from .session import VoiceSession, TrackedVoiceState

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

        # State
        self.handle_events = False
        self.tracking_lock = asyncio.Lock()

        self.untracked_channels = self.settings.UntrackedChannels._cache

    async def cog_load(self):
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
            self.crossload_group(self.configure_group, configcog.configure_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        # TODO: Shutdown task to trigger updates on all ongoing sessions
        # Simultaneously!
        ...

    def get_session(self, guildid, userid) -> VoiceSession:
        """
        Get the VoiceSession for the given member.

        Creates it if it does not exist.
        """
        return VoiceSession.get(self.bot, guildid, userid)

    @LionCog.listener('on_ready')
    @log_wrap(action='Init Voice Sessions')
    async def initialise(self):
        """
        (Re)-initialise voice tracking using current voice channel members as source of truth.

        Ends ongoing sessions for members who are not in the given voice channel.
        """
        # First take the tracking lock
        # Ensures current event handling completes before re-initialisation
        async with self.tracking_lock:
            logger.info("Reloading ongoing voice sessions")

            logger.debug("Disabling voice state event handling.")
            self.handle_events = False
            # Read and save the tracked voice states of all visible voice channels
            voice_members = {}  # (guildid, userid) -> TrackedVoiceState
            voice_guilds = set()
            for guild in self.bot.guilds:
                for channel in guild.voice_channels:
                    for member in channel.members:
                        voice_members[(guild.id, member.id)] = TrackedVoiceState.from_voice_state(member.voice)
                        voice_guilds.add(guild.id)

            logger.debug(f"Cached {len(voice_members)} members from voice channels.")
            self.handle_events = True
            logger.debug("Re-enabled voice state event handling.")

            # Iterate through members with current ongoing sessions
            # End or update sessions as needed, based on saved tracked state
            ongoing_rows = await self.data.VoiceSessionsOngoing.fetch_where(
                guildid=[guild.id for guild in self.bot.guilds]
            )
            logger.debug(
                f"Loaded {len(ongoing_rows)} ongoing sessions from data. Splitting into complete and incomplete."
            )
            complete = []
            incomplete = []
            incomplete_guildids = set()

            # Compute time to end complete sessions
            now = utc_now()
            last_update = max((row.last_update for row in ongoing_rows), default=now)
            end_at = min(last_update + dt.timedelta(seconds=3600), now)

            for row in ongoing_rows:
                key = (row.guildid, row.userid)
                state = voice_members.get(key, None)
                untracked = self.untracked_channels.get(row.guildid, [])
                if (
                    state
                    and state.channelid == row.channelid
                    and state.channelid not in untracked
                    and (ch := self.bot.get_channel(state.channelid)) is not None
                    and (not ch.category_id or ch.category_id not in untracked)
                ):
                    # Mark session as ongoing
                    incomplete.append((row, state))
                    incomplete_guildids.add(row.guildid)
                    voice_members.pop(key)
                else:
                    # Mark session as complete
                    complete.append((row.guildid, row.userid, end_at))

            # Load required guild data into cache
            active_guildids = incomplete_guildids.union(voice_guilds)
            if active_guildids:
                await self.bot.core.data.Guild.fetch_where(guildid=tuple(active_guildids))
            lguilds = {guildid: await self.bot.core.lions.fetch_guild(guildid) for guildid in active_guildids}

            # Calculate tracked_today for members with ongoing sessions
            active_members = set((row.guildid, row.userid) for row, _ in incomplete)
            active_members.update(voice_members.keys())
            if active_members:
                tracked_today_data = await self.data.VoiceSessions.multiple_voice_tracked_since(
                    *((guildid, userid, lguilds[guildid].today) for guildid, userid in active_members)
                )
            else:
                tracked_today_data = []
            tracked_today = {(row['guildid'], row['userid']): row['tracked'] for row in tracked_today_data}

            if incomplete:
                # Note that study_time_since _includes_ ongoing sessions in its calculation
                # So expiry times are "time left today until cap" or "tomorrow + cap"
                to_load = []  # (session_data, expiry_time)
                to_update = []  # (guildid, userid, update_at, stream, video, hourly_rate)
                for session_data, state in incomplete:
                    # Calculate expiry times
                    lguild = lguilds[session_data.guildid]
                    cap = lguild.config.get('daily_voice_cap').value
                    tracked = tracked_today[(session_data.guildid, session_data.userid)]
                    if tracked >= cap:
                        # Already over cap
                        complete.append(
                            session_data.guildid,
                            session_data.userid,
                            max(now + dt.timedelta(seconds=tracked - cap), session_data.last_update)
                        )
                    else:
                        tomorrow = lguild.today + dt.timedelta(days=1)
                        expiry = now + dt.timedelta(seconds=(cap - tracked))
                        if expiry > tomorrow:
                            expiry = tomorrow + dt.timedelta(seconds=cap)
                        to_load.append((session_data, expiry))

                        # TODO: Probably better to do this by batch
                        # Could force all bonus calculators to accept list of members
                        hourly_rate = await self._calculate_rate(session_data.guildid, session_data.userid, state)
                        to_update.append((
                            session_data.guildid,
                            session_data.userid,
                            now,
                            state.stream,
                            state.video,
                            hourly_rate
                        ))
                # Run the updates, note that session_data uses registry pattern so will also update
                if to_update:
                    await self.data.VoiceSessionsOngoing.update_voice_sessions_at(*to_update)

                # Load the sessions
                for data, expiry in to_load:
                    VoiceSession.from_ongoing(self.bot, data, expiry)

                logger.info(f"Resumed {len(to_load)} ongoing voice sessions.")

            if complete:
                logger.info(f"Ending {len(complete)} out-of-date or expired study sessions.")

                # Complete sessions just need a mass end_voice_session_at()
                await self.data.VoiceSessionsOngoing.close_voice_sessions_at(*complete)

            # Then iterate through the saved states from tracked voice channels
            # Start sessions if they don't already exist
            if voice_members:
                expiries = {}  # (guildid, memberid) -> expiry time
                to_create = []  # (guildid, userid, channelid, start_time, last_update, live_stream, live_video, rate)
                for (guildid, userid), state in voice_members.items():
                    untracked = self.untracked_channels.get(guildid, [])
                    channel = self.bot.get_channel(state.channelid)
                    if (
                        channel
                        and channel.id not in untracked
                        and (not channel.category_id or channel.category_id not in untracked)
                    ):
                        # State is from member in tracked voice channel
                        # Calculate expiry
                        lguild = lguilds[guildid]
                        cap = lguild.config.get('daily_voice_cap').value
                        tracked = tracked_today[(guildid, userid)]
                        if tracked < cap:
                            tomorrow = lguild.today + dt.timedelta(days=1)
                            expiry = now + dt.timedelta(seconds=(cap - tracked))
                            if expiry > tomorrow:
                                expiry = tomorrow + dt.timedelta(seconds=cap)
                            expiries[(guildid, userid)] = expiry

                            hourly_rate = await self._calculate_rate(guildid, userid, state)
                            to_create.append((
                                guildid, userid,
                                state.channelid,
                                now, now,
                                state.stream, state.video,
                                hourly_rate
                            ))
                # Bulk create the ongoing sessions
                if to_create:
                    rows = await self.data.VoiceSessionsOngoing.table.insert_many(
                        ('guildid', 'userid', 'channelid', 'start_time', 'last_update', 'live_stream',
                         'live_video', 'hourly_coins'),
                        *to_create
                    ).with_adapter(self.data.VoiceSessionsOngoing._make_rows)
                    for row in rows:
                        VoiceSession.from_ongoing(self.bot, row, expiries[(row.guildid, row.userid)])
                    logger.info(f"Started {len(rows)} new voice sessions from voice channels!")

    @LionCog.listener("on_voice_state_update")
    @log_wrap(action='Voice Track')
    async def session_voice_tracker(self, member, before, after):
        """
        Spawns the correct tasks from members joining, leaving, and changing live state.
        """
        # TODO: Logging context
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

        # Take tracking lock
        async with self.tracking_lock:
            # Fetch tracked member session state
            session = self.get_session(member.guild.id, member.id)
            tstate = session.state
            untracked = self.untracked_channels.get(member.guild.id, [])

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
                                f"left channel '#{before.channel.name}' <cid:{leaving}> "
                                f"during voice session in channel <cid:{tstate.channelid}>!"
                            )
                        # Close (or cancel) active session
                        logger.info(
                            f"Closing session for member `{member.name}' <uid:{member.id}> "
                            f"in guild '{member.guild.name}' <gid: {member.guild.id}> "
                            " because they left the channel."
                        )
                        await session.close()
                    elif (
                        leaving not in untracked and
                        not (before.channel.category_id and before.channel.category_id in untracked)
                    ):
                        # Leaving tracked channel without an active session?
                        logger.warning(
                            "Voice event does not match session information! "
                            f"Member '{member.name}' <uid:{member.id}> "
                            f"of guild '{member.guild.name}' <gid:{member.guild.id}> "
                            f"left tracked channel '#{before.channel.name}' <cid:{leaving}> "
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
                            f"joined channel '#{after.channel.name}' <cid:{joining}> "
                            f"during voice session in channel <cid:{tstate.channelid}>!"
                        )
                        await session.close()
                    if (
                        joining not in untracked and
                        not (after.channel.category_id and after.channel.category_id in untracked)
                    ):
                        # If the channel they are joining is tracked, schedule a session start for them
                        delay, start, expiry = await self._session_boundaries_for(member.guild.id, member.id)
                        hourly_rate = await self._calculate_rate(member.guild.id, member.id, astate)

                        logger.debug(
                            f"Scheduling voice session for member `{member.name}' <uid:{member.id}> "
                            f"in guild '{member.guild.name}' <gid: member.guild.id> "
                            f"in channel '{after.channel.name}' <cid: {after.channel.id}>. "
                            f"Session will start at {start}, expire at {expiry}, and confirm in {delay}."
                        )
                        await session.schedule_start(delay, start, expiry, astate, hourly_rate)
            elif session.activity:
                # If the channelid did not change, the live state must have
                # Recalculate the economy rate, and update the session
                # Touch the ongoing session with the new state
                hourly_rate = await self._calculate_rate(member.guild.id, member.id, astate)
                await session.update(new_state=astate, new_rate=hourly_rate)

    @LionCog.listener("on_guild_setting_update_untracked_channels")
    async def update_untracked_channels(self, guildid, setting):
        """
        Close sessions in untracked channels, and recalculate previously untracked sessions
        """
        if not self.handle_events:
            return

        async with self.tracking_lock:
            lguild = await self.bot.core.lions.fetch_guild(guildid)
            guild = self.bot.get_guild(guildid)
            if not guild:
                # Left guild while waiting on lock
                return
            cap = lguild.config.get('daily_voice_cap').value
            untracked = self.untracked_channels.get(guildid, [])
            now = utc_now()

            # Iterate through active sessions, close any that are in untracked channels
            active = VoiceSession._active_sessions_.get(guildid, {})
            for session in list(active.values()):
                if session.state.channelid in untracked:
                    await session.close()

            # Iterate through voice members, open new sessions if needed
            expiries = {}
            to_create = []
            for channel in guild.voice_channels:
                if channel.id in untracked:
                    continue
                for member in channel.members:
                    if self.get_session(guildid, member.id).activity:
                        # Already have an active session for this member
                        continue
                    userid = member.id
                    state = TrackedVoiceState.from_voice_state(member.voice)

                    # TODO: Take into account tracked_today time?
                    # TODO: Make a per-guild refresh function to stay DRY
                    tomorrow = lguild.today + dt.timedelta(days=1)
                    expiry = now + dt.timedelta(seconds=cap)
                    if expiry > tomorrow:
                        expiry = tomorrow + dt.timedelta(seconds=cap)
                    expiries[(guildid, userid)] = expiry

                    hourly_rate = await self._calculate_rate(guildid, userid, state)
                    to_create.append((
                        guildid, userid,
                        state.channelid,
                        now, now,
                        state.stream, state.video,
                        hourly_rate
                    ))

            if to_create:
                rows = await self.data.VoiceSessionsOngoing.table.insert_many(
                    ('guildid', 'userid', 'channelid', 'start_time', 'last_update', 'live_stream',
                        'live_video', 'hourly_coins'),
                    *to_create
                ).with_adapter(self.data.VoiceSessionsOngoing._make_rows)
                for row in rows:
                    VoiceSession.from_ongoing(self.bot, row, expiries[(row.guildid, row.userid)])
                    logger.info(
                        f"Started {len(rows)} new voice sessions from voice members "
                        f"in previously untracked channels of guild '{guild.name}' <gid:{guildid}>."
                    )

    @LionCog.listener("on_guild_setting_update_hourly_reward")
    async def update_hourly_reward(self, guildid, setting):
        if not self.handle_events:
            return

        async with self.tracking_lock:
            sessions = VoiceSession._active_sessions_.get(guildid, {})
            for session in list(sessions.values()):
                hourly_rate = await self._calculate_rate(session.guildid, session.userid, session.state)
                await session.update(new_rate=hourly_rate)

    @LionCog.listener("on_guild_setting_update_hourly_live_bonus")
    async def update_hourly_live_bonus(self, guildid, setting):
        if not self.handle_events:
            return

        async with self.tracking_lock:
            sessions = VoiceSession._active_sessions_.get(guildid)
            for session in sessions:
                hourly_rate = await self._calculate_rate(session.guildid, session.userid, session.state)
                await session.update(new_rate=hourly_rate)

    @LionCog.listener("on_guild_setting_update_daily_voice_cap")
    async def update_daily_voice_cap(self, guildid, setting):
        # TODO: Guild daily_voice_cap setting triggers session expiry recalculation for all sessions
        ...

    @LionCog.listener("on_guild_setting_update_timezone")
    @log_wrap(action='Voice Track')
    @log_wrap(action='Timezone Update')
    async def update_timezone(self, guildid, setting):
        # TODO: Guild timezone setting triggers studied_today cache rebuild
        logger.info("Received dispatch event for timezone change!")

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

    async def _session_boundaries_for(self, guildid: int, userid: int) -> tuple[int, dt.datetime, dt.datetime]:
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
        tomorrow = now + dt.timedelta(days=1)

        studied_today = await self.fetch_tracked_today(guildid, userid)
        cap = lguild.config.get('daily_voice_cap').value

        if studied_today >= cap - 90:
            start_time = tomorrow
            delay = (tomorrow - now).total_seconds()
        else:
            start_time = now
            delay = 60

        expiry = start_time + dt.timedelta(seconds=cap)
        if expiry >= tomorrow:
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
            return

        async with self.tracking_lock:
            guildid = guild.id
            lguild = await self.bot.core.lions.fetch_guild(guildid)
            cap = lguild.config.get('daily_voice_cap').value
            untracked = self.untracked_channels.get(guildid, [])
            now = utc_now()

            expiries = {}
            to_create = []
            for channel in guild.voice_channels:
                if channel.id in untracked:
                    continue
                for member in channel.members:
                    userid = member.id
                    state = TrackedVoiceState.from_voice_state(member.voice)

                    tomorrow = lguild.today + dt.timedelta(days=1)
                    expiry = now + dt.timedelta(seconds=cap)
                    if expiry > tomorrow:
                        expiry = tomorrow + dt.timedelta(seconds=cap)
                    expiries[(guildid, userid)] = expiry

                    hourly_rate = await self._calculate_rate(guildid, userid, state)
                    to_create.append((
                        guildid, userid,
                        state.channelid,
                        now, now,
                        state.stream, state.video,
                        hourly_rate
                    ))

            if to_create:
                rows = await self.data.VoiceSessionsOngoing.table.insert_many(
                    ('guildid', 'userid', 'channelid', 'start_time', 'last_update', 'live_stream',
                        'live_video', 'hourly_coins'),
                    *to_create
                ).with_adapter(self.data.VoiceSessionsOngoing._make_rows)
                for row in rows:
                    VoiceSession.from_ongoing(self.bot, row, expiries[(row.guildid, row.userid)])
                    logger.info(
                        f"Started {len(rows)} new voice sessions from voice members "
                        f"in new guild '{guild.name}' <gid:{guildid}>."
                    )

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
                if session.start_task is not None:
                    session.start_task.cancel()
                if session.expiry_task is not None:
                    session.expiry_task.cancel()
                to_close.append(session.guildid, session.userid, now)
            await self.data.VoiceSessionsOngoing.close_voice_sessions_at(*to_close)
            logger.info(
                f"Closed {len(to_close)} voice sessions after leaving guild '{guild.name}' <gid:{guild.id}>"
            )

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
    @cmds.check(low_management)
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

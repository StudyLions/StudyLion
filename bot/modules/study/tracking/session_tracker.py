import asyncio
import discord
import logging
import traceback
from typing import Dict
from collections import defaultdict

from utils.lib import utc_now
from data import tables
from data.conditions import THIS_SHARD
from core import Lion
from meta import client

from ..module import module
from .data import current_sessions, SessionChannelType
from .settings import untracked_channels, hourly_reward, hourly_live_bonus


class Session:
    """
    A `Session` describes an ongoing study session by a single guild member.
    A member is counted as studying when they are in a tracked voice channel.

    This class acts as an opaque interface to the corresponding `sessions` data row.
    """
    __slots__ = (
        'guildid',
        'userid',
        '_expiry_task'
    )
    # Global cache of ongoing sessions
    sessions: Dict[int, Dict[int, 'Session']] = defaultdict(dict)

    # Global cache of members pending session start (waiting for daily cap reset)
    members_pending: Dict[int, Dict[int, asyncio.Task]] = defaultdict(dict)

    def __init__(self, guildid, userid):
        self.guildid = guildid
        self.userid = userid

        self._expiry_task: asyncio.Task = None

    @classmethod
    def get(cls, guildid, userid):
        """
        Fetch the current session for the provided member.
        If there is no current session, returns `None`.
        """
        return cls.sessions[guildid].get(userid, None)

    @classmethod
    def start(cls, member: discord.Member, state: discord.VoiceState):
        """
        Start a new study session for the provided member.
        """
        guildid = member.guild.id
        userid = member.id
        now = utc_now()

        if userid in cls.sessions[guildid]:
            raise ValueError("A session for this member already exists!")

        # If the user is study capped, schedule the session start for the next day
        if (lion := Lion.fetch(guildid, userid)).remaining_study_today <= 10:
            if pending := cls.members_pending[guildid].pop(userid, None):
                pending.cancel()
            task = asyncio.create_task(cls._delayed_start(guildid, userid, member, state))
            cls.members_pending[guildid][userid] = task
            client.log(
                "Member (uid:{}) in (gid:{}) is study capped, "
                "delaying session start for {} seconds until start of next day.".format(
                    userid, guildid, lion.remaining_in_day
                ),
                context="SESSION_TRACKER",
                level=logging.DEBUG
            )
            return

        # TODO: More reliable channel type determination
        if state.channel.id in tables.rented.row_cache:
            channel_type = SessionChannelType.RENTED
        elif state.channel.category and state.channel.category.id == lion.guild_settings.accountability_category.data:
            channel_type = SessionChannelType.ACCOUNTABILITY
        else:
            channel_type = SessionChannelType.STANDARD

        current_sessions.create_row(
            guildid=guildid,
            userid=userid,
            channelid=state.channel.id,
            channel_type=channel_type,
            start_time=now,
            live_start=now if (state.self_video or state.self_stream) else None,
            stream_start=now if state.self_stream else None,
            video_start=now if state.self_video else None,
            hourly_coins=hourly_reward.get(guildid).value,
            hourly_live_coins=hourly_live_bonus.get(guildid).value
        )
        session = cls(guildid, userid).activate()
        client.log(
            "Started session: {}".format(session.data),
            context="SESSION_TRACKER",
            level=logging.DEBUG,
        )

    @classmethod
    async def _delayed_start(cls, guildid, userid, *args):
        delay = Lion.fetch(guildid, userid).remaining_in_day
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            pass
        else:
            cls.start(*args)

    @property
    def key(self):
        """
        RowTable Session identification key.
        """
        return (self.guildid, self.userid)

    @property
    def lion(self):
        """
        The Lion member object associated with this member.
        """
        return Lion.fetch(self.guildid, self.userid)

    @property
    def data(self):
        """
        Row of the `current_sessions` table corresponding to this session.
        """
        return current_sessions.fetch(self.key)

    @property
    def duration(self):
        """
        Current duration of the session.
        """
        return (utc_now() - self.data.start_time).total_seconds()

    @property
    def coins_earned(self):
        """
        Number of coins earned so far.
        """
        data = self.data

        coins = self.duration * data.hourly_coins
        coins += data.live_duration * data.hourly_live_coins
        if data.live_start:
            coins += (utc_now() - data.live_start).total_seconds() * data.hourly_live_coins
        return coins // 3600

    def activate(self):
        """
        Activate the study session.
        This adds the session to the studying members cache,
        and schedules the session expiry, based on the daily study cap.
        """
        # Add to the active cache
        self.sessions[self.guildid][self.userid] = self

        # Schedule the session expiry
        self.schedule_expiry()

        # Return self for easy chaining
        return self

    def schedule_expiry(self):
        """
        Schedule session termination when the user reaches the maximum daily study time.
        """
        asyncio.create_task(self._schedule_expiry())

    async def _schedule_expiry(self):
        # Cancel any existing expiry
        if self._expiry_task and not self._expiry_task.done():
            self._expiry_task.cancel()

        # Wait for the maximum session length
        self._expiry_task = asyncio.create_task(asyncio.sleep(self.lion.remaining_study_today))
        try:
            await self._expiry_task
        except asyncio.CancelledError:
            pass
        else:
            if self.lion.remaining_study_today <= 10:
                # End the session
                # Note that the user will not automatically start a new session when the day starts
                # TODO: Notify user? Disconnect them?
                client.log(
                    "Session for (uid:{}) in (gid:{}) reached daily guild study cap.\n{}".format(
                        self.userid, self.guildid, self.data
                    ),
                    context="SESSION_TRACKER"
                )
                self.finish()
            else:
                # It's possible the expiry time was pushed forwards while waiting
                # If so, reschedule
                self.schedule_expiry()

    def finish(self):
        """
        Close the study session.
        """
        # Note that save_live_status doesn't need to be called here
        # The database saving procedure will account for the values.
        current_sessions.queries.close_study_session(*self.key)

        # Remove session from active cache
        self.sessions[self.guildid].pop(self.userid, None)

        # Cancel any existing expiry task
        if self._expiry_task and not self._expiry_task.done():
            self._expiry_task.cancel()

    def save_live_status(self, state: discord.VoiceState):
        """
        Update the saved live status of the member.
        """
        has_video = state.self_video
        has_stream = state.self_stream
        is_live = has_video or has_stream

        now = utc_now()
        data = self.data

        with data.batch_update():
            # Update video session stats
            if data.video_start:
                data.video_duration += (now - data.video_start).total_seconds()
            data.video_start = now if has_video else None

            # Update stream session stats
            if data.stream_start:
                data.stream_duration += (now - data.stream_start).total_seconds()
            data.stream_start = now if has_stream else None

            # Update overall live session stats
            if data.live_start:
                data.live_duration += (now - data.live_start).total_seconds()
            data.live_start = now if is_live else None


async def session_voice_tracker(client, member, before, after):
    """
    Voice update event dispatcher for study session tracking.
    """
    if member.bot:
        return

    guild = member.guild
    Lion.fetch(guild.id, member.id)
    session = Session.get(guild.id, member.id)

    if before.channel == after.channel:
        # Voice state change without moving channel
        if session and ((before.self_video != after.self_video) or (before.self_stream != after.self_stream)):
            # Live status has changed!
            session.save_live_status(after)
    else:
        # Member changed channel
        # End the current session and start a new one, if applicable
        if session:
            if (scid := session.data.channelid) and (not before.channel or scid != before.channel.id):
                client.log(
                    "The previous voice state for "
                    "member {member.name} (uid:{member.id}) in {guild.name} (gid:{guild.id}) "
                    "does not match their current study session!\n"
                    "Session channel is (cid:{scid}), but the previous channel is {previous}.".format(
                        member=member,
                        guild=member.guild,
                        scid=scid,
                        previous="{0.name} (cid:{0.id})".format(before.channel) if before.channel else "None"
                    ),
                    context="SESSION_TRACKER",
                    level=logging.ERROR
                )
            client.log(
                "Ending study session for {member.name} (uid:{member.id}) "
                "in {member.guild.id} (gid:{member.guild.id}) since they left the voice channel.\n{session}".format(
                    member=member,
                    session=session.data
                ),
                context="SESSION_TRACKER",
                post=False
            )
            # End the current session
            session.finish()
        elif pending := Session.members_pending[guild.id].pop(member.id, None):
            client.log(
                "Cancelling pending study session for {member.name} (uid:{member.id}) "
                "in {member.guild.name} (gid:{member.guild.id}) since they left the voice channel.".format(
                    member=member
                ),
                context="SESSION_TRACKER",
                post=False
            )
            pending.cancel()

        if after.channel:
            blacklist = client.user_blacklist()
            guild_blacklist = client.objects['ignored_members'][guild.id]
            untracked = untracked_channels.get(guild.id).data
            start_session = (
                (after.channel.id not in untracked)
                and (member.id not in blacklist)
                and (member.id not in guild_blacklist)
            )
            if start_session:
                # Start a new session for the member
                client.log(
                    "Starting a new voice channel study session for {member.name} (uid:{member.id}) "
                    "in {member.guild.name} (gid:{member.guild.id}).".format(
                        member=member,
                    ),
                    context="SESSION_TRACKER",
                    post=False
                )
                session = Session.start(member, after)


async def leave_guild_sessions(client, guild):
    """
    `guild_leave` hook.
    Close all sessions in the guild when we leave.
    """
    sessions = list(Session.sessions[guild.id].values())
    for session in sessions:
        session.finish()
    client.log(
        "Left {} (gid:{}) and closed {} ongoing study sessions.".format(guild.name, guild.id, len(sessions)),
        context="SESSION_TRACKER"
    )


async def join_guild_sessions(client, guild):
    """
    `guild_join` hook.
    Refresh all sessions for the guild when we rejoin.
    """
    # Delete existing current sessions, which should have been closed when we left
    # It is possible we were removed from the guild during an outage
    current_sessions.delete_where(guildid=guild.id)

    untracked = untracked_channels.get(guild.id).data
    members = [
        member
        for channel in guild.voice_channels
        for member in channel.members
        if channel.members and channel.id not in untracked and not member.bot
    ]
    for member in members:
        client.log(
            "Starting new session for '{}' (uid: {}) in '{}' (cid: {}) of '{}' (gid: {})".format(
                member.name,
                member.id,
                member.voice.channel.name,
                member.voice.channel.id,
                member.guild.name,
                member.guild.id
            ),
            context="SESSION_TRACKER",
            level=logging.INFO,
            post=False
        )
        Session.start(member, member.voice)

    # Log newly started sessions
    client.log(
        "Joined {} (gid:{}) and started {} new study sessions from current voice channel members.".format(
            guild.name,
            guild.id,
            len(members)
        ),
        context="SESSION_TRACKER",
    )


async def _init_session_tracker(client):
    """
    Load ongoing saved study sessions into the session cache,
    update them depending on the current voice states,
    and attach the voice event handler.
    """
    # Ensure the client caches are ready and guilds are chunked
    await client.wait_until_ready()

    # Pre-cache the untracked channels
    await untracked_channels.launch_task(client)

    # Log init start and define logging counters
    client.log(
        "Loading ongoing study sessions.",
        context="SESSION_INIT",
        level=logging.DEBUG
    )
    resumed = 0
    ended = 0

    # Grab all ongoing sessions from data
    rows = current_sessions.fetch_rows_where(guildid=THIS_SHARD)

    # Iterate through, resume or end as needed
    for row in rows:
        if (guild := client.get_guild(row.guildid)) is not None and row.channelid is not None:
            try:
                # Load the Session
                session = Session(row.guildid, row.userid)

                # Find the channel and member voice state
                voice = None
                if channel := guild.get_channel(row.channelid):
                    voice = next((member.voice for member in channel.members if member.id == row.userid), None)

                # Resume or end as required
                if voice and voice.channel:
                    client.log(
                        "Resuming ongoing session: {}".format(row),
                        context="SESSION_INIT",
                        level=logging.DEBUG
                    )
                    session.activate()
                    session.save_live_status(voice)
                    resumed += 1
                else:
                    client.log(
                        "Ending already completed session: {}".format(row),
                        context="SESSION_INIT",
                        level=logging.DEBUG
                    )
                    session.finish()
                    ended += 1
            except Exception:
                # Fatal error
                client.log(
                    "Fatal error occurred initialising session: {}\n{}".format(row, traceback.format_exc()),
                    context="SESSION_INIT",
                    level=logging.CRITICAL
                )
                module.ready = False
                return

    # Log resumed sessions
    client.log(
        "Resumed {} ongoing study sessions, and ended {}.".format(resumed, ended),
        context="SESSION_INIT",
        level=logging.INFO
    )

    # Now iterate through members of all tracked voice channels
    # Start sessions if they don't already exist
    tracked_channels = [
        channel
        for guild in client.guilds
        for channel in guild.voice_channels
        if channel.members and channel.id not in untracked_channels.get(guild.id).data
    ]
    new_members = [
        member
        for channel in tracked_channels
        for member in channel.members
        if not member.bot and not Session.get(member.guild.id, member.id)
    ]
    for member in new_members:
        client.log(
            "Starting new session for '{}' (uid: {}) in '{}' (cid: {}) of '{}' (gid: {})".format(
                member.name,
                member.id,
                member.voice.channel.name,
                member.voice.channel.id,
                member.guild.name,
                member.guild.id
            ),
            context="SESSION_INIT",
            level=logging.DEBUG
        )
        Session.start(member, member.voice)

    # Log newly started sessions
    client.log(
        "Started {} new study sessions from current voice channel members.".format(len(new_members)),
        context="SESSION_INIT",
        level=logging.INFO
    )

    # Now that we are in a valid initial state, attach the session event handler
    client.add_after_event("voice_state_update", session_voice_tracker)
    client.add_after_event("guild_remove", leave_guild_sessions)
    client.add_after_event("guild_join", join_guild_sessions)


@module.launch_task
async def launch_session_tracker(client):
    """
    Launch the study session initialiser.
    Doesn't block on the client being ready.
    """
    client.objects['sessions'] = Session.sessions
    asyncio.create_task(_init_session_tracker(client))

import asyncio
import discord
import logging
import traceback
from collections import defaultdict

from utils.lib import utc_now
from data import tables
from core import Lion

from ..module import module
from .data import current_sessions, SessionChannelType
from .settings import untracked_channels, hourly_reward, hourly_live_bonus, max_daily_study


class Session:
    """
    A `Session` is a guild member that is currently studying (i.e. that is in a tracked voice channel).
    This class acts as an opaque interface to the corresponding `sessions` data row.
    """
    # TODO: Slots
    sessions = defaultdict(dict)

    def __init__(self, guildid, userid):
        self.guildid = guildid
        self.userid = userid
        self.key = (guildid, userid)

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
        # TODO: Handle daily study cap

        # TODO: More reliable channel type determination
        if state.channel.id in tables.rented.row_cache:
            channel_type = SessionChannelType.RENTED
        elif state.channel.id in tables.accountability_rooms.row_cache:
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
        session = cls(guildid, userid)
        cls.sessions[guildid][userid] = session
        return session

    @property
    def data(self):
        return current_sessions.fetch(self.key)

    def finish(self):
        """
        Close the study session.
        """
        self.sessions[self.guildid].pop(self.userid, None)
        # Note that save_live_status doesn't need to be called here
        # The database saving procedure will account for the values.
        current_sessions.queries.close_study_session(*self.key)

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
        # TODO: Max daily study session tasks
        # TODO: Error if before is None but we have a current session
        if session:
            # End the current session
            session.finish()
        if after.channel:
            blacklist = client.objects['blacklisted_users']
            guild_blacklist = client.objects['ignored_members'][guild.id]
            untracked = untracked_channels.get(guild.id).data
            start_session = (
                (after.channel.id not in untracked)
                and (member.id not in blacklist)
                and (member.id not in guild_blacklist)
            )
            if start_session:
                # Start a new session for the member
                Session.start(member, after)


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
    rows = current_sessions.fetch_rows_where()

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
                    Session.sessions[row.guildid][row.userid] = session
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
        if not Session.get(member.guild.id, member.id)
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


@module.launch_task
async def launch_session_tracker(client):
    """
    Launch the study session initialiser.
    Doesn't block on the client being ready.
    """
    client.objects['sessions'] = Session.sessions
    asyncio.create_task(_init_session_tracker(client))

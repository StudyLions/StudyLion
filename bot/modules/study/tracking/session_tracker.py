import asyncio
import discord
from collections import defaultdict

from utils.lib import utc_now
from ..module import module
from .data import current_sessions
from .settings import untracked_channels, hourly_reward, hourly_live_bonus, max_daily_study


class Session:
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
        # TODO: Calculate channel type
        # TODO: Ensure lion
        current_sessions.create_row(
            guildid=guildid,
            userid=userid,
            channelid=state.channel.id,
            channel_type=None,
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
    await client.wait_until_ready()
    await untracked_channels.launch_task(client)
    client.add_after_event("voice_state_update", session_voice_tracker)


@module.launch_task
async def launch_session_tracker(client):
    """
    Launch the study session initialiser.
    Doesn't block on the client being ready.
    """
    client.objects['sessions'] = Session.sessions
    asyncio.create_task(_init_session_tracker(client))

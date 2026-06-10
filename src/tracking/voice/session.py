from typing import Optional, overload, Literal
from enum import IntEnum
from collections import defaultdict
import datetime as dt
import asyncio

import discord
from cachetools import TTLCache

from utils.lib import utc_now
from meta import LionBot
from data import WeakCache
from .data import VoiceTrackerData

from . import logger, babel

_p = babel._p


class TrackedVoiceState:
    __slots__ = (
        'channelid',
        'video',
        'stream'
    )

    def __init__(self, channelid: Optional[int], video: bool, stream: bool):
        self.channelid = channelid
        self.video = video
        self.stream = stream

    def __eq__(self, other: 'TrackedVoiceState'):
        equal = other.channelid == self.channelid
        equal = equal and other.video == self.video
        equal = equal and other.stream == self.stream

    def __bool__(self):
        """Whether this is an active state"""
        return bool(self.channelid)

    @property
    def live(self):
        return self.video or self.stream

    @classmethod
    def from_voice_state(cls, state: discord.VoiceState):
        if state is not None:
            return cls(
                state.channel.id if state.channel else None,
                state.self_video,
                state.self_stream
            )
        else:
            return cls(None, False, False)


class SessionState(IntEnum):
    ONGOING = 2
    PENDING = 1
    INACTIVE = 0


class VoiceSession:
    """
    High-level tracked voice state in the LionBot paradigm.

    To ensure cache integrity and event safety,
    this state may lag behind the `member.voice` obtained from Discord API.
    However, the state must always match the stored state (in data).
    """
    __slots__ = (
        'bot',
        'guildid', 'userid',
        'registry',
        'start_task', 'expiry_task',
        'data', 'state', 'hourly_rate',
        '_tag', '_start_time',
        'lock',
        '__weakref__'
    )

    _sessions_ = defaultdict(lambda: WeakCache(TTLCache(5000, ttl=60*60)))  # Registry mapping

    # Maintains strong references to active sessions
    _active_sessions_: dict[int, dict[int, 'VoiceSession']] = defaultdict(dict) 

    def __init__(self, bot: LionBot, guildid: int, userid: int, data=None):
        self.bot = bot
        self.guildid = guildid
        self.userid = userid
        self.registry: VoiceTrackerData = self.bot.get_cog('VoiceTrackerCog').data

        self.start_task = None  # Task triggering a delayed session start
        self.expiry_task = None  # Task triggering a session expiry from reaching the daily cap
        self.data: Optional[VoiceTrackerData.VoiceSessionsOngoing] = data  # Ongoing session data

        # TrackedVoiceState set when session is active
        # Must match data when session in ongoing
        self.state: Optional[TrackedVoiceState] = None
        self.hourly_rate: Optional[float] = None
        self._tag = None
        self._start_time = None

        # Member session lock
        # Ensures state changes are atomic and serialised
        self.lock = asyncio.Lock()

    def cancel(self):
        if self.start_task is not None:
            self.start_task.cancel()
        if self.expiry_task is not None:
            self.expiry_task.cancel()
        self._active_sessions_[self.guildid].pop(self.userid, None)

    @property
    def tag(self) -> Optional[str]:
        if self.data:
            tag = self.data.tag
        else:
            tag = self._tag
        return tag

    @property
    def start_time(self):
        if self.data:
            start_time = self.data.start_time
        else:
            start_time = self._start_time
        return start_time

    @property
    def activity(self):
        if self.data is not None:
            return SessionState.ONGOING
        elif self.start_task is not None:
            return SessionState.PENDING
        else:
            return SessionState.INACTIVE

    @overload
    @classmethod
    def get(cls, bot: LionBot, guildid: int, userid: int, create: Literal[False]) -> Optional['VoiceSession']:
        ...

    @overload
    @classmethod
    def get(cls, bot: LionBot, guildid: int, userid: int, create: Literal[True] = True) -> 'VoiceSession':
        ...

    @classmethod
    def get(cls, bot: LionBot, guildid: int, userid: int, create=True) -> Optional['VoiceSession']:
        """
        Fetch the VoiceSession for the given member. Respects cache.
        Creates the session if it doesn't already exist.
        """
        session = cls._sessions_[guildid].get(userid, None)
        if session is None and create:
            session = cls(bot, guildid, userid)
            cls._sessions_[guildid][userid] = session
        return session

    @classmethod
    def from_ongoing(cls, bot: LionBot, data: VoiceTrackerData.VoiceSessionsOngoing, expires_at: dt.datetime):
        """
        Create a VoiceSession from ongoing data and expiry time.
        """
        self = cls.get(bot, data.guildid, data.userid)
        if self.activity:
            raise ValueError("Initialising a session which is already running!")
        self.data = data
        self.state = TrackedVoiceState(data.channelid, data.live_video, data.live_stream)
        self.hourly_rate = data.hourly_coins
        self.schedule_expiry(expires_at)
        self._active_sessions_[self.guildid][self.userid] = self
        return self

    async def set_tag(self, new_tag):
        async with self.lock:
            if self.activity is SessionState.INACTIVE:
                raise ValueError("Cannot set tag on an inactive voice session.")
            self._tag = new_tag
            if self.data is not None:
                await self.data.update(tag=new_tag)

    async def schedule_start(self, delay, start_time, expire_time, state, hourly_rate):
        """
        Schedule the voice session to start at the given target time,
        with the given state and hourly rate.
        """
        self.state = state
        self.hourly_rate = hourly_rate
        self._start_time = start_time
        self._tag = None

        self.start_task = asyncio.create_task(self._start_after(delay, start_time))
        self.schedule_expiry(expire_time)
        self._active_sessions_[self.guildid][self.userid] = self

    async def _start_after(self, delay: int, start_time: dt.datetime):
        """
        Start a new voice session with the given state and hourly rate.

        Creates the tracked_channel if required.
        """
        await asyncio.sleep(delay)

        async with self.lock:
            logger.info(
                f"Starting voice session for member <uid:{self.userid}> in guild <gid:{self.guildid}> "
                f"and channel <cid:{self.state.channelid}>."
            )
            # Create the lion if required
            await self.bot.core.lions.fetch_member(self.guildid, self.userid)

            # Create the tracked channel if required
            await self.registry.TrackedChannel.fetch_or_create(
                self.state.channelid, guildid=self.guildid, deleted=False
            )

            # Insert an ongoing_session with the correct state, set data
            state = self.state
            self.data = await self.registry.VoiceSessionsOngoing.create(
                guildid=self.guildid,
                userid=self.userid,
                channelid=state.channelid,
                start_time=start_time,
                last_update=start_time,
                live_stream=state.stream,
                live_video=state.video,
                hourly_coins=self.hourly_rate,
                tag=self._tag
            )
            self.bot.dispatch('voice_session_start', self.data)
            self.start_task = None

    def schedule_expiry(self, expire_time):
        """
        (Re-)schedule expiry for an ongoing session.
        """
        if not self.activity:
            raise ValueError("Cannot schedule expiry for an inactive session!")
        if self.expiry_task is not None and not self.expiry_task.done():
            self.expiry_task.cancel()

        delay = (expire_time - utc_now()).total_seconds()
        self.expiry_task = asyncio.create_task(self._expire_after(delay))

    async def update(self, new_state: Optional[TrackedVoiceState] = None, new_rate: Optional[int] = None):
        """
        Update the session state with the provided voice state or hourly rate.
        Also applies to pending states.

        Raises ValueError if the state does not match the saved session (i.e. wrong channel)
        """
        if not self.activity:
            raise ValueError("Cannot update inactive session!")
        elif (new_state is not None and new_state != self.state) or (new_rate != self.hourly_rate):
            if new_state is not None:
                self.state = new_state
            if new_rate is not None:
                self.hourly_rate = new_rate

            if self.data:
                await self.data.update_voice_session_at(
                    guildid=self.guildid,
                    userid=self.userid,
                    _at=utc_now(),
                    stream=self.state.stream,
                    video=self.state.video,
                    rate=self.hourly_rate
                )

    async def _expire_after(self, delay: int):
        """
        Expire a session which has exceeded the daily voice cap.
        """
        # TODO: Logging, and guild logging, and user notification (?)
        await asyncio.sleep(delay)
        logger.info(
            f"Expiring voice session for member <uid:{self.userid}> in guild <gid:{self.guildid}> "
            f"and channel <cid:{self.state.channelid}>."
        )
        async with self.lock:
            # --- AI-MODIFIED (2026-06-10) ---
            # Purpose: Remember whether this expiry actually ended an ongoing session,
            #   so we can notify the member below (tickets #0098, #0112: members had no
            #   idea why their time silently stopped counting until guild midnight).
            was_ongoing = self.activity is SessionState.ONGOING and self.data is not None
            # --- END AI-MODIFIED ---
            await self._close()

            if self.activity:
                t = self.bot.translator.t
                lguild = await self.bot.core.lions.fetch_guild(self.guildid)
                if self.activity is SessionState.ONGOING and self.data is not None:
                    lguild.log_event(
                        t(_p(
                            'eventlog|event:voice_session_expired|title',
                            "Member Voice Session Expired"
                        )),
                        t(_p(
                            'eventlog|event:voice_session_expired|desc',
                            "{member}'s voice session in {channel} expired "
                            "because they reached the daily voice cap."
                        )).format(
                            member=f"<@{self.userid}>",
                            channel=f"<#{self.state.channelid}>",
                        ),
                        start=discord.utils.format_dt(self.data.start_time),
                        coins_earned=int(self.data._total_coins_earned),
                    )

            if self.start_task is not None:
                self.start_task.cancel()
                self.start_task = None

            self.data = None

            cog = self.bot.get_cog('VoiceTrackerCog')
            delay, start, expiry = await cog._session_boundaries_for(self.guildid, self.userid)
            hourly_rate = await cog._calculate_rate(self.guildid, self.userid, self.state)

            self.hourly_rate = hourly_rate
            self._start_time = start

            self.start_task = asyncio.create_task(self._start_after(delay, start))
            self.schedule_expiry(expiry)

            # --- AI-MODIFIED (2026-06-10) ---
            # Purpose: Implement the user-notification TODO above (tickets #0098, #0112).
            #   When the expiry genuinely capped an ongoing session (the recomputed next
            #   start is deferred to the next guild day rather than restarting in ~20s),
            #   DM the member so they know why tracking stopped and when it resumes.
            #   Fire-and-forget OUTSIDE this lock; every failure is swallowed so the
            #   expiry/restart flow can never be affected.
            if was_ongoing and delay > 60:
                try:
                    asyncio.create_task(self._notify_cap_reached(start))
                except Exception:
                    logger.debug(
                        "Failed to schedule daily-cap notification "
                        f"for <uid:{self.userid}> in <gid:{self.guildid}>.",
                        exc_info=True
                    )
            # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-06-10) ---
    # Purpose: New helper for the daily-cap notification (tickets #0098, #0112).
    #   Sends a single DM when a member's voice session expires from reaching the
    #   guild's daily voice cap, including when tracking resumes (as Discord
    #   timestamps, so the time renders in the member's own timezone).
    #   Best-effort only: closed DMs and any other failure are silently ignored.
    async def _notify_cap_reached(self, resume_at: dt.datetime):
        try:
            user = self.bot.get_user(self.userid)
            if user is None:
                return

            lguild = await self.bot.core.lions.fetch_guild(self.guildid)
            guild = self.bot.get_guild(self.guildid)
            t = self.bot.translator.t

            cap_setting = lguild.config.get('daily_voice_cap')
            try:
                cap_formatted = cap_setting.formatted
            except Exception:
                cap_formatted = None
            if not cap_formatted:
                hours = (cap_setting.value or 0) // 3600
                cap_formatted = t(_p(
                    'voice_session|cap_notify|cap_fallback',
                    "{hours} hours"
                )).format(hours=hours)

            embed = discord.Embed(
                colour=discord.Colour.orange(),
                title=t(_p(
                    'voice_session|cap_notify|title',
                    "Daily voice limit reached"
                )),
                description=t(_p(
                    'voice_session|cap_notify|desc',
                    "You have reached the daily voice activity limit of {cap} in **{guild_name}**, "
                    "so the rest of your voice time there today will not be counted.\n"
                    "Tracking resumes {resume_relative} (at {resume_time})."
                )).format(
                    cap=cap_formatted,
                    guild_name=guild.name if guild else t(_p(
                        'voice_session|cap_notify|guild_fallback',
                        "the server"
                    )),
                    resume_relative=discord.utils.format_dt(resume_at, style='R'),
                    resume_time=discord.utils.format_dt(resume_at, style='t'),
                )
            )
            embed.set_footer(text=t(_p(
                'voice_session|cap_notify|footer',
                "This limit is configured by the server admins."
            )))
            await user.send(embed=embed)
        except discord.HTTPException:
            # DMs closed, or user unreachable. Nothing to do.
            pass
        except Exception:
            logger.debug(
                f"Unexpected error sending daily-cap notification to <uid:{self.userid}> "
                f"for guild <gid:{self.guildid}>.",
                exc_info=True
            )
    # --- END AI-MODIFIED ---

    async def close(self):
        """
        Close the session, or cancel the pending session. Idempotent.
        """
        async with self.lock:
            await self._close()
            if self.activity:
                t = self.bot.translator.t
                lguild = await self.bot.core.lions.fetch_guild(self.guildid)
                if self.activity is SessionState.ONGOING and self.data is not None:
                    lguild.log_event(
                        t(_p(
                            'eventlog|event:voice_session_closed|title',
                            "Member Voice Session Ended"
                        )),
                        t(_p(
                            'eventlog|event:voice_session_closed|desc',
                            "{member} completed their voice session in {channel}."
                        )).format(
                            member=f"<@{self.userid}>",
                            channel=f"<#{self.state.channelid}>",
                        ),
                        start=discord.utils.format_dt(self.data.start_time),
                        coins_earned=int(self.data._total_coins_earned),
                    )
                else:
                    lguild.log_event(
                        t(_p(
                            'eventlog|event:voice_session_cancelled|title',
                            "Member Voice Session Cancelled"
                        )),
                        t(_p(
                            'eventlog|event:voice_session_cancelled|desc',
                            "{member} left {channel} before their voice session started."
                        )).format(
                            member=f"<@{self.userid}>",
                            channel=f"<#{self.state.channelid}>",
                        ),
                    )

            if self.start_task is not None:
                self.start_task.cancel()
                self.start_task = None

            if self.expiry_task is not None:
                self.expiry_task.cancel()
                self.expiry_task = None

            self.data = None
            self.state = None
            self.hourly_rate = None
            self._tag = None
            self._start_time = None

            # Always release strong reference to session (to allow garbage collection)
            self._active_sessions_[self.guildid].pop(self.userid)

    async def _close(self):
        if self.activity is SessionState.ONGOING:
            # End the ongoing session
            now = utc_now()
            await self.data.close_study_session_at(self.guildid, self.userid, now)

            # TODO: Something a bit saner/safer.. dispatch the finished session instead?
            self.bot.dispatch('voice_session_end', self.data, now)

            # Rank update
            # TODO: Change to broadcasted event?
            rank_cog = self.bot.get_cog('RankCog')
            if rank_cog is not None:
                asyncio.create_task(rank_cog.on_voice_session_complete(
                    (self.guildid, self.userid, int((utc_now() - self.data.start_time).total_seconds()), 0)
                ))

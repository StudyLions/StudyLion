from typing import Optional, TYPE_CHECKING
from collections import defaultdict
import datetime as dt
import asyncio

import discord

from meta import LionBot
from meta.sharding import THIS_SHARD
from meta.logger import log_context, log_wrap
from utils.lib import utc_now
from core.lion_member import LionMember
from core.lion_guild import LionGuild
from tracking.voice.session import SessionState
from utils.data import as_duration, MEMBERS, TemporaryTable
from utils.ratelimits import Bucket
from modules.economy.cog import Economy
from modules.economy.data import EconomyData, TransactionType

from .. import babel, logger
from ..data import ScheduleData as Data
from ..lib import slotid_to_utc, batchrun_per_second, limit_concurrency
from ..settings import ScheduleSettings

from .session import ScheduledSession
from .session_member import SessionMember

if TYPE_CHECKING:
    from ..cog import ScheduleCog

_p = babel._p


class TimeSlot:
    """
    Represents a single schedule session timeslot.

    Maintains a cache of ScheduleSessions for event handling.
    Responsible for the state of all scheduled sessions in this timeslot.
    Provides methods for executing each stage of the time slot,
    performing operations concurrently where possible.
    """
    # TODO: Logging context
    # TODO: Add per-shard jitter to improve ratelimit handling

    def __init__(self, cog: 'ScheduleCog', slot_data: Data.ScheduleSlot):
        self.cog = cog
        self.bot: LionBot = cog.bot
        self.data: Data = cog.data
        self.slot_data = slot_data
        self.slotid = slot_data.slotid
        log_context.set(f"slotid: {self.slotid}")

        self.prep_at = slotid_to_utc(self.slotid - 15*60)
        self.start_at = slotid_to_utc(self.slotid)
        self.end_at = slotid_to_utc(self.slotid + 3600)

        self.preparing = asyncio.Event()
        self.opening = asyncio.Event()
        self.opened = asyncio.Event()
        self.closing = asyncio.Event()

        self.sessions: dict[int, ScheduledSession] = {}  # guildid -> loaded ScheduledSession
        self.run_task = None
        self.loaded = False

    def __repr__(self):
        if self.closing.is_set():
            state = 'closing'
        elif self.opened.is_set():
            state = 'opened'
        elif self.opening.is_set():
            state = 'opening'
        elif self.preparing.is_set():
            state = 'preparing'
        elif self.loaded:
            state = 'loaded'
        else:
            state = 'unloaded'

        if self.run_task:
            if self.run_task.cancelled():
                running = 'Cancelled'
            elif self.run_task.done():
                running = 'Done'
            else:
                running = 'Running'
        else:
            running = 'None'

        return (
            "<TimeSlot "
            f"slotid={self.slotid} "
            f"state='{state}' "
            f"sessions={len(self.sessions)} "
            f"members={sum(len(s.members) for s in self.sessions.values())} "
            f"loaded={self.loaded} "
            f"run_task='{running}'"
            ">"
        )

    @log_wrap(action="Fetch sessions")
    async def fetch(self):
        """
        Load all slot sessions from data. Must be executed before reading event based updates.

        Does not take session lock because nothing external should read or modify before load.
        """
        self.loaded = False
        self.sessions.clear()
        session_data = await self.data.ScheduleSession.fetch_where(
            THIS_SHARD,
            slotid=self.slotid,
            closed_at=None,
        )
        sessions = await self.load_sessions(session_data)
        self.sessions.update(sessions)
        self.loaded = True
        logger.info(
            f"Timeslot {self!r}> finished preloading {len(self.sessions)} guilds. Ready to open."
        )

    @log_wrap(action="Load sessions")
    async def load_sessions(self, session_data) -> dict[int, ScheduledSession]:
        """
        Load slot state for the provided GuildSchedule rows.
        """
        if not session_data:
            return {}

        guildids = [row.guildid for row in session_data]

        # Bulk fetch guild config data
        config_data = await self.data.ScheduleGuild.fetch_multiple(*guildids)

        # Fetch channel data. This *should* hit cache if initialisation did its job
        channel_settings = {guildid: await ScheduleSettings.SessionChannels.get(guildid) for guildid in guildids}

        # Data fetch all member schedules with this slotid
        members = await self.data.ScheduleSessionMember.fetch_where(
            slotid=self.slotid,
            guildid=guildids
        )
        # Bulk fetch lions
        lions = await self.bot.core.lions.fetch_members(
            *((m.guildid, m.userid) for m in members)
        ) if members else {}

        # Partition member data
        session_member_data = defaultdict(list)
        for mem in members:
            session_member_data[mem.guildid].append(mem)

        # Create the session guilds and session members.
        sessions = {}
        for row in session_data:
            session = ScheduledSession(self.bot, row, config_data[row.guildid], channel_settings[row.guildid])
            smembers = {}
            for memdata in session_member_data[row.guildid]:
                smember = SessionMember(
                    self.bot, memdata, lions[memdata.guildid, memdata.userid]
                )
                smembers[memdata.userid] = smember
                session.members = smembers
            sessions[row.guildid] = session

        logger.debug(
            f"Timeslot {self!r} "
            f"loaded guild data for {len(sessions)} guilds: {', '.join(map(str, guildids))}"
        )
        return sessions

    @log_wrap(action="Reset Clocks")
    async def _reset_clocks(self, sessions: list[ScheduledSession]):
        """
        Accurately set clocks (i.e. attendance time) for all tracked members in this time slot.
        """
        now = utc_now()
        tracker = self.bot.get_cog('VoiceTrackerCog')
        tracking_lock = tracker.tracking_lock
        session_locks = [session.lock for session in sessions]

        # Take the tracking lock so that sessions are not started/finished while we reset the clock
        try:
            await tracking_lock.acquire()
            [await lock.acquire() for lock in session_locks]
            if now > self.start_at + dt.timedelta(minutes=5):
                # Set initial clocks based on session data
                # First request sessions intersection with the timeslot
                memberids = [
                    (sm.data.guildid, sm.data.userid)
                    for sg in sessions for sm in sg.members.values()
                ]
                session_map = {session.guildid: session for session in sessions}
                model = tracker.data.VoiceSessions
                if memberids:
                    voice_sessions = await model.table.select_where(
                        MEMBERS(*memberids),
                        model.start_time < self.end_at,
                        model.start_time + as_duration(model.duration) > self.start_at
                    ).select(
                        'guildid', 'userid', 'start_time', 'channelid',
                        end_time=model.start_time + as_duration(model.duration)
                    ).with_no_adapter()
                else:
                    voice_sessions = []

                # Intersect and aggregate sessions, accounting for session channels
                clocks = defaultdict(int)
                for vsession in voice_sessions:
                    if session_map[vsession['guildid']].validate_channel(vsession['channelid']):
                        start = max(vsession['start_time'], self.start_at)
                        end = min(vsession['end_time'], self.end_at)
                        clocks[(vsession['guildid'], vsession['userid'])] += (end - start).total_seconds()

                # Now write clocks
                for sg in sessions:
                    for sm in sg.members.values():
                        sg.clock = clocks[(sm.guildid, sm.userid)]

            # Mark current attendance using current voice session
            for session in sessions:
                for smember in session.members.values():
                    voice_session = tracker.get_session(smember.data.guildid, smember.data.userid)
                    smember.clock_start = None
                    if voice_session is not None and voice_session.activity is SessionState.ONGOING:
                        if session.validate_channel(voice_session.data.channelid):
                            smember.clock_start = max(voice_session.data.start_time, self.start_at)
                session.listening = True
        finally:
            tracking_lock.release()
            [lock.release() for lock in session_locks]

    @log_wrap(action="Prepare Sessions")
    async def prepare(self, sessions: list[ScheduledSession]):
        """
        Bulk prepare ScheduledSessions for the upcoming timeslot.

        Preparing means sending the initial message and adding permissions for the next members.
        This does not take the session lock for setting perms, because this is race-safe
        (aside from potentially leaving extra permissions, which will be overwritten by `open`).
        """
        logger.debug(f"Running prepare for time slot: {self!r}")
        try:
            bucket = Bucket(5, 1)
            coros = [bucket.wrapped(session.prepare(save=False)) for session in sessions if session.can_run]
            async for task in limit_concurrency(coros, 5):
                await task

            # Save messageids
            tmptable = TemporaryTable(
                '_gid', '_sid', '_mid',
                types=('BIGINT', 'INTEGER', 'BIGINT')
            )
            tmptable.values = [
                (sg.data.guildid, sg.data.slotid, sg.messageid)
                for sg in sessions
                if sg.messageid is not None
            ]
            if tmptable.values:
                await Data.ScheduleSession.table.update_where(
                    guildid=tmptable['_gid'], slotid=tmptable['_sid']
                ).set(
                    messageid=tmptable['_mid']
                ).from_expr(tmptable)
        except Exception:
            logger.exception(
                f"Unhandled exception while preparing timeslot: {self!r}"
            )
        else:
            logger.info(
                f"Prepared {len(sessions)} for scheduled session timeslot: {self!r}"
            )

    @log_wrap(action="Open Sessions")
    async def open(self, sessions: list[ScheduledSession]):
        """
        Bulk open guild sessions.

        If session opens "late", uses voice session statistics to calculate clock times.
        Otherwise, uses member's current sessions.

        Due to the bulk channel update, this method may take up to 5 or 10 minutes.
        """
        try:
            # List of sessions which have not been previously opened
            # Used so that we only set channel permissions and notify and write opened once
            fresh = [session for session in sessions if session.data.opened_at is None]

            # Calculate the attended time so far, referencing voice session data if required
            await self._reset_clocks(sessions)

            # Bulk update lobby messages
            message_tasks = [
                asyncio.create_task(session.update_status(save=False))
                for session in sessions
                if session.lobby_channel is not None
            ]
            notify_tasks = [
                asyncio.create_task(session.notify())
                for session in fresh
                if session.lobby_channel is not None and session.data.opened_at is None
            ]

            # Start lobby update loops
            for session in sessions:
                session.start_updating()

            # Bulk run guild open to open session rooms
            bucket = Bucket(5, 1)
            voice_coros = [
                bucket.wrapped(session.open_room())
                for session in fresh
                if session.room_channel is not None and session.data.opened_at is None
            ]
            async for task in limit_concurrency(voice_coros, 5):
                await task
            await asyncio.gather(*message_tasks)
            await asyncio.gather(*notify_tasks)

            # Write opened
            if fresh:
                now = utc_now()
                tmptable = TemporaryTable(
                    '_gid', '_sid', '_mid', '_open',
                    types=('BIGINT', 'INTEGER', 'BIGINT', 'TIMESTAMPTZ')
                )
                tmptable.values = [
                    (sg.data.guildid, sg.data.slotid, sg.messageid, now)
                    for sg in fresh
                ]
                await Data.ScheduleSession.table.update_where(
                    guildid=tmptable['_gid'], slotid=tmptable['_sid']
                ).set(
                    messageid=tmptable['_mid'],
                    opened_at=tmptable['_open']
                ).from_expr(tmptable)
        except Exception:
            logger.exception(
                f"Unhandled exception while opening sessions for timeslot: {self!r}"
            )
        else:
            logger.info(
                f"Opened {len(sessions)} sessions for scheduled session timeslot: {self!r}"
            )

    @log_wrap(action="Close Sessions")
    async def close(self, sessions: list[ScheduledSession], consequences=False):
        """
        Close the session.

        Responsible for saving the member attendance, performing economy updates,
        closing the guild sessions, and if `consequences` is set,
        cancels future member sessions and blacklists members as required.
        Also performs the last lobby message update for this timeslot.

        Does not modify session room channels (responsibility of the next open).
        """
        try:
            conn = await self.bot.db.get_connection()
            async with conn.transaction():
                # Calculate rewards
                rewards = []
                attendance = []
                did_not_show = []
                for session in sessions:
                    bonus = session.bonus_reward * session.all_attended
                    reward = session.attended_reward + bonus
                    required = session.min_attendence
                    for member in session.members.values():
                        guildid = member.guildid
                        userid = member.userid
                        attended = (member.total_clock >= required)
                        if attended:
                            rewards.append(
                                (TransactionType.SCHEDULE_REWARD,
                                    guildid, self.bot.user.id,
                                    0, userid,
                                    reward, 0,
                                    None)
                            )
                        else:
                            did_not_show.append((guildid, userid))

                        attendance.append(
                            (self.slotid, guildid, userid, attended, member.total_clock)
                        )

                # Perform economy transactions
                economy: Economy = self.bot.get_cog('Economy')
                transactions = await economy.data.Transaction.execute_transactions(*rewards)
                reward_ids = {
                    (t.guildid, t.to_account): t.transactionid
                    for t in transactions
                }

                # Update lobby messages
                message_tasks = [
                    asyncio.create_task(session.update_status(save=False))
                    for session in sessions
                    if session.lobby_channel is not None
                ]
                await asyncio.gather(*message_tasks)

                # Save attendance
                if attendance:
                    att_table = TemporaryTable(
                        '_sid', '_gid', '_uid', '_att', '_clock', '_reward',
                        types=('INTEGER', 'BIGINT', 'BIGINT', 'BOOLEAN', 'INTEGER', 'INTEGER')
                    )
                    att_table.values = [
                        (sid, gid, uid, att, clock, reward_ids.get((gid, uid), None))
                        for sid, gid, uid, att, clock in attendance
                    ]
                    await self.data.ScheduleSessionMember.table.update_where(
                        slotid=att_table['_sid'],
                        guildid=att_table['_gid'],
                        userid=att_table['_uid'],
                    ).set(
                        attended=att_table['_att'],
                        clock=att_table['_clock'],
                        reward_transactionid=att_table['_reward']
                    ).from_expr(att_table)

                # Mark guild sessions as closed
                if sessions:
                    await self.data.ScheduleSession.table.update_where(
                        slotid=self.slotid,
                        guildid=list(session.guildid for session in sessions)
                    ).set(closed_at=utc_now())

            if consequences and did_not_show:
                # Trigger blacklist and cancel member bookings as needed
                await self.cog.handle_noshow(*did_not_show)
        except Exception:
            logger.exception(
                f"Unhandled exception while closing sessions for timeslot: {self!r}"
            )
        else:
            logger.info(
                f"Closed {len(sessions)} for scheduled session timeslot: {self!r}"
            )

    def launch(self) -> asyncio.Task:
        self.run_task = asyncio.create_task(self.run())
        return self.run_task

    @log_wrap(action="TimeSlot Run")
    async def run(self):
        """
        Execute each stage of the scheduled timeslot.

        Skips preparation if the open time has passed.
        """
        if not self.loaded:
            raise ValueError("Attempting to run a Session before loading.")

        try:
            now = utc_now()
            if now < self.start_at:
                await discord.utils.sleep_until(self.prep_at)
                self.preparing.set()
                logger.info(f"Active timeslot preparing. {self!r}")
                await self.prepare(list(self.sessions.values()))
                logger.info(f"Active timeslot prepared. {self!r}")
                await discord.utils.sleep_until(self.start_at)
            else:
                self.preparing.set()

            self.opening.set()
            logger.info(f"Active timeslot opening. {self!r}")
            await self.open(list(self.sessions.values()))
            logger.info(f"Active timeslot opened. {self!r}")
            self.opened.set()
            await discord.utils.sleep_until(self.end_at)
            self.closing.set()
            logger.info(f"Active timeslot closing. {self!r}")
            await self.close(list(self.sessions.values()), consequences=True)
            logger.info(f"Active timeslot closed. {self!r}")
        except asyncio.CancelledError:
            logger.info(
                f"Deactivating active time slot: {self!r}"
            )
        except Exception:
            logger.exception(
                f"Unexpected exception occurred while running active time slot: {self!r}."
            )

    @log_wrap(action="Slot Cleanup")
    async def cleanup(self, sessions: list[ScheduledSession]):
        """
        Cleanup after "missed" ScheduledSessions.

        Missed sessions are unclosed sessions which are already past their closed time.
        If the sessions were opened, they will be closed (with no consequences).
        If the sessions were not opened, they will be cancelled (and the bookings refunded).
        """
        now = utc_now()
        if now < self.end_at:
            raise ValueError("Attempting to cleanup sessions in current timeslot. Use close() or cancel() instead.")

        # Split provided sessions into ignore/close/cancel
        to_close = []
        to_cancel = []
        for session in sessions:
            if session.slotid != self.slotid:
                raise ValueError(f"Timeslot {self.slotid} attempting to cleanup session with slotid {session.slotid}")

            if session.data.closed_at is not None:
                # Already closed, ignore
                pass
            elif session.data.opened_at is not None:
                # Session was opened, request close
                to_close.append(session)
            else:
                # Session was never opened, request cancel
                to_cancel.append(session)

        # Handle close
        if to_close:
            await self._reset_clocks(to_close)
            await self.close(to_close, consequences=False)

        # Handle cancel
        if to_cancel:
            await self.cancel(to_cancel)

    @log_wrap(action="Cancel TimeSlot")
    async def cancel(self, sessions: list[ScheduledSession]):
        """
        Cancel the provided sessions.

        This involves refunding the booking transactions, deleting the booking rows,
        and updating any messages that may have been posted.
        """
        conn = await self.bot.db.get_connection()
        async with conn.transaction():
            # Collect booking rows
            bookings = [member.data for session in sessions for member in session.members.values()]

            if bookings:
                # Refund booking transactions
                economy: Economy = self.bot.get_cog('Economy')
                maybe_tids = (r.book_transactionid for r in bookings)
                tids = [tid for tid in maybe_tids if tid is not None]
                await economy.data.Transaction.refund_transactions(*tids)

                # Delete booking rows
                await self.data.ScheduleSessionMember.table.delete_where(
                    MEMBERS(*((r.guildid, r.userid) for r in bookings)),
                    slotid=self.slotid,
                )

            # Trigger message update for existent messages
            lobby_tasks = [
                asyncio.create_task(session.update_status(save=False, resend=False))
                for session in sessions
            ]
            await asyncio.gather(*lobby_tasks)

            # Mark sessions as closed
            await self.data.ScheduleSession.table.update_where(
                slotid=self.slotid,
                guildid=[session.guildid for session in sessions]
            ).set(
                closed_at=utc_now()
            )
            # TODO: Logging

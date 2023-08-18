from typing import Optional
from weakref import WeakValueDictionary
import datetime as dt
from collections import defaultdict
import asyncio

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.app_commands import Range

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.errors import UserInputError, ResponseTimedOut
from meta.sharding import THIS_SHARD
from utils.lib import utc_now, error_embed
from utils.ui import Confirm
from utils.data import MULTIVALUE_IN, MEMBERS
from wards import low_management_ward
from core.data import CoreData
from data import NULL, ORDER
from modules.economy.data import TransactionType
from constants import MAX_COINS

from . import babel, logger
from .data import ScheduleData
from .settings import ScheduleSettings, ScheduleConfig
from .ui.scheduleui import ScheduleUI
from .ui.settingui import ScheduleSettingUI
from .core import TimeSlot, ScheduledSession, SessionMember
from .lib import slotid_to_utc, time_to_slotid

_p, _np = babel._p, babel._np


class ScheduleCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data: ScheduleData = bot.db.load_registry(ScheduleData())
        self.settings = ScheduleSettings()

        # Whether we are ready to take events
        self.initialised = asyncio.Event()

        # Activated slot cache
        self.active_slots: dict[int, TimeSlot] = {}  # slotid -> TimeSlot

        # External modification (including spawing) a slot requires holding a slot lock
        self._slot_locks = WeakValueDictionary()

        # Modifying a non-running slot or session requires holding the spawn lock
        # This ensures the slot will not start while being modified
        self.spawn_lock = asyncio.Lock()

        # Spawner loop task
        self.spawn_task: Optional[asyncio.Task] = None

        self.session_channels = self.settings.SessionChannels._cache

    @property
    def nowid(self):
        now = utc_now()
        return time_to_slotid(now)

    async def cog_load(self):
        await self.data.init()

        # Update the session channel cache
        await self.settings.SessionChannels.setup(self.bot)

        configcog = self.bot.get_cog('ConfigCog')
        self.crossload_group(self.configure_group, configcog.configure_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        """
        Cancel session spawning and the ongoing sessions.
        """
        # TODO: Test/design for reload
        if self.spawn_task and not self.spawn_task.done():
            self.spawn_task.cancel()

        for slot in list(self.active_slots.values()):
            if slot.run_task and not slot.run_task.done():
                slot.run_task.cancel()
            for session in slot.sessions.values():
                if session._updater and not session._updater.done():
                    session._updater.cancel()
                if session._status_task and not session._status_task.done():
                    session._status_task.cancel()

    @LionCog.listener('on_ready')
    @log_wrap(action='Init Schedule')
    async def initialise(self):
        """
        Launch current timeslots, cleanup missed timeslots, and start the spawner.
        """
        # Wait until voice session tracker has initialised
        tracker = self.bot.get_cog('VoiceTrackerCog')
        await tracker.initialised.wait()

        # Spawn the current session
        now = utc_now()
        nowid = time_to_slotid(now)
        await self._spawner(nowid)

        # Start the spawner, with a small jitter based on shard id (for db loading)
        spawn_start = now.replace(minute=30, second=0, microsecond=0)
        spawn_start += dt.timedelta(seconds=self.bot.shard_id * 10)
        self.spawn_task = asyncio.create_task(self._spawn_loop(start_at=spawn_start))

        # Cleanup after missed or delayed timeslots
        model = self.data.ScheduleSession
        missed_session_data = await model.fetch_where(
            model.slotid < nowid,
            model.slotid > (nowid - 24 * 60 * 60),
            model.closed_at == NULL,
            THIS_SHARD
        )
        if missed_session_data:
            # Partition by slotid
            slotid_session_data = defaultdict(list)
            for row in missed_session_data:
                slotid_session_data[row.slotid].append(row)

            # Fetch associated TimeSlots, oldest first
            slot_data = await self.data.ScheduleSlot.fetch_where(
                slotid=list(slotid_session_data.keys())
            ).order_by('slotid')

            # Process each slot
            for row in slot_data:
                try:
                    slot = TimeSlot(self, row)
                    sessions = await slot.load_sessions(slotid_session_data[slot.slotid])
                    await slot.cleanup(list(sessions.values()))
                except Exception:
                    logger.exception(
                        f"Unhandled exception while cleaning up missed timeslot {row!r}"
                    )
        self.initialised.set()

    @log_wrap(stack=['Schedule Spawner'])
    async def _spawn_loop(self, start_at: dt.datetime):
        """
        Every hour, starting at start_at,
        the spawn loop will use `_spawner` to ensure the next slotid has been launched.
        """
        logger.info(f"Started scheduled session spawner at {start_at}")
        next_spawn = start_at
        while True:
            try:
                await discord.utils.sleep_until(next_spawn)
            except asyncio.CancelledError:
                break
            next_spawn = next_spawn + dt.timedelta(hours=1)
            try:
                nextid = time_to_slotid(next_spawn)
                await self._spawner(nextid)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Unexpected error occurred while spawning scheduled sessions."
                )

    @log_wrap(action='Spawn')
    async def _spawner(self, slotid):
        """
        Ensure the provided slotid exists and is running.
        """
        async with self.slotlock(slotid):
            slot = self.active_slots.get(slotid, None)
            if slot is None or slot.run_task is None:
                slot_data = await self.data.ScheduleSlot.fetch_or_create(slotid)
                slot = TimeSlot(self, slot_data)
                await slot.fetch()
                self.active_slots[slotid] = slot
                self._launch(slot)
                logger.info(f"Spawned Schedule TimeSlot <slotid: {slotid}>")

    def _launch(self, slot: TimeSlot):
        launch_task = slot.launch()
        key = slot.slotid
        launch_task.add_done_callback(lambda fut: self.active_slots.pop(key, None))

    # API
    def slotlock(self, slotid):
        lock = self._slot_locks.get(slotid, None)
        if lock is None:
            lock = self._slot_locks[slotid] = asyncio.Lock()
        logger.debug(f"Getting slotlock <slotid: {slotid}> (locked: {lock.locked()})")
        return lock

    @log_wrap(action='Cancel Booking')
    async def cancel_bookings(self, *bookingids: tuple[int, int, int], refund=True):
        """
        Cancel the provided bookings.

        bookingid: tuple[int, int, int]
            Tuple of (slotid, guildid, userid)
        """
        slotids = set(bookingid[0] for bookingid in bookingids)
        logger.debug(
            "Cancelling bookings: " + ', '.join(map(str, bookingids))
        )

        # Request all relevant slotlocks
        locks = [self.slotlock(slotid) for slotid in sorted(slotids)]

        try:
            [await lock.acquire() for lock in locks]
            # TODO: Some benchmarking here
            # Should we do the channel updates in bulk?
            for bookingid in bookingids:
                await self._cancel_booking_active(*bookingid)

            conn = await self.bot.db.get_connection()
            async with conn.transaction():
                # Now delete from data
                records = await self.data.ScheduleSessionMember.table.delete_where(
                    MULTIVALUE_IN(
                        ('slotid', 'guildid', 'userid'),
                        *bookingids
                    )
                )

                # Refund cancelled bookings
                if refund:
                    maybe_tids = (record['book_transactionid'] for record in records)
                    tids = [tid for tid in maybe_tids if tid is not None]
                    if tids:
                        economy = self.bot.get_cog('Economy')
                        await economy.data.Transaction.refund_transactions(*tids)
        finally:
            for lock in locks:
                lock.release()
        logger.info(
            "Cancelled Scheduled Session bookings: " + ', '.join(map(str, bookingids))
        )
        return records

    @log_wrap(action='Cancel Active Booking')
    async def _cancel_booking_active(self, slotid, guildid, userid):
        """
        Booking cancel worker for active slots.

        Does nothing if the provided bookingid is not active.
        The slot lock MUST be taken before this is run.
        """
        if not self.slotlock(slotid).locked():
            raise ValueError("Attempting to cancel active booking without taking slotlock.")

        slot = self.active_slots.get(slotid, None)
        session = slot.sessions.get(guildid, None) if slot else None
        member = session.members.pop(userid, None) if session else None
        if member is not None:
            if slot.closing.is_set():
                # Don't try to cancel a booking for a closing active slot.
                return
            async with session.lock:
                # Update message if it has already been sent
                session.update_status_soon(resend=False)
                room = session.room_channel
                member = session.guild.get_member(userid) if room else None
                if room and member and session.prepared:
                    # Update channel permissions unless the member is in the next session and it is prepared
                    nextslotid = slotid + 3600
                    nextslot = self.active_slots.get(nextslotid, None)
                    nextsession = nextslot.sessions.get(guildid, None) if nextslot else None
                    nextmember = (userid in nextsession.members) if nextsession else None

                    if (nextmember is None) or not (nextsession.prepared):
                        async with self.bot.idlock(room.id):
                            try:
                                await room.set_permissions(member, overwrite=None)
                            except discord.HTTPException:
                                pass
        elif slot is not None and member is None:
            # Should not happen
            logger.error(
                f"Cancelling booking <slotid: {slotid}> <gid: {guildid}> <uid: {userid}> "
                "for active slot "
                "but the session member was not found. This should not happen."
            )

    @log_wrap(action='Clear Member Schedule')
    async def clear_member_schedule(self, guildid, userid, refund=False):
        """
        Cancel all current and future bookings for the given member.
        """
        now = utc_now()
        nowid = time_to_slotid(now)

        # First retrieve current and future booking data
        bookings = await self.data.ScheduleSessionMember.fetch_where(
            (ScheduleData.ScheduleSessionMember.slotid >= nowid),
            guildid=guildid,
            userid=userid,
        )
        bookingids = [(b.slotid, guildid, userid) for b in bookings]
        if bookingids:
            await self.cancel_bookings(*bookingids, refund=refund)

    @log_wrap(action='Handle NoShow')
    async def handle_noshow(self, *memberids):
        """
        Handle "did not show" members.

        Typically cancels all future sessions for this member,
        blacklists depending on guild settings,
        and notifies the user.
        """
        logger.debug(
            "Handling TimeSlot noshow for members: {}".format(', '.join(map(str, memberids)))
        )
        now = utc_now()
        nowid = time_to_slotid(now)
        member_model = self.data.ScheduleSessionMember

        # First handle blacklist
        guildids, userids = map(set, zip(*memberids))
        # This should hit cache
        config_data = await self.data.ScheduleGuild.fetch_multiple(*guildids)
        autoblacklisting = {}
        for gid, row in config_data.items():
            if row['blacklist_after'] and (rid := row['blacklist_role']):
                guild = self.bot.get_guild(gid)
                role = guild.get_role(rid) if guild else None
                if role is not None:
                    autoblacklisting[gid] = (row['blacklist_after'], role)

        to_blacklist = {}
        if autoblacklisting:
            # Count number of missed sessions in the last 24h for each member in memberids
            # who is also in an autoblacklisting guild
            members = {}
            for gid, uid in memberids:
                if gid in autoblacklisting:
                    guild = self.bot.get_guild(gid)
                    member = guild.get_member(uid) if guild else None
                    if member:
                        members[(gid, uid)] = member

            if members:
                missed = await member_model.table.select_where(
                    member_model.slotid < nowid,
                    member_model.slotid >= nowid - 24 * 3600,
                    MEMBERS(*members.keys()),
                    attended=False,
                ).select(
                    guildid=member_model.guildid,
                    userid=member_model.userid,
                    missed="COUNT(slotid)"
                ).group_by(member_model.guildid, member_model.userid).with_no_adapter()
                for row in missed:
                    if row['missed'] >= autoblacklisting[row['guildid']][0]:
                        key = (row['guildid'], row['userid'])
                        to_blacklist[key] = members[key]

        if to_blacklist:
            # Actually apply blacklist
            tasks = []
            for (gid, uid), member in to_blacklist.items():
                role = autoblacklisting[gid][1]
                task = asyncio.create_task(member.add_role(role))
                tasks.append(task)
            # TODO: Logging and some error handling
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(
                f"Applied scheduled session blacklist to {len(to_blacklist)} missing members."
            )

        # Now cancel future sessions for members who were not blacklisted and are not currently clocked on
        to_clear = []
        activeslot = self.active_slots[nowid]
        for mid in memberids:
            if mid not in to_blacklist:
                gid, uid = mid
                session = activeslot.sessions.get(gid, None)
                member = session.members.get(uid, None) if session else None
                clocked = (member is not None) and (member.clock_start is not None)
                if not clocked:
                    to_clear.append(mid)

        if to_clear:
            # Retrieve booking data
            bookings = await member_model.fetch_where(
                (member_model.slotid >= nowid),
                MEMBERS(*to_clear)
            )
            bookingids = [(b.slotid, b.guildid, b.userid) for b in bookings]
            if bookingids:
                await self.cancel_bookings(*bookingids, refund=False)
            logger.info(
                f"Cancelled future sessions for {len(to_clear)} missing members."
            )
        logger.debug(
            "Completed NoShow handling"
        )

    @log_wrap(action='Create Booking')
    async def create_booking(self, guildid, userid, *slotids):
        """
        Create new bookings with the given bookingids.

        Probably best refactored into an interactive method,
        with some parts in slot and session.
        """
        logger.debug(
            f"Creating bookings for member <uid: {userid}> in <gid: {guildid}> "
            f"for slotids: {', '.join(map(str, slotids))}"
        )
        t = self.bot.translator.t
        locks = [self.slotlock(slotid) for slotid in sorted(slotids)]
        try:
            [await lock.acquire() for lock in locks]
            # Validate bookings
            guild_data = await self.data.ScheduleGuild.fetch_or_create(guildid)
            config = ScheduleConfig(guildid, guild_data)

            # Check guild lobby exists
            if config.get(ScheduleSettings.SessionLobby.setting_id).value is None:
                error = t(_p(
                    'create_booking|error:no_lobby',
                    "This server has not set a `session_lobby`, so the scheduled session system is disabled!"
                ))
                raise UserInputError(error)

            # Fetch up to data lion data and member data
            lion = await self.bot.core.lions.fetch_member(guildid, userid)
            member = await lion.fetch_member()
            await lion.data.refresh()
            if not member:
                # This should pretty much never happen unless something went wrong on Discord's end
                error = t(_p(
                    'create_booking|error:no_member',
                    "An unknown Discord error occurred. Please try again in a few minutes."
                ))
                raise UserInputError(error)

            # Check member blacklist
            if (role := config.get(ScheduleSettings.BlacklistRole.setting_id).value) and role in member.roles:
                error = t(_p(
                    'create_booking|error:blacklisted',
                    "You have been blacklisted from the scheduled session system in this server."
                ))
                raise UserInputError(error)

            # Check member balance
            requested = len(slotids)
            required = len(slotids) * config.get(ScheduleSettings.ScheduleCost.setting_id).value
            balance = lion.data.coins
            if balance < required:
                error = t(_np(
                    'create_booking|error:insufficient_balance',
                    "Booking a session costs {coin}**{required}**, but you only have {coin}**{balance}**.",
                    "Booking `{count}` sessions costs {coin}**{required}**, but you only have {coin}**{balance}**.",
                    requested
                )).format(
                    count=requested, coin=self.bot.config.emojis.coin,
                    required=required, balance=balance
                )
                raise UserInputError(error)

            # Check existing bookings
            schedule = await self._fetch_schedule(userid)
            if set(slotids).intersection(schedule.keys()):
                error = t(_p(
                    'create_booking|error:already_booked',
                    "One or more requested timeslots are already booked!"
                ))
                raise UserInputError(error)
            conn = await self.bot.db.get_connection()

            # Booking request is now validated. Perform bookings.
            # Fetch or create session data
            await self.data.ScheduleSlot.fetch_multiple(*slotids)
            session_data = await self.data.ScheduleSession.fetch_multiple(
                *((guildid, slotid) for slotid in slotids)
            )

            async with conn.transaction():
                # Create transactions
                economy = self.bot.get_cog('Economy')
                trans_data = (
                    TransactionType.SCHEDULE_BOOK,
                    guildid, userid, userid, 0,
                    config.get(ScheduleSettings.ScheduleCost.setting_id).value,
                    0, None
                )
                transactions = await economy.data.Transaction.execute_transactions(*(trans_data for _ in slotids))
                transactionids = [row.transactionid for row in transactions]

                # Create bookings
                now = utc_now()
                booking_data = await self.data.ScheduleSessionMember.table.insert_many(
                    ('guildid', 'userid', 'slotid', 'booked_at', 'book_transactionid'),
                    *(
                        (guildid, userid, slotid, now, tid)
                        for slotid, tid in zip(slotids, transactionids)
                    )
                )

            # Now pass to activated slots
            for record in booking_data:
                slotid = record['slotid']
                if (slot := self.active_slots.get(slotid, None)):
                    session = slot.sessions.get(guildid, None)
                    if session is None:
                        # Create a new session in the slot and set it up
                        sessions = await slot.load_sessions([session_data[guildid, slotid]])
                        session = sessions[guildid]
                        slot.sessions[guildid] = session
                        if slot.closing.is_set():
                            # This should never happen
                            logger.error(
                                "Attempt to book a session in a closing slot. This should be impossible."
                            )
                            raise ValueError('Cannot book a session in a closing slot.')
                        elif slot.opening.is_set():
                            await slot.open([session])
                        elif slot.preparing.is_set():
                            await slot.prepare([session])
                    else:
                        # Session already exists in the slot
                        async with session.lock:
                            smember = SessionMember(
                                self.bot, record, lion
                            )
                            session.members[userid] = smember
                            if session.prepared:
                                session.update_status_soon()
                                if (room := session.room_channel) and (mem := session.guild.get_member(userid)):
                                    try:
                                        await room.set_permissions(
                                            mem, connect=True, view_channel=True
                                        )
                                    except discord.HTTPException:
                                        logger.info(
                                            f"Could not set room permissions for newly booked session "
                                            f"<uid: {userid}> in {session!r}",
                                            exc_info=True
                                        )
                        if slot.preparing.is_set() and not session.prepared:
                            # Slot is preparing, but has not prepared the guild
                            # This *may* cause the guild to get prepared twice
                            await slot.prepare([session])
            logger.info(
                f"Member <uid: {userid}> in <gid: {guildid}> booked scheduled sessions: " +
                ', '.join(map(str, slotids))
            )
        except UserInputError:
            raise
        except Exception:
            logger.exception(
                "Unexpected exception occurred while booking scheduled sessions."
            )
            raise
        finally:
            for lock in locks:
                lock.release()
        return booking_data

    # Event listeners
    @LionCog.listener('on_member_update')
    @log_wrap(action="Schedule Check Blacklist")
    async def check_blacklist_role(self, before: discord.Member, after: discord.Member):
        guild = before.guild
        await self.initialised.wait()
        before_roles = {role.id for role in before.roles}
        new_roles = {role.id for role in after.roles if role.id not in before_roles}
        if new_roles:
            # This should be in cache in the vast majority of cases
            guild_data = await self.data.ScheduleGuild.fetch(guild.id)
            if guild_data and (roleid := guild_data.blacklist_role) is not None and roleid in new_roles:
                # Clear member schedule
                await self.clear_member_schedule(guild.id, after.id)

    @LionCog.listener('on_member_remove')
    @log_wrap(action="Schedule Member Remove")
    async def clear_leaving_member(self, member: discord.Member):
        """
        When a member leaves, clear their schedule
        """
        await self.initialised.wait()
        await self.clear_member_schedule(member.guild.id, member.id, refund=True)

    @LionCog.listener('on_guild_remove')
    @log_wrap(action="Schedule Guild Remove")
    async def clear_leaving_guild(self, guild: discord.Guild):
        """
        When leaving a guild, delete all future bookings in the guild.

        This avoids penalising members for missing sessions in guilds we are not part of.
        However, do not delete the guild sessions,
        this allows seamless resuming if we rejoin the guild (aside from the cancelled sessions).

        Note that loaded sessions are independent of whether we are in the guild or not
        (rather, we load all sessions that match this shard).
        Hence we do not need to recreate the sessions when we join a new guild.
        """
        await self.initialised.wait()

        now = utc_now()
        nowid = time_to_slotid(now)

        bookings = await self.data.ScheduleSessionMember.fetch_where(
            (ScheduleData.ScheduleSessionMember.slotid >= nowid),
            guildid=guild.id
        )
        bookingids = [(b.slotid, b.guildid, b.userid) for b in bookings]
        if bookingids:
            await self.cancel_bookings(*bookingids, refund=True)

    @LionCog.listener('on_voice_session_start')
    @log_wrap(action="Schedule Clock On")
    async def schedule_clockon(self, session_data):
        try:
            # DEBUG
            logger.debug(f"Handling clock on parsing for {session_data}")
            # Get current slot
            now = utc_now()
            nowid = time_to_slotid(now)
            async with self.slotlock(nowid):
                slot = self.active_slots.get(nowid, None)
                if slot is not None:
                    # Get session in current slot
                    session = slot.sessions.get(session_data.guildid, None)
                    member = session.members.get(session_data.userid, None) if session else None
                    if member is not None:
                        async with session.lock:
                            if session.listening and session.validate_channel(session_data.channelid):
                                member.clock_on(session_data.start_time)
                                session.update_status_soon()
                                logger.debug(
                                    f"Clocked on member {member.data!r} in session {session!r}"
                                )
        except Exception:
            logger.exception(
                f"Unexpected exception while clocking on voice sessions {session_data!r}"
            )

    @LionCog.listener('on_voice_session_end')
    @log_wrap(action="Schedule Clock Off")
    async def schedule_clockoff(self, session_data, ended_at):
        try:
            # DEBUG
            logger.debug(f"Handling clock off parsing for {session_data}")
            # Get current slot
            now = utc_now()
            nowid = time_to_slotid(now)
            async with self.slotlock(nowid):
                slot = self.active_slots.get(nowid, None)
                if slot is not None:
                    # Get session in current slot
                    session = slot.sessions.get(session_data.guildid)
                    member = session.members.get(session_data.userid, None) if session else None
                    if member is not None:
                        async with session.lock:
                            if session.listening and member.clock_start is not None:
                                member.clock_off(ended_at)
                                session.update_status_soon()
                                logger.debug(
                                    f"Clocked off member {member.data!r} from session {session!r}"
                                )
        except Exception:
            logger.exception(
                f"Unexpected exception while clocking off voice sessions {session_data!r}"
            )

    # Schedule commands
    @cmds.hybrid_command(
        name=_p('cmd:schedule', "schedule"),
        description=_p(
            'cmd:schedule|desc',
            "View and manage your scheduled session."
        )
    )
    @appcmds.guild_only
    async def schedule_cmd(self, ctx: LionContext):
        # TODO: Auotocomplete for book and cancel options
        # Will require TTL caching for member schedules.
        book = None
        cancel = None
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        t = self.bot.translator.t
        guildid = ctx.guild.id
        guild_data = await self.data.ScheduleGuild.fetch_or_create(guildid)
        config = ScheduleConfig(guildid, guild_data)
        now = utc_now()
        lines: list[tuple[bool, str]] = []  # (error_status, msg)

        if cancel is not None:
            schedule = await self._fetch_schedule(ctx.author.id)
            # Validate provided
            if not cancel.isdigit():
                # Error, slot {cancel} not recognised, please select a session to cancel from the acmpl list.
                error = t(_p(
                    'cmd:schedule|cancel_booking|error:parse_slot',
                    "Time slot `{provided}` not recognised. "
                    "Please select a session to cancel from the autocomplete options."
                ))
                line = (True, error)
            elif (slotid := int(cancel)) not in schedule:
                # Can't cancel slot because it isn't booked
                error = t(_p(
                    'cmd:schedule|cancel_booking|error:not_booked',
                    "Could not cancel {time} booking because it is not booked!"
                )).format(
                    time=discord.utils.format_dt(slotid_to_utc(slotid), style='t')
                )
                line = (True, error)
            elif (slotid_to_utc(slotid) - now).total_seconds() < 60:
                # Can't cancel slot because it is running or about to start
                error = t(_p(
                    'cmd:schedule|cancel_booking|error:too_soon',
                    "Cannot cancel {time} booking because it is running or starting soon!"
                )).format(
                    time=discord.utils.format_dt(slotid_to_utc(slotid), style='t')
                )
                line = (True, error)
            else:
                # Okay, slot is booked and cancellable.
                # Actually cancel it
                booking = schedule[slotid]
                await self.cancel_bookings((booking.slotid, booking.guildid, booking.userid))
                # Confirm cancel done
                ack = t(_p(
                    'cmd:schedule|cancel_booking|success',
                    "Successfully cancelled your booking at {time}."
                )).format(
                    time=discord.utils.format_dt(slotid_to_utc(slotid), style='t')
                )
                line = (False, ack)
            lines.append(line)

        if book is not None:
            schedule = await self._fetch_schedule(ctx.author.id)
            if not book.isdigit():
                # Error, slot not recognised, please use autocomplete menu
                error = t(_p(
                    'cmd:schedule|create_booking|error:parse_slot',
                    "Time slot `{provided}` not recognised. "
                    "Please select a session to cancel from the autocomplete options."
                ))
                lines = (True, error)
            elif (slotid := int(book)) in schedule:
                # Can't book because the slot is already booked
                error = t(_p(
                    'cmd:schedule|create_booking|error:already_booked',
                    "You have already booked a scheduled session for {time}."
                )).format(
                    time=discord.utils.format_dt(slotid_to_utc(slotid), style='t')
                )
                lines = (True, error)
            elif (slotid_to_utc(slotid) - now).total_seconds() < 60:
                # Can't book because it is running or about to start
                error = t(_p(
                    'cmd:schedule|create_booking|error:too_soon',
                    "Cannot book session at {time} because it is running or starting soon!"
                )).format(
                    time=discord.utils.format_dt(slotid_to_utc(slotid), style='t')
                )
                line = (True, error)
            else:
                # The slotid is valid and bookable
                # Run the booking
                try:
                    await self.create_booking(guildid, ctx.author.id)
                    ack = t(_p(
                        'cmd:schedule|create_booking|success',
                        "You have successfully scheduled a session at {time}."
                    )).format(
                        time=discord.utils.format_dt(slotid_to_utc(slotid), style='t')
                    )
                    line = (False, ack)
                except UserInputError as e:
                    line = (True, e.msg)
            lines.append(line)

        if lines:
            # Post lines
            any_failed = False
            text = []

            for failed, msg in lines:
                any_failed = any_failed or failed
                emoji = self.bot.config.emojis.warning if failed else self.bot.config.emojis.tick
                text.append(f"{emoji} {msg}")

            embed = discord.Embed(
                colour=discord.Colour.brand_red() if any_failed else discord.Colour.brand_green(),
                description='\n'.join(text)
            )
            await ctx.interaction.edit_original_response(embed=embed)
        else:
            # Post ScheduleUI
            ui = ScheduleUI(self.bot, ctx.guild, ctx.author.id)
            await ui.run(ctx.interaction)
            await ui.wait()

    async def _fetch_schedule(self, userid, **kwargs):
        """
        Fetch the given user's schedule (i.e. booking map)
        """
        nowid = time_to_slotid(utc_now())

        booking_model = self.data.ScheduleSessionMember
        bookings = await booking_model.fetch_where(
            booking_model.slotid >= nowid,
            userid=userid,
        ).order_by('slotid', ORDER.ASC)

        return {
            booking.slotid: booking for booking in bookings
        }

    # Configuration
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        """
        Substitute configure command group.
        """
        pass

    config_params = {
        'session_lobby': ScheduleSettings.SessionLobby,
        'session_room': ScheduleSettings.SessionRoom,
        'schedule_cost': ScheduleSettings.ScheduleCost,
        'attendance_reward': ScheduleSettings.AttendanceReward,
        'attendance_bonus': ScheduleSettings.AttendanceBonus,
        'min_attendance': ScheduleSettings.MinAttendance,
        'blacklist_role': ScheduleSettings.BlacklistRole,
        'blacklist_after': ScheduleSettings.BlacklistAfter,
    }

    @configure_group.command(
        name=_p('cmd:configure_schedule', "schedule"),
        description=_p(
            'cmd:configure_schedule|desc',
            "Configure Scheduled Session system"
        )
    )
    @appcmds.rename(
        **{param: option._display_name for param, option in config_params.items()}
    )
    @appcmds.describe(
        **{param: option._desc for param, option in config_params.items()}
    )
    @low_management_ward
    async def configure_schedule_command(self, ctx: LionContext,
                                         session_lobby: Optional[discord.TextChannel | discord.VoiceChannel] = None,
                                         session_room: Optional[discord.VoiceChannel] = None,
                                         schedule_cost: Optional[appcmds.Range[int, 0, MAX_COINS]] = None,
                                         attendance_reward: Optional[appcmds.Range[int, 0, MAX_COINS]] = None,
                                         attendance_bonus: Optional[appcmds.Range[int, 0, MAX_COINS]] = None,
                                         min_attendance: Optional[appcmds.Range[int, 1, 60]] = None,
                                         blacklist_role: Optional[discord.Role] = None,
                                         blacklist_after: Optional[appcmds.Range[int, 1, 24]] = None
                                         ):
        # Type Guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # Map of parameter names to setting values
        provided = {
            'session_lobby': session_lobby,
            'session_room': session_room,
            'schedule_cost': schedule_cost,
            'attendance_reward': attendance_reward,
            'attendance_bonus': attendance_bonus,
            'min_attendance': min_attendance,
            'blacklist_role': blacklist_role,
            'blacklist_after': blacklist_after,
        }
        modified = set(param for param, value in provided.items() if value is not None)

        # Make a config instance
        guild_data = await self.data.ScheduleGuild.fetch_or_create(ctx.guild.id)
        config = ScheduleConfig(ctx.guild.id, guild_data)

        if modified:
            # Check provided values and build a list of write arguments
            # Note that all settings are ModelSettings of ScheduleData.ScheduleGuild
            lines = []
            update_args = {}
            settings = []
            for param in modified:
                # TODO: Add checks with setting._check_value
                setting = self.config_params[param]
                new_value = provided[param]

                instance = config.get(setting.setting_id)
                instance.value = new_value
                settings.append(instance)
                update_args[instance._column] = instance._data
                lines.append(instance.update_message)

            # Perform data update
            await guild_data.update(**update_args)
            # Dispatch setting updates to trigger hooks
            for setting in settings:
                setting.dispatch_update()

            # Ack modified settings
            tick = self.bot.config.emojis.tick
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description='\n'.join(f"{tick} {line}" for line in lines)
            )
            await ctx.reply(embed=embed)

        # Launch config UI if needed
        if ctx.channel.id not in ScheduleSettingUI._listening or not modified:
            ui = ScheduleSettingUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()

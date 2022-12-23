import asyncio
import datetime
import collections
import traceback
import logging
import discord
from typing import Dict
from discord.utils import sleep_until

from meta import client
from utils.interactive import discord_shield
from data import NULL, NOTNULL, tables
from data.conditions import LEQ, THIS_SHARD
from settings import GuildSettings

from .TimeSlot import TimeSlot
from .lib import utc_now
from .data import accountability_rooms, accountability_members
from .module import module


voice_ignore_lock = asyncio.Lock()
room_lock = asyncio.Lock()


def locker(lock):
    """
    Function decorator to wrap the function in a provided Lock
    """
    def decorator(func):
        async def wrapped(*args, **kwargs):
            async with lock:
                return await func(*args, **kwargs)
        return wrapped
    return decorator


class AccountabilityGuild:
    __slots__ = ('guildid', 'current_slot', 'upcoming_slot')

    cache: Dict[int, 'AccountabilityGuild'] = {}  # Map guildid -> AccountabilityGuild

    def __init__(self, guildid):
        self.guildid = guildid
        self.current_slot = None
        self.upcoming_slot = None

        self.cache[guildid] = self

    @property
    def guild(self):
        return client.get_guild(self.guildid)

    @property
    def guild_settings(self):
        return GuildSettings(self.guildid)

    def advance(self):
        self.current_slot = self.upcoming_slot
        self.upcoming_slot = None


async def open_next(start_time):
    """
    Open all the upcoming accountability rooms, and fire channel notify.
    To be executed ~5 minutes to the hour.
    """
    # Pre-fetch the new slot data, also populating the table caches
    room_data = accountability_rooms.fetch_rows_where(
        start_at=start_time,
        guildid=THIS_SHARD
    )
    guild_rows = {row.guildid: row for row in room_data}
    member_data = accountability_members.fetch_rows_where(
        slotid=[row.slotid for row in room_data]
    ) if room_data else []
    slot_memberids = collections.defaultdict(list)
    for row in member_data:
        slot_memberids[row.slotid].append(row.userid)

    # Open a new slot in each accountability guild
    to_update = []  # Cache of slot update data to be applied at the end
    for aguild in list(AccountabilityGuild.cache.values()):
        guild = aguild.guild
        if guild:
            # Initialise next TimeSlot
            slot = TimeSlot(
                guild,
                start_time,
                data=guild_rows.get(aguild.guildid, None)
            )
            slot.load(memberids=slot_memberids[slot.data.slotid] if slot.data else None)

            if not slot.category:
                # Log and unload guild
                aguild.guild_settings.event_log.log(
                    "The scheduled session category couldn't be found!\n"
                    "Shutting down the scheduled session system in this server.\n"
                    "To re-activate, please reconfigure `config session_category`."
                )
                AccountabilityGuild.cache.pop(aguild.guildid, None)
                await slot.cancel()
                continue
            elif not slot.lobby:
                # TODO: Consider putting in TimeSlot.open().. or even better in accountability_lobby.create()
                # Create a new lobby
                try:
                    channel = await guild.create_text_channel(
                        name="session-lobby",
                        category=slot.category,
                        reason="Automatic creation of scheduled session lobby."
                    )
                    aguild.guild_settings.accountability_lobby.value = channel
                    slot.lobby = channel
                except discord.HTTPException:
                    # Event log failure and skip session
                    aguild.guild_settings.event_log.log(
                        "Failed to create the scheduled session lobby text channel.\n"
                        "Please set the lobby channel manually with `config`."
                    )
                    await slot.cancel()
                    continue

                # Event log creation
                aguild.guild_settings.event_log.log(
                    "Automatically created a scheduled session lobby channel {}.".format(channel.mention)
                )

            results = await slot.open()
            if results is None:
                # Couldn't open the channel for some reason.
                # Should already have been logged in `open`.
                # Skip this session
                await slot.cancel()
                continue
            elif slot.data:
                to_update.append((results[0], results[1], slot.data.slotid))

            # Time slot should now be open and ready to start
            aguild.upcoming_slot = slot
        else:
            # Unload guild from cache
            AccountabilityGuild.cache.pop(aguild.guildid, None)

    # Update slot data
    if to_update:
        accountability_rooms.update_many(
            *to_update,
            set_keys=('channelid', 'messageid'),
            where_keys=('slotid',)
        )


async def turnover():
    """
    Switchover from the current accountability rooms to the next ones.
    To be executed as close as possible to the hour.
    """
    now = utc_now()

    # Open event lock so we don't read voice channel movement
    async with voice_ignore_lock:
        # Update session data for completed sessions
        last_slots = [
            aguild.current_slot for aguild in AccountabilityGuild.cache.values()
            if aguild.current_slot is not None
        ]

        to_update = [
            (mem.data.duration + int((now - mem.data.last_joined_at).total_seconds()), None, mem.slotid, mem.userid)
            for slot in last_slots for mem in slot.members.values()
            if mem.data and mem.data.last_joined_at
        ]
        if to_update:
            accountability_members.update_many(
                *to_update,
                set_keys=('duration', 'last_joined_at'),
                where_keys=('slotid', 'userid'),
                cast_row='(NULL::int, NULL::timestamptz, NULL::int, NULL::int)'
            )

        # Close all completed rooms, update data
        await asyncio.gather(*(slot.close() for slot in last_slots), return_exceptions=True)
        update_slots = [slot.data.slotid for slot in last_slots if slot.data]
        if update_slots:
            accountability_rooms.update_where(
                {'closed_at': utc_now()},
                slotid=update_slots
            )

        # Rotate guild sessions
        [aguild.advance() for aguild in AccountabilityGuild.cache.values()]

        # TODO: (FUTURE) with high volume, we might want to start the sessions before moving the members.
        # We could break up the session starting?

        # ---------- Start next session ----------
        current_slots = [
            aguild.current_slot for aguild in AccountabilityGuild.cache.values()
            if aguild.current_slot is not None
        ]
        slotmap = {slot.data.slotid: slot for slot in current_slots if slot.data}

        # Reload the slot members in case they cancelled from another shard
        member_data = accountability_members.fetch_rows_where(
            slotid=list(slotmap.keys())
        ) if slotmap else []
        slot_memberids = {slotid: [] for slotid in slotmap}
        for row in member_data:
            slot_memberids[row.slotid].append(row.userid)
        reload_tasks = (
            slot._reload_members(memberids=slot_memberids[slotid])
            for slotid, slot in slotmap.items()
        )
        await asyncio.gather(
            *reload_tasks,
            return_exceptions=True
        )

        # Move members of the next session over to the session channel
        movement_tasks = (
            mem.member.edit(
                voice_channel=slot.channel,
                reason="Moving to scheduled session."
            )
            for slot in current_slots
            for mem in slot.members.values()
            if mem.data and mem.member and mem.member.voice and mem.member.voice.channel != slot.channel
        )
        # We return exceptions here to ignore any permission issues that occur with moving members.
        # It's also possible (likely) that members will move while we are moving other members
        # Returning the exceptions ensures that they are explicitly ignored
        await asyncio.gather(
            *movement_tasks,
            return_exceptions=True
        )

        # Update session data of all members in new channels
        member_session_data = [
            (0, slot.start_time, mem.slotid, mem.userid)
            for slot in current_slots
            for mem in slot.members.values()
            if mem.data and mem.member and mem.member.voice and mem.member.voice.channel == slot.channel
        ]
        if member_session_data:
            accountability_members.update_many(
                *member_session_data,
                set_keys=('duration', 'last_joined_at'),
                where_keys=('slotid', 'userid'),
                cast_row='(NULL::int, NULL::timestamptz, NULL::int, NULL::int)'
            )

    # Start all the current rooms
    await asyncio.gather(
        *(slot.start() for slot in current_slots),
        return_exceptions=True
    )


@client.add_after_event('voice_state_update')
async def room_watchdog(client, member, before, after):
    """
    Update session data when a member joins or leaves an accountability room.
    Ignores events that occur while `voice_ignore_lock` is held.
    """
    if not voice_ignore_lock.locked() and before.channel != after.channel:
        aguild = AccountabilityGuild.cache.get(member.guild.id)
        if aguild and aguild.current_slot and aguild.current_slot.channel:
            slot = aguild.current_slot
            if member.id in slot.members:
                if after.channel and after.channel.id != slot.channel.id:
                    # Summon them back!
                    asyncio.create_task(member.edit(voice_channel=slot.channel))

                slot_member = slot.members[member.id]
                data = slot_member.data

                if before.channel and before.channel.id == slot.channel.id:
                    # Left accountability room
                    with data.batch_update():
                        data.duration += int((utc_now() - data.last_joined_at).total_seconds())
                        data.last_joined_at = None
                    await slot.update_status()
                elif after.channel and after.channel.id == slot.channel.id:
                    # Joined accountability room
                    with data.batch_update():
                        data.last_joined_at = utc_now()
                    await slot.update_status()


async def _accountability_loop():
    """
    Runloop in charge of executing the room update tasks at the correct times.
    """
    # Wait until ready
    while not client.is_ready():
        await asyncio.sleep(0.1)

    # Calculate starting next_time
    # Assume the resume logic has taken care of all events/tasks before current_time
    now = utc_now()
    if now.minute < 55:
        next_time = now.replace(minute=55, second=0, microsecond=0)
    else:
        next_time = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)

    # Executor loop
    while True:
        # TODO: (FUTURE) handle cases where we actually execute much late than expected
        await sleep_until(next_time)
        if next_time.minute == 55:
            next_time = next_time + datetime.timedelta(minutes=5)
            # Open next sessions
            try:
                async with room_lock:
                    await open_next(next_time)
            except Exception:
                # Unknown exception. Catch it so the loop doesn't die.
                client.log(
                    "Error while opening new scheduled sessions! "
                    "Exception traceback follows.\n{}".format(
                        traceback.format_exc()
                    ),
                    context="ACCOUNTABILITY_LOOP",
                    level=logging.ERROR
                )
        elif next_time.minute == 0:
            # Start new sessions
            try:
                async with room_lock:
                    await turnover()
            except Exception:
                # Unknown exception. Catch it so the loop doesn't die.
                client.log(
                    "Error while starting scheduled sessions! "
                    "Exception traceback follows.\n{}".format(
                        traceback.format_exc()
                    ),
                    context="ACCOUNTABILITY_LOOP",
                    level=logging.ERROR
                )
            next_time = next_time + datetime.timedelta(minutes=55)


async def _accountability_system_resume():
    """
    Logic for starting the accountability system from cold.
    Essentially, session and state resume logic.
    """
    now = utc_now()

    # Fetch the open room data, only takes into account currently running sessions.
    # May include sessions that were never opened, or opened but never started
    # Does not include sessions that were opened that start on the next hour
    open_room_data = accountability_rooms.fetch_rows_where(
        closed_at=NULL,
        start_at=LEQ(now),
        guildid=THIS_SHARD,
        _extra="ORDER BY start_at ASC"
    )

    if open_room_data:
        # Extract member data of these rows
        member_data = accountability_members.fetch_rows_where(
            slotid=[row.slotid for row in open_room_data]
        )
        slot_members = collections.defaultdict(list)
        for row in member_data:
            slot_members[row.slotid].append(row)

        # Filter these into expired rooms and current rooms
        expired_room_data = []
        current_room_data = []
        for row in open_room_data:
            if row.start_at + datetime.timedelta(hours=1) < now:
                expired_room_data.append(row)
            else:
                current_room_data.append(row)

        session_updates = []

        # TODO URGENT: Batch room updates here

        # Expire the expired rooms
        for row in expired_room_data:
            if row.channelid is None or row.messageid is None:
                # TODO refunds here
                # If the rooms were never opened, close them and skip
                row.closed_at = now
            else:
                # If the rooms were opened and maybe started, make optimistic guesses on session data and close.
                session_end = row.start_at + datetime.timedelta(hours=1)
                session_updates.extend(
                    (mow.duration + int((session_end - mow.last_joined_at).total_seconds()),
                     None, mow.slotid, mow.userid)
                    for mow in slot_members[row.slotid] if mow.last_joined_at
                )
                if client.get_guild(row.guildid):
                    slot = TimeSlot(client.get_guild(row.guildid), row.start_at, data=row).load(
                        memberids=[mow.userid for mow in slot_members[row.slotid]]
                    )
                    try:
                        await slot.close()
                    except discord.HTTPException:
                        pass
                row.closed_at = now

        # Load the in-progress room data
        if current_room_data:
            async with voice_ignore_lock:
                current_hour = now.replace(minute=0, second=0, microsecond=0)
                await open_next(current_hour)
                [aguild.advance() for aguild in AccountabilityGuild.cache.values()]

                current_slots = [
                    aguild.current_slot
                    for aguild in AccountabilityGuild.cache.values()
                    if aguild.current_slot
                ]

                session_updates.extend(
                    (mem.data.duration + int((now - mem.data.last_joined_at).total_seconds()),
                        None, mem.slotid, mem.userid)
                    for slot in current_slots
                    for mem in slot.members.values()
                    if mem.data.last_joined_at and mem.member not in slot.channel.members
                )

                session_updates.extend(
                    (mem.data.duration,
                        now, mem.slotid, mem.userid)
                    for slot in current_slots
                    for mem in slot.members.values()
                    if not mem.data.last_joined_at and mem.member in slot.channel.members
                )

                if session_updates:
                    accountability_members.update_many(
                        *session_updates,
                        set_keys=('duration', 'last_joined_at'),
                        where_keys=('slotid', 'userid'),
                        cast_row='(NULL::int, NULL::timestamptz, NULL::int, NULL::int)'
                    )

                await asyncio.gather(
                    *(aguild.current_slot.start()
                        for aguild in AccountabilityGuild.cache.values() if aguild.current_slot)
                )
        else:
            if session_updates:
                accountability_members.update_many(
                    *session_updates,
                    set_keys=('duration', 'last_joined_at'),
                    where_keys=('slotid', 'userid'),
                    cast_row='(NULL::int, NULL::timestamptz, NULL::int, NULL::int)'
                )

    # If we are in the last five minutes of the hour, open new rooms.
    # Note that these may already have been opened, or they may not have been.
    if now.minute >= 55:
        await open_next(
            now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
        )


@module.launch_task
async def launch_accountability_system(client):
    """
    Launcher for the accountability system.
    Resumes saved sessions, and starts the accountability loop.
    """
    # Load the AccountabilityGuild cache
    guilds = tables.guild_config.fetch_rows_where(
        accountability_category=NOTNULL,
        guildid=THIS_SHARD
    )
    # Further filter out any guilds that we aren't in
    [AccountabilityGuild(guild.guildid) for guild in guilds if client.get_guild(guild.guildid)]
    await _accountability_system_resume()
    asyncio.create_task(_accountability_loop())


async def unload_accountability(client):
    """
    Save the current sessions and cancel the runloop in preparation for client shutdown.
    """
    ...


@client.add_after_event('member_join')
async def restore_accountability(client, member):
    """
    Restore accountability channel permissions when a member rejoins the server, if applicable.
    """
    aguild = AccountabilityGuild.cache.get(member.guild.id, None)
    if aguild:
        if aguild.current_slot and member.id in aguild.current_slot.members:
            # Restore member permission for current slot
            slot = aguild.current_slot
            if slot.channel:
                asyncio.create_task(discord_shield(
                    slot.channel.set_permissions(
                        member,
                        overwrite=slot._member_overwrite
                    )
                ))
        if aguild.upcoming_slot and member.id in aguild.upcoming_slot.members:
            slot = aguild.upcoming_slot
            if slot.channel:
                asyncio.create_task(discord_shield(
                    slot.channel.set_permissions(
                        member,
                        overwrite=slot._member_overwrite
                    )
                ))

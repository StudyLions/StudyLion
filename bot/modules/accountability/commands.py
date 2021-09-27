import re
import datetime
import discord
import asyncio
from cmdClient.checks import in_guild

from utils.lib import multiselect_regex, parse_ranges, prop_tabulate
from data import NOTNULL
from data.conditions import GEQ, LEQ

from .module import module
from .lib import utc_now
from .tracker import AccountabilityGuild as AGuild
from .tracker import room_lock
from .TimeSlot import SlotMember
from .data import accountability_members, accountability_member_info, accountability_rooms


hint_icon = "https://projects.iamcal.com/emoji-data/img-apple-64/1f4a1.png"


def time_format(time):
    diff = (time - utc_now()).total_seconds()
    if diff < 0:
        diffstr = "`Right Now!!`"
    elif diff < 600:
        diffstr = "`Very soon!!`"
    elif diff < 3600:
        diffstr = "`In <1 hour `"
    else:
        hours = round(diff / 3600)
        diffstr = "`In {:>2} hour{}`".format(hours, 's' if hours > 1 else ' ')

    return "{} | <t:{:.0f}:t> - <t:{:.0f}:t>".format(
        diffstr,
        time.timestamp(),
        time.timestamp() + 3600,
    )


@module.cmd(
    name="rooms",
    desc="Book an accountability timeslot",
    group="Productivity"
)
@in_guild()
async def cmd_rooms(ctx):
    """
    Usage``:
        {prefix}rooms
        {prefix}rooms book
        {prefix}rooms cancel
    Description:
        View, book, or cancel your accountability sessions.
    """
    lower = ctx.args.lower()
    splits = lower.split()
    command = splits[0] if splits else None

    if not ctx.guild_settings.accountability_category.value:
        return await ctx.error_reply("The accountability system isn't set up!")

    # First grab the sessions the member is booked in
    joined_rows = accountability_member_info.select_where(
        userid=ctx.author.id,
        start_at=GEQ(utc_now()),
        _extra="ORDER BY start_at ASC"
    )

    if command == 'cancel':
        if not joined_rows:
            return await ctx.error_reply("You have no bookings to cancel!")

        # Show unbooking menu
        lines = [
            "`[{:>2}]` | {}".format(i, time_format(row['start_at']))
            for i, row in enumerate(joined_rows)
        ]
        out_msg = await ctx.reply(
            content="Please reply with the number(s) of the rooms you want to cancel. E.g. `1, 3, 5` or `1-3, 7-8`.",
            embed=discord.Embed(
                title="Please choose the bookings you want to cancel.",
                description='\n'.join(lines),
                colour=discord.Colour.orange()
            ).set_footer(
                text=(
                    "All times are in your own timezone! Hover over a time to see the date."
                )
            )
        )

        await ctx.cancellable(
            out_msg,
            cancel_message="Cancel menu closed, no accountability sessions were cancelled.",
            timeout=70
        )

        def check(msg):
            valid = msg.channel == ctx.ch and msg.author == ctx.author
            valid = valid and (re.search(multiselect_regex, msg.content) or msg.content.lower() == 'c')
            return valid

        try:
            message = await ctx.client.wait_for('message', check=check, timeout=60)
        except asyncio.TimeoutError:
            try:
                await out_msg.edit(
                    content=None,
                    embed=discord.Embed(
                        description="Cancel menu timed out, no accountability sessions were cancelled.",
                        colour=discord.Colour.red()
                    )
                )
                await out_msg.clear_reactions()
            except discord.HTTPException:
                pass
            return

        try:
            await out_msg.delete()
            await message.delete()
        except discord.HTTPException:
            pass

        if message.content.lower() == 'c':
            return

        to_cancel = [
            joined_rows[index]
            for index in parse_ranges(message.content) if index < len(joined_rows)
        ]
        if not to_cancel:
            return await ctx.error_reply("No valid bookings selected for cancellation.")
        cost = len(to_cancel) * ctx.guild_settings.accountability_price.value

        slotids = [row['slotid'] for row in to_cancel]
        async with room_lock:
            accountability_members.delete_where(
                userid=ctx.author.id,
                slotid=slotids
            )

            # Handle case where the slot has already opened
            # TODO: Possible race condition if they open over the hour border? Might never cancel
            for row in to_cancel:
                aguild = AGuild.cache.get(row['guildid'], None)
                if aguild and aguild.upcoming_slot and aguild.upcoming_slot.data:
                    if aguild.upcoming_slot.data.slotid in slotids:
                        aguild.upcoming_slot.members.pop(ctx.author.id, None)
                        if aguild.upcoming_slot.channel:
                            try:
                                await aguild.upcoming_slot.channel.set_permissions(
                                    ctx.author,
                                    overwrite=None
                                )
                            except discord.HTTPException:
                                pass
                        await aguild.upcoming_slot.update_status()
                        break

        ctx.alion.addCoins(cost)

        remaining = [row for row in joined_rows if row['slotid'] not in slotids]
        if not remaining:
            await ctx.embed_reply("Cancelled all your upcoming accountability sessions!")
        else:
            next_booked_time = min(row['start_at'] for row in remaining)
            if len(to_cancel) > 1:
                await ctx.embed_reply(
                    "Cancelled `{}` upcoming sessions!\nYour next session is at <t:{:.0f}>.".format(
                        len(to_cancel),
                        next_booked_time.timestamp()
                    )
                )
            else:
                await ctx.embed_reply(
                    "Cancelled your session at <t:{:.0f}>!\n"
                    "Your next session is at <t:{:.0f}>.".format(
                        to_cancel[0]['start_at'].timestamp(),
                        next_booked_time.timestamp()
                    )
                )
    elif command == 'book':
        # Show booking menu
        # Get attendee count
        rows = accountability_member_info.select_where(
            guildid=ctx.guild.id,
            userid=NOTNULL,
            select_columns=(
                'slotid',
                'start_at',
                'COUNT(*) as num'
            ),
            _extra="GROUP BY start_at, slotid"
        )
        attendees = {row['start_at']: row['num'] for row in rows}
        attendee_pad = max((len(str(num)) for num in attendees.values()), default=1)

        # Build lines
        already_joined_times = set(row['start_at'] for row in joined_rows)
        start_time = utc_now().replace(minute=0, second=0, microsecond=0)
        times = (
            start_time + datetime.timedelta(hours=n)
            for n in range(1, 25)
        )
        times = [time for time in times if time not in already_joined_times]
        lines = [
            "`[{num:>2}]` | `{count:>{count_pad}}` attending | {time}".format(
                num=i,
                count=attendees.get(time, 0), count_pad=attendee_pad,
                time=time_format(time),
            )
            for i, time in enumerate(times)
        ]
        # TODO: Nicer embed
        # TODO: Don't allow multi bookings if the member has a bad attendance rate
        out_msg = await ctx.reply(
            content="Please reply with the number(s) of the rooms you want to join. E.g. `1, 3, 5` or `1-3, 7-8`.",
            embed=discord.Embed(
                title="Please choose the sessions you want to book.",
                description='\n'.join(lines),
                colour=discord.Colour.orange()
            ).set_footer(
                text=(
                    "All times are in your own timezone! Hover over a time to see the date."
                )
            )
        )
        await ctx.cancellable(
            out_msg,
            cancel_message="Booking menu cancelled, no sessions were booked.",
            timeout=70
        )

        def check(msg):
            valid = msg.channel == ctx.ch and msg.author == ctx.author
            valid = valid and (re.search(multiselect_regex, msg.content) or msg.content.lower() == 'c')
            return valid

        try:
            message = await ctx.client.wait_for('message', check=check, timeout=60)
        except asyncio.TimeoutError:
            try:
                await out_msg.edit(
                    content=None,
                    embed=discord.Embed(
                        description="Booking menu timed out, no sessions were booked.",
                        colour=discord.Colour.red()
                    )
                )
                await out_msg.clear_reactions()
            except discord.HTTPException:
                pass
            return

        try:
            await out_msg.delete()
            await message.delete()
        except discord.HTTPException:
            pass

        if message.content.lower() == 'c':
            return

        to_book = [
            times[index]
            for index in parse_ranges(message.content) if index < len(times)
        ]
        if not to_book:
            return await ctx.error_reply("No valid sessions selected.")
        cost = len(to_book) * ctx.guild_settings.accountability_price.value
        if cost > ctx.alion.coins:
            return await ctx.error_reply(
                "Sorry, booking `{}` sessions costs `{}` coins, and you only have `{}`!".format(
                    len(to_book),
                    cost,
                    ctx.alion.coins
                )
            )

        # Add the member to data, creating the row if required
        slot_rows = accountability_rooms.fetch_rows_where(
            guildid=ctx.guild.id,
            start_at=to_book
        )
        slotids = [row.slotid for row in slot_rows]
        to_add = set(to_book).difference((row.start_at for row in slot_rows))
        if to_add:
            slotids.extend(row['slotid'] for row in accountability_rooms.insert_many(
                *((ctx.guild.id, start_at) for start_at in to_add),
                insert_keys=('guildid', 'start_at'),
            ))
        accountability_members.insert_many(
            *((slotid, ctx.author.id, ctx.guild_settings.accountability_price.value) for slotid in slotids),
            insert_keys=('slotid', 'userid', 'paid')
        )

        # Handle case where the slot has already opened
        aguild = AGuild.cache.get(ctx.guild.id, None)
        if aguild:
            if aguild.upcoming_slot and aguild.upcoming_slot.start_time in to_book:
                slot = aguild.upcoming_slot
                if not slot.data:
                    # Handle slot activation
                    slot._refresh()
                    channelid, messageid = await slot.open()
                    accountability_rooms.update_where(
                        {'channelid': channelid, 'messageid': messageid},
                        slotid=slot.data.slotid
                    )
                else:
                    slot.members[ctx.author.id] = SlotMember(slot.data.slotid, ctx.author.id, ctx.guild)
                    # Also update the channel permissions
                    try:
                        await slot.channel.set_permissions(ctx.author, view_channel=True, connect=True)
                    except discord.HTTPException:
                        pass
                await slot.update_status()
        ctx.alion.addCoins(-cost)

        # Ack purchase
        embed = discord.Embed(
            title="You have booked the following session{}!".format('s' if len(to_book) > 1 else ''),
            description=(
                "*Please attend all your booked sessions!*\n"
                "*If you can't attend, cancel with* `{}rooms cancel`\n\n{}"
            ).format(
                ctx.best_prefix,
                '\n'.join(time_format(time) for time in to_book),
            ),
            colour=discord.Colour.orange()
        ).set_footer(
            text=(
                "Use {prefix}rooms to see your current bookings.\n"
            ).format(prefix=ctx.best_prefix)
        )
        try:
            await ctx.reply(
                embed=embed,
                reference=ctx.msg
            )
        except discord.NotFound:
            await ctx.reply(embed=embed)
    else:
        # Show accountability room information for this user
        # Accountability profile
        # Author
        # Special case for no past bookings, emphasis hint
        # Hint on Bookings section for booking/cancelling as applicable
        # Description has stats
        # Footer says that all times are in their timezone
        # TODO: attendance requirement shouldn't be retroactive! Add attended data column
        # Attended `{}` out of `{}` booked (`{}%` attendance rate!)
        # Attendance streak: `{}` days attended with no missed sessions!
        # Add explanation for first time users

        # Get all slots the member has ever booked
        history = accountability_member_info.select_where(
            userid=ctx.author.id,
            # start_at=LEQ(utc_now() - datetime.timedelta(hours=1)),
            start_at=LEQ(utc_now()),
            select_columns=("*", "(duration > 0 OR last_joined_at IS NOT NULL) AS attended"),
            _extra="ORDER BY start_at DESC"
        )

        if not (history or joined_rows):
            # First-timer information
            about = (
                "You haven't joined any accountability sessions yet!\n"
                "Book a session by typing **`{}rooms book`** and selecting "
                "the hours you intend to study, "
                "then attend by joining the accountability voice channel when the session starts!\n"
                "Only if everyone attends will they get the bonus of `{}` LionCoins!\n"
                "Let's all do our best and keep each other accountable 🔥"
            ).format(
                ctx.best_prefix,
                ctx.guild_settings.accountability_bonus.value
            )
            embed = discord.Embed(
                description=about,
                colour=discord.Colour.orange()
            )
            embed.set_footer(
                text="Please keep your DMs open so I can notify you when the session starts!\n",
                icon_url=hint_icon
            )
            await ctx.reply(embed=embed)
        else:
            # Build description with stats
            if history:
                # First get the counts
                attended_count = sum(row['attended'] for row in history)
                total_count = len(history)
                total_duration = sum(row['duration'] for row in history)

                # Add current session to duration if it exists
                if history[0]['last_joined_at'] and (utc_now() - history[0]['start_at']).total_seconds() < 3600:
                    total_duration += int((utc_now() - history[0]['last_joined_at']).total_seconds())

                # Calculate the streak
                timezone = ctx.alion.settings.timezone.value

                streak = 0
                current_streak = None
                max_streak = 0
                day_attended = None
                date = utc_now().astimezone(timezone).replace(hour=0, minute=0, second=0, microsecond=0)
                daydiff = datetime.timedelta(days=1)

                i = 0
                while i < len(history):
                    row = history[i]
                    i += 1
                    if not row['attended']:
                        # Not attended, streak broken
                        pass
                    elif row['start_at'] > date:
                        # They attended this day
                        day_attended = True
                        continue
                    elif day_attended is None:
                        # Didn't attend today, but don't break streak
                        day_attended = False
                        date -= daydiff
                        i -= 1
                        continue
                    elif not day_attended:
                        # Didn't attend the day, streak broken
                        date -= daydiff
                        i -= 1
                        pass
                    else:
                        # Attended the day
                        streak += 1

                        # Move window to the previous day and try the row again
                        date -= daydiff
                        day_attended = False
                        i -= 1
                        continue

                    max_streak = max(max_streak, streak)
                    if current_streak is None:
                        current_streak = streak
                    streak = 0

                # Handle loop exit state, i.e. the last streak
                if day_attended:
                    streak += 1
                max_streak = max(max_streak, streak)
                if current_streak is None:
                    current_streak = streak

                # Build the stats
                table = {
                    "Sessions": "**{}** attended out of **{}**, `{:.0f}%` attendance rate.".format(
                        attended_count,
                        total_count,
                        (attended_count * 100) / total_count,
                    ),
                    "Time": "**{:02}:{:02}** spent in accountability rooms.".format(
                        total_duration // 3600,
                        (total_duration % 3600) // 60
                    ),
                    "Streak": "**{}** day{} with no missed sessions! (Longest: **{}** day{}.)".format(
                        current_streak,
                        's' if current_streak != 1 else '',
                        max_streak,
                        's' if max_streak != 1 else '',
                    ),
                }
                desc = prop_tabulate(*zip(*table.items()))
            else:
                desc = (
                    "Good luck with your next session!\n"
                )

            # Build currently booked list

            if joined_rows:
                # TODO: (Future) calendar link
                # Get attendee counts for currently booked sessions
                rows = accountability_member_info.select_where(
                    slotid=[row["slotid"] for row in joined_rows],
                    userid=NOTNULL,
                    select_columns=(
                        'slotid',
                        'start_at',
                        'COUNT(*) as num'
                    ),
                    _extra="GROUP BY start_at, slotid ORDER BY start_at ASC"
                )
                attendees = {row['start_at']: row['num'] for row in rows}
                attendee_pad = max((len(str(num)) for num in attendees.values()), default=1)

                # TODO: Allow cancel to accept multiselect keys as args

                booked_list = '\n'.join(
                    "`{:>{}}` attendees | {}".format(
                        num,
                        attendee_pad,
                        time_format(start)
                    ) for start, num in attendees.items()
                )
                booked_field = (
                    "{}\n\n"
                    "*If you can't make your booking, please cancel using `{}rooms cancel`!*"
                ).format(booked_list, ctx.best_prefix)

                # Temporary footer for acclimatisation
                # footer = "All times are displayed in your own timezone!"
                footer = "Book another session using {}rooms book".format(ctx.best_prefix)
            else:
                booked_field = (
                    "Your schedule is empty!\n"
                    "Book another session using `{}rooms book`."
                ).format(ctx.best_prefix)
                footer = "Please keep your DMs open for notifications!"

            # Finally, build embed
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                description=desc,
            ).set_author(
                name="Accountability profile for {}".format(ctx.author.name),
                icon_url=ctx.author.avatar_url
            ).set_footer(
                text=footer,
                icon_url=hint_icon
            ).add_field(
                name="Upcoming sessions",
                value=booked_field
            )

            # And send it!
            await ctx.reply(embed=embed)


# TODO: roomadmin

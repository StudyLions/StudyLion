import re
import datetime
import discord
import asyncio
from cmdClient.checks import in_guild

from utils.lib import multiselect_regex, parse_ranges
from data import NOTNULL
from data.conditions import GEQ

from .module import module
from .lib import utc_now
from .data import accountability_members, accountability_member_info, accountability_open_slots, accountability_rooms


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
        Book an accountability session timeslot.
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
            "`[{:>2}]` | <t:{}:d><t:{}:t> - <t:{}:t>".format(
                i,
                int(row['start_at'].timestamp()),
                int(row['start_at'].timestamp()),
                int(row['start_at'].timestamp()) + 3600
            )
            for i, row in enumerate(joined_rows)
        ]
        out_msg = await ctx.reply(
            embed=discord.Embed(
                title="Please choose the bookings you want to cancel.",
                description='\n'.join(lines),
                colour=discord.Colour.orange()
            ).set_footer(
                text=(
                    "Reply with the number(s) of the rooms you want to join.\n"
                    "E.g. 1, 3, 5 or 1-5, 7-8."
                )
            )
        )

        def check(msg):
            valid = msg.channel == ctx.ch and msg.author == ctx.author
            valid = valid and (re.search(multiselect_regex, msg.content) or msg.content.lower() == 'c')
            return valid

        try:
            message = await ctx.client.wait_for('message', check=check, timeout=60)
        except asyncio.TimeoutError:
            await out_msg.delete()
            await ctx.error_reply("Session timed out. No accountability bookings were cancelled.")
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

        accountability_members.delete_where(
            userid=ctx.author.id,
            slotid=[row['slotid'] for row in to_cancel]
        )
        ctx.alion.addCoins(-cost)
        await ctx.embed_reply(
            "Successfully canceled your bookings."
        )
    # elif command == 'book':
    else:
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
            for n in range(3, 28)
        )
        times = list(time for time in times if time not in already_joined_times)
        lines = [
            "`[{:>2}]` | `{:>{}}` attending | <t:{}:d><t:{}:t> - <t:{}:t>".format(
                i,
                attendees.get(time, 0), attendee_pad,
                int(time.timestamp()), int(time.timestamp()), int(time.timestamp()) + 3600
            )
            for i, time in enumerate(times)
        ]
        # TODO: Nicer embed
        # TODO: Don't allow multi bookings if the member has a bad attendence rate
        out_msg = await ctx.reply(
            embed=discord.Embed(
                title="Please choose the sessions you want to book.",
                description='\n'.join(lines),
                colour=discord.Colour.orange()
            ).set_footer(
                text=(
                    "Reply with the number(s) of the rooms you want to join.\n"
                    "E.g. 1, 3, 5 or 1-5, 7-8."
                )
            )
        )

        def check(msg):
            valid = msg.channel == ctx.ch and msg.author == ctx.author
            valid = valid and (re.search(multiselect_regex, msg.content) or msg.content.lower() == 'c')
            return valid

        try:
            message = await ctx.client.wait_for('message', check=check, timeout=60)
        except asyncio.TimeoutError:
            await out_msg.delete()
            await ctx.error_reply("Session timed out. No accountability slots were booked.")
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

        slot_rows = accountability_rooms.fetch_rows_where(
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
        ctx.alion.addCoins(-cost)
        await ctx.embed_reply(
            "You have booked the following accountability sessions.\n{}".format(
                '\n'.join(
                    "<t:{}:d><t:{}:t> - <t:{}:t>".format(
                        int(time.timestamp()), int(time.timestamp()), int(time.timestamp() + 3600)
                    ) for time in to_book
                )
            )
        )
    # else:
    #     # Show current booking information
    #     embed = discord.Embed(
    #         title="Accountability Room Information"
    #     )
    #     ...


# TODO: roomadmin

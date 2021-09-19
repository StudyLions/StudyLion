import re
import datetime
import discord
import asyncio
from cmdClient.checks import in_guild

from utils.lib import multiselect_regex, parse_ranges
from data import NOTNULL

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
        ...
    """
    lower = ctx.args.lower()
    splits = lower.split()
    command = splits[0] if splits else None

    if not ctx.guild_settings.accountability_category.value:
        return await ctx.error_reply("The accountability system isn't set up!")

    if command == 'book':
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
        start_time = utc_now().replace(minute=0, second=0, microsecond=0)
        times = list(start_time + datetime.timedelta(hours=n) for n in range(0, 25))
        lines = [
            "`[{:>2}]` | `{:>{}}` attending | <t:{}:d><t:{}:t> - <t:{}:t>".format(
                i,
                attendees.get(time, 0), attendee_pad,
                int(time.timestamp()), int(time.timestamp()), int(time.timestamp()) + 3600
            )
            for i, time in enumerate(times)
        ]
        # TODO: Nicer embed
        # TODO: Remove the slots that the member already booked
        out_msg = await ctx.reply(
            embed=discord.Embed(
                title="Please choose the sessions you want to book.",
                description='\n'.join(lines),
                colour=discord.Colour.orange()
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

        # TODO: Make sure we aren't double-booking
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
        await ctx.embed_reply("You have booked `{}` accountability sessions.".format(len(to_book)))
    elif command == 'cancel':
        # Show unbooking menu
        await ctx.reply("[Placeholder text for cancel menu]")
        ...
    else:
        # Show current booking information
        await ctx.reply("[Placeholder text for current booking information]")
        ...


# TODO: roomadmin

"""
Shared commands for the moderation module.
"""
import asyncio
from collections import defaultdict
import discord

from wards import guild_moderator

from .module import module
from .tickets import Ticket, TicketType, TicketState


type_accepts = {
    'note': TicketType.NOTE,
    'notes': TicketType.NOTE,
    'studyban': TicketType.STUDY_BAN,
    'studybans': TicketType.STUDY_BAN,
    'warn': TicketType.WARNING,
    'warns': TicketType.WARNING,
    'warning': TicketType.WARNING,
    'warnings': TicketType.WARNING,
}

type_formatted = {
    TicketType.NOTE: 'NOTE',
    TicketType.STUDY_BAN: 'STUDYBAN',
    TicketType.WARNING: 'WARNING',
}

type_summary_formatted = {
    TicketType.NOTE: 'note',
    TicketType.STUDY_BAN: 'studyban',
    TicketType.WARNING: 'warning',
}

state_formatted = {
    TicketState.OPEN: 'ACTIVE',
    TicketState.EXPIRING: 'TEMP',
    TicketState.EXPIRED: 'EXPIRED',
    TicketState.PARDONED: 'PARDONED'
}


@module.cmd(
    "tickets",
    group="Moderation",
    desc="View and filter the server moderation tickets.",
    flags=('active', 'type=')
)
@guild_moderator()
async def cmd_tickets(ctx, flags):
    """
    Usage``:
        {prefix}tickets [@user] [--type <type>] [--active]
    Description:
        Display and optionally filter the moderation event history in this guild.
    Flags::
        type: Filter by ticket type. See **Ticket Types** below.
        active: Only show active tickets (i.e. hide expired and pardoned ones).
    Ticket Types::
        note: Moderation notes.
        warn: Moderation warnings, both manual and automatic.
        studyban: Bans from using study features from abusing the study system.
        blacklist: Complete blacklisting from using my commands.
    Examples:
        {prefix}tickets {ctx.guild.owner.mention} --type warn --active
    """
    # Parse filter fields
    # First the user
    if ctx.args:
        userstr = ctx.args.strip('<@!&> ')
        if not userstr.isdigit():
            return await ctx.error_reply(
                "**Usage:** `{prefix}tickets [@user] [--type <type>] [--active]`.\n"
                "Please provide the `user` as a mention or id!".format(prefix=ctx.best_prefix)
            )
        filter_userid = int(userstr)
    else:
        filter_userid = None

    if flags['type']:
        typestr = flags['type'].lower()
        if typestr not in type_accepts:
            return await ctx.error_reply(
                "Please see `{prefix}help tickets` for the valid ticket types!".format(prefix=ctx.best_prefix)
            )
        filter_type = type_accepts[typestr]
    else:
        filter_type = None

    filter_active = flags['active']

    # Build the filter arguments
    filters = {}
    if filter_userid:
        filters['targetid'] = filter_userid
    if filter_type:
        filters['ticket_type'] = filter_type
    if filter_active:
        filters['ticket_state'] = [TicketState.OPEN, TicketState.EXPIRING]

    # Fetch the tickets with these filters
    tickets = Ticket.fetch_tickets(**filters)

    if not tickets:
        if filters:
            return ctx.embed_reply("There are no tickets with these criteria!")
        else:
            return ctx.embed_reply("There are no moderation tickets in this server!")

    tickets = sorted(tickets, key=lambda ticket: ticket.data.guild_ticketid, reverse=True)
    ticket_map = {ticket.data.guild_ticketid: ticket for ticket in tickets}

    # Build the format string based on the filters
    components = []
    # Ticket id with link to message in mod log
    components.append("[#{ticket.data.guild_ticketid}]({ticket.link})")
    # Ticket creation date
    components.append("<t:{timestamp:.0f}:d>")
    # Ticket type, with current state
    if filter_type is None:
        if not filter_active:
            components.append("`{ticket_type}{ticket_state}`")
        else:
            components.append("`{ticket_type}`")
    elif not filter_active:
        components.append("`{ticket_real_state}`")
    if not filter_userid:
        # Ticket user
        components.append("<@{ticket.data.targetid}>")
    if filter_userid or (filter_active and filter_type):
        # Truncated ticket content
        components.append("{content}")

    format_str = ' | '.join(components)

    # Break tickets into blocks
    blocks = [tickets[i:i+10] for i in range(0, len(tickets), 10)]

    # Build pages of tickets
    ticket_pages = []
    for block in blocks:
        ticket_page = []

        type_len = max(len(type_formatted[ticket.type]) for ticket in block)
        state_len = max(len(state_formatted[ticket.state]) for ticket in block)
        for ticket in block:
            # First truncate content if required
            content = ticket.data.content
            if len(content) > 40:
                content = content[:37] + '...'

            # Build ticket line
            line = format_str.format(
                ticket=ticket,
                timestamp=ticket.data.created_at.timestamp(),
                ticket_type=type_formatted[ticket.type],
                type_len=type_len,
                ticket_state=" [{}]".format(state_formatted[ticket.state]) if ticket.state != TicketState.OPEN else '',
                ticket_real_state=state_formatted[ticket.state],
                state_len=state_len,
                content=content
            )
            if ticket.state == TicketState.PARDONED:
                line = "~~{}~~".format(line)

            # Add to current page
            ticket_page.append(line)
        # Combine lines and add page to pages
        ticket_pages.append('\n'.join(ticket_page))

    # Build summary
    freq = defaultdict(int)
    for ticket in tickets:
        if ticket.state != TicketState.PARDONED:
            freq[ticket.type] += 1
    summary_pairs = [
        (num, type_summary_formatted[ttype] + ('s' if num > 1 else ''))
        for ttype, num in freq.items()
    ]
    summary_pairs.sort(key=lambda pair: pair[0])
    # num_len = max(len(str(num)) for num in freq.values())
    # summary = '\n'.join(
    #     "**{}** {}".format(*pair)
    #     for pair in summary_pairs
    # )
    summary_strings = [
        "**`{}`** {}".format(*pair) for pair in summary_pairs
    ]
    if len(summary_strings) > 2:
        summary = ', '.join(summary_strings[:-1]) + ', and ' + summary_strings[-1]
    elif len(summary_strings) == 2:
        summary = ' and '.join(summary_strings)
    else:
        summary = ''.join(summary_strings)
    if summary:
        summary += '.'

    # Build embed info
    title = "{}{}{}".format(
        "Active " if filter_active else '',
        "{} tickets ".format(type_formatted[filter_type]) if filter_type else "Tickets ",
        (" for {}".format(ctx.guild.get_member(filter_userid) or filter_userid)
         if filter_userid else " in {}".format(ctx.guild.name))
    )
    footer = "Click a ticket id to jump to it, or type the number to show the full ticket."
    page_count = len(blocks)
    if page_count > 1:
        footer += "\nPage {{page_num}}/{}".format(page_count)

    # Create embeds
    embeds = [
        discord.Embed(
            title=title,
            description="{}\n{}".format(summary, page),
            colour=discord.Colour.orange(),
        ).set_footer(text=footer.format(page_num=i+1))
        for i, page in enumerate(ticket_pages)
    ]

    # Run output with cancellation and listener
    out_msg = await ctx.pager(embeds, add_cancel=True)
    display_task = asyncio.create_task(_ticket_display(ctx, ticket_map))
    ctx.tasks.append(display_task)
    await ctx.cancellable(out_msg, add_reaction=False)


async def _ticket_display(ctx, ticket_map):
    """
    Display tickets when the ticket number is entered.
    """
    current_ticket_msg = None

    try:
        while True:
            # Wait for a number
            try:
                result = await ctx.client.wait_for(
                    "message",
                    check=lambda msg: (msg.author == ctx.author
                                       and msg.channel == ctx.ch
                                       and msg.content.isdigit()
                                       and int(msg.content) in ticket_map)
                )
            except asyncio.TimeoutError:
                return

            # Delete the response
            try:
                await result.delete()
            except discord.HTTPException:
                pass

            # Display the ticket
            embed = ticket_map[int(result.content)].msg_args['embed']
            if current_ticket_msg:
                try:
                    await current_ticket_msg.edit(embed=embed)
                except discord.HTTPException:
                    current_ticket_msg = None

            if not current_ticket_msg:
                try:
                    current_ticket_msg = await ctx.reply(embed=embed)
                except discord.HTTPException:
                    return
                asyncio.create_task(ctx.offer_delete(current_ticket_msg))
    except asyncio.CancelledError:
        if current_ticket_msg:
            try:
                await current_ticket_msg.delete()
            except discord.HTTPException:
                pass

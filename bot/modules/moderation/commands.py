"""
Shared commands for the moderation module.
"""
import asyncio
from collections import defaultdict
import discord

from cmdClient.lib import ResponseTimedOut
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

state_summary_formatted = {
    TicketState.OPEN: 'Active',
    TicketState.EXPIRING: 'Temporary',
    TicketState.EXPIRED: 'Expired',
    TicketState.REVERTED: 'Manually Reverted',
    TicketState.PARDONED: 'Pardoned'
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
        active: Only show in-effect tickets (i.e. hide expired and pardoned ones).
    Ticket Types::
        note: Moderation notes.
        warn: Moderation warnings, both manual and automatic.
        studyban: Bans from using study features from abusing the study system.
        blacklist: Complete blacklisting from using my commands.
    Ticket States::
        Active: Active tickets that will not automatically expire.
        Temporary: Active tickets that will automatically expire after a set duration.
        Expired: Tickets that have automatically expired.
        Reverted: Tickets with actions that have been reverted.
        Pardoned: Tickets that have been pardoned and no longer apply to the user.
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

    # Build active ticket type summary
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
    # type_summary = '\n'.join(
    #     "**`{:<{}}`** {}".format(pair[0], num_len, pair[1])
    #     for pair in summary_pairs
    # )

    # # Build status summary
    # freq = defaultdict(int)
    # for ticket in tickets:
    #     freq[ticket.state] += 1
    # num_len = max(len(str(num)) for num in freq.values())
    # status_summary = '\n'.join(
    #     "**`{:<{}}`** {}".format(freq[state], num_len, state_str)
    #     for state, state_str in state_summary_formatted.items()
    #     if state in freq
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



@module.cmd(
    "pardon",
    group="Moderation",
    desc="Pardon a ticket, or clear a member's moderation history.",
    flags=('type=',)
)
@guild_moderator()
async def cmd_pardon(ctx, flags):
    """
    Usage``:
        {prefix}pardon ticketid, ticketid, ticketid
        {prefix}pardon @user [--type <type>]
    Description:
        Marks the given tickets as no longer applicable.
        These tickets will not be considered when calculating automod actions such as automatic study bans.

        This may be used to mark warns or other tickets as no longer in-effect.
        If the ticket is active when it is pardoned, it will be reverted, and any expiry cancelled.

        Use the `{prefix}tickets` command to view the relevant tickets.
    Flags::
        type: Filter by ticket type. See **Ticket Types** in `{prefix}help tickets`.
    Examples:
        {prefix}pardon 21
        {prefix}pardon {ctx.guild.owner.mention} --type warn
    """
    usage = "**Usage**: `{prefix}pardon ticketid` or `{prefix}pardon @user`.".format(prefix=ctx.best_prefix)
    if not ctx.args:
        return await ctx.error_reply(
            usage
        )

    # Parse provided tickets or filters
    targetid = None
    ticketids = []
    if ',' in ctx.args:
        # Assume provided numbers are ticketids.
        items = [item.strip() for item in ctx.args.split(',')]
        if not all(item.isdigit() for item in items):
            return await ctx.error_reply(usage)
        ticketids = [int(item) for item in items]
        args = {'guild_ticketid': ticketids}
    else:
        # Guess whether the provided numbers were ticketids or not
        idstr = ctx.args.strip('<@!&> ')
        if not idstr.isdigit():
            return await ctx.error_reply(usage)

        maybe_id = int(idstr)
        if maybe_id > 4194304:  # Testing whether it is greater than the minimum snowflake id
            # Assume userid
            targetid = maybe_id
            args = {'targetid': maybe_id}

            # Add the type filter if provided
            if flags['type']:
                typestr = flags['type'].lower()
                if typestr not in type_accepts:
                    return await ctx.error_reply(
                        "Please see `{prefix}help tickets` for the valid ticket types!".format(prefix=ctx.best_prefix)
                    )
                args['ticket_type'] = type_accepts[typestr]
        else:
            # Assume guild ticketid
            ticketids = [maybe_id]
            args = {'guild_ticketid': maybe_id}

    # Fetch the matching tickets
    tickets = Ticket.fetch_tickets(**args)

    # Check whether we have the right selection of tickets
    if targetid and not tickets:
        return await ctx.error_reply(
            "<@{}> has no matching tickets to pardon!"
        )
    if ticketids and len(ticketids) != len(tickets):
        # Not all of the ticketids were valid
        difference = list(set(ticketids).difference(ticket.ticketid for ticket in tickets))
        if len(difference) == 1:
            return await ctx.error_reply(
                "Couldn't find ticket `{}`!".format(difference[0])
            )
        else:
            return await ctx.error_reply(
                "Couldn't find any of the following tickets:\n`{}`".format(
                    '`, `'.join(difference)
                )
            )

    # Check whether there are any tickets left to pardon
    to_pardon = [ticket for ticket in tickets if ticket.state != TicketState.PARDONED]
    if not to_pardon:
        if ticketids and len(tickets) == 1:
            ticket = tickets[0]
            return await ctx.error_reply(
                "[Ticket #{}]({}) is already pardoned!".format(ticket.data.guild_ticketid, ticket.link)
            )
        else:
            return await ctx.error_reply(
                "All of these tickets are already pardoned!"
            )

    # We now know what tickets we want to pardon
    # Request the pardon reason
    try:
        reason = await ctx.input("Please provide a reason for the pardon.")
    except ResponseTimedOut:
        raise ResponseTimedOut("Prompt timed out, no tickets were pardoned.")

    # Pardon the tickets
    for ticket in to_pardon:
        await ticket.pardon(ctx.author, reason)

    # Finally, ack the pardon
    if targetid:
        await ctx.embed_reply(
            "The active {}s for <@{}> have been cleared.".format(
                type_summary_formatted[args['ticket_type']] if flags['type'] else 'ticket',
                targetid
            )
        )
    elif len(to_pardon) == 1:
        ticket = to_pardon[0]
        await ctx.embed_reply(
            "[Ticket #{}]({}) was pardoned.".format(
                ticket.data.guild_ticketid,
                ticket.link
            )
        )
    else:
        await ctx.embed_reply(
            "The following tickets were pardoned.\n{}".format(
                ", ".join(
                    "[#{}]({})".format(ticket.data.guild_ticketid, ticket.link)
                    for ticket in to_pardon
                )
            )
        )

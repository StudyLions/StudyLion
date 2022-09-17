"""
Note ticket implementation.

Guild moderators can add a note about a user, visible in their moderation history.
Notes appear in the moderation log and the user's ticket history, like any other ticket.

This module implements the Note TicketType and the `note` moderation command.
"""
from cmdClient.lib import ResponseTimedOut

from wards import guild_moderator

from ..module import module
from ..data import tickets

from .Ticket import Ticket, TicketType, TicketState


@Ticket.register_ticket_type
class NoteTicket(Ticket):
    _ticket_type = TicketType.NOTE

    @classmethod
    async def create(cls, guildid, targetid, moderatorid, content, **kwargs):
        """
        Create a new Note on a target.

        `kwargs` are passed transparently to the table insert method.
        """
        ticket_row = tickets.insert(
            guildid=guildid,
            targetid=targetid,
            ticket_type=cls._ticket_type,
            ticket_state=TicketState.OPEN,
            moderator_id=moderatorid,
            auto=False,
            content=content,
            **kwargs
        )

        # Create the note ticket
        ticket = cls(ticket_row['ticketid'])

        # Post the ticket and return
        await ticket.post()
        return ticket


@module.cmd(
    "note",
    group="Moderation",
    desc="Add a Note to a member's record."
)
@guild_moderator()
async def cmd_note(ctx):
    """
    Usage``:
        {prefix}note @target
        {prefix}note @target <content>
    Description:
        Add a note to the target's moderation record.
        The note will appear in the moderation log and in the `tickets` command.

        The `target` must be specificed by mention or user id.
        If the `content` is not given, it will be prompted for.
    Example:
        {prefix}note {ctx.author.mention} Seen reading the `note` documentation.
    """
    if not ctx.args:
        return await ctx.error_reply(
            "**Usage:** `{}note @target <content>`.".format(ctx.best_prefix)
        )

    # Extract the target. We don't require them to be in the server
    splits = ctx.args.split(maxsplit=1)
    target_str = splits[0].strip('<@!&> ')
    if not target_str.isdigit():
        return await ctx.error_reply(
            "**Usage:** `{}note @target <content>`.\n"
            "`target` must be provided by mention or userid.".format(ctx.best_prefix)
        )
    targetid = int(target_str)

    # Extract or prompt for the content
    if len(splits) != 2:
        try:
            content = await ctx.input("What note would you like to add?", timeout=300)
        except ResponseTimedOut:
            raise ResponseTimedOut("Prompt timed out, no note was created.")
    else:
        content = splits[1].strip()

    # Create the note ticket
    ticket = await NoteTicket.create(
        ctx.guild.id,
        targetid,
        ctx.author.id,
        content
    )

    if ticket.data.log_msg_id:
        await ctx.embed_reply(
            "Note on <@{}> created as [Ticket #{}]({}).".format(
                targetid,
                ticket.data.guild_ticketid,
                ticket.link
            )
        )
    else:
        await ctx.embed_reply(
            "Note on <@{}> created as Ticket #{}.".format(targetid, ticket.data.guild_ticketid)
        )

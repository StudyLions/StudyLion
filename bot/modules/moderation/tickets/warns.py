"""
Warn ticket implementation.

Guild moderators can officially warn a user via command.
This DMs the users with the warning.
"""
import datetime
import discord
from cmdClient.lib import ResponseTimedOut

from wards import guild_moderator

from ..module import module
from ..data import tickets

from .Ticket import Ticket, TicketType, TicketState


@Ticket.register_ticket_type
class WarnTicket(Ticket):
    _ticket_type = TicketType.WARNING

    @classmethod
    async def create(cls, guildid, targetid, moderatorid, content, **kwargs):
        """
        Create a new Warning for the target.

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

    async def _revert(*args, **kwargs):
        # Warnings don't have a revert process
        pass


@module.cmd(
    "warn",
    group="Moderation",
    desc="Officially warn a user for a misbehaviour."
)
@guild_moderator()
async def cmd_warn(ctx):
    """
    Usage``:
        {prefix}warn @target
        {prefix}warn @target <reason>
    Description:

        The `target` must be specificed by mention or user id.
        If the `reason` is not given, it will be prompted for.
    Example:
        {prefix}warn {ctx.author.mention} Don't actually read the documentation!
    """
    if not ctx.args:
        return await ctx.error_reply(
            "**Usage:** `{}warn @target <reason>`.".format(ctx.best_prefix)
        )

    # Extract the target. We do require them to be in the server
    splits = ctx.args.split(maxsplit=1)
    target_str = splits[0].strip('<@!&> ')
    if not target_str.isdigit():
        return await ctx.error_reply(
            "**Usage:** `{}warn @target <reason>`.\n"
            "`target` must be provided by mention or userid.".format(ctx.best_prefix)
        )
    targetid = int(target_str)
    target = ctx.guild.get_member(targetid)
    if not target:
        return await ctx.error_reply("Cannot warn a user who is not in the server!")

    # Extract or prompt for the content
    if len(splits) != 2:
        try:
            content = await ctx.input("Please give a reason for this warning!", timeout=300)
        except ResponseTimedOut:
            raise ResponseTimedOut("Prompt timed out, the member was not warned.")
    else:
        content = splits[1].strip()

    # Create the warn ticket
    ticket = await WarnTicket.create(
        ctx.guild.id,
        targetid,
        ctx.author.id,
        content
    )

    # Attempt to message the member
    embed = discord.Embed(
        title="You have received a warning!",
        description=(
            content
        ),
        colour=discord.Colour.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(
        name="Info",
        value=(
            "*Warnings appear in your moderation history. "
            "Failure to comply, or repeated warnings, "
            "may result in muting, studybanning, or server banning.*"
        )
    )
    embed.set_footer(
        icon_url=ctx.guild.icon_url,
        text=ctx.guild.name
    )
    dm_msg = None
    try:
        dm_msg = await target.send(embed=embed)
    except discord.HTTPException:
        pass

    # Get previous warnings
    count = tickets.select_one_where(
        guildid=ctx.guild.id,
        targetid=targetid,
        ticket_type=TicketType.WARNING,
        ticket_state=[TicketState.OPEN, TicketState.EXPIRING],
        select_columns=('COUNT(*)',)
    )[0]
    if count == 1:
        prev_str = "This is their first warning."
    else:
        prev_str = "They now have `{}` warnings.".format(count)

    await ctx.embed_reply(
        "[Ticket #{}]({}): {} has been warned. {}\n{}".format(
            ticket.data.guild_ticketid,
            ticket.link,
            target.mention,
            prev_str,
            "*Could not DM the user their warning!*" if not dm_msg else ''
        )
    )

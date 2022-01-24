import discord

from meta import conf

from LionContext import LionContext as Context

from .module import module


@module.cmd(
    "support",
    group="Meta",
    desc=f"Have a question? Join my [support server]({conf.bot.get('support_link')})"
)
async def cmd_support(ctx: Context):
    """
    Usage``:
        {prefix}support
    Description:
        Replies with an invite link to my support server.
    """
    await ctx.reply(
        f"Click here to join my support server: {conf.bot.get('support_link')}"
    )


@module.cmd(
    "invite",
    group="Meta",
    desc=f"[Invite me]({conf.bot.get('invite_link')}) to your server so I can help your members stay productive!"
)
async def cmd_invite(ctx: Context):
    """
    Usage``:
        {prefix}invite
    Description:
        Replies with my invite link so you can add me to your server.
    """
    embed = discord.Embed(
        colour=discord.Colour.orange(),
        description=f"Click here] to add me to your server: {conf.bot.get('invite_link')}"
    )
    embed.add_field(
        name="Setup tips",
        value=(
            "Remember to check out `{prefix}help` for the full command list, "
            "and `{prefix}config info` for the configuration options.\n"
            "[Click here]({guide}) for our comprehensive setup tutorial, and if you still have questions you can "
            "join our support server [here]({support}) to talk to our friendly support team!"
        ).format(
            prefix=ctx.best_prefix,
            support=conf.bot.get('support_link'),
            guide="https://discord.studylions.com/tutorial"
        )
    )
    await ctx.reply(embed=embed)

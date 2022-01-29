import discord
from .module import module
from cmdClient.checks import is_owner
from settings.user_settings import UserSettings
from LionContext import LionContext

from .webhook import on_dbl_vote
from .utils import lion_loveemote


@module.cmd(
    "forcevote",
    desc="Simulate a Topgg Vote from the given user.",
    group="Bot Admin",
)
@is_owner()
async def cmd_forcevote(ctx: LionContext):
    """
    Usage``:
        {prefix}forcevote
    Description:
        Simulate Top.gg vote without actually a confirmation from Topgg site.

        Can be used for force a vote for testing or if topgg has an error or production time bot error.
    """
    target = ctx.author

    # Identify the target
    if ctx.args:
        if not ctx.msg.mentions:
            return await ctx.error_reply("Please mention a user to simulate a vote!")
        target = ctx.msg.mentions[0]

    await on_dbl_vote({"user": target.id, "type": "test"})
    return await ctx.reply('Topgg vote simulation successful on {}'.format(target), suggest_vote=False)


@module.cmd(
    "vote",
    desc="[Vote](https://top.gg/bot/889078613817831495/vote) for me to get 25% more LCs!",
    group="Economy",
    aliases=('topgg', 'topggvote', 'upvote')
)
async def cmd_vote(ctx: LionContext):
    """
    Usage``:
        {prefix}vote
    Description:
        Get Top.gg bot's link for +25% Economy boost.
    """
    embed = discord.Embed(
        title="Claim your boost!",
        description=(
            "Please click [here](https://top.gg/bot/889078613817831495/vote) to vote and support our bot!\n\n"
            "Thank you! {}.".format(lion_loveemote)
        ),
        colour=discord.Colour.orange()
    ).set_thumbnail(
        url="https://cdn.discordapp.com/attachments/908283085999706153/933012309532614666/lion-love.png"
    )
    return await ctx.reply(embed=embed, suggest_vote=False)


@module.cmd(
    "vote_reminder",
    group="Personal Settings",
    desc="Turn on/off boost reminders."
)
async def cmd_remind_vote(ctx: LionContext):
    """
    Usage:
        `{prefix}vote_reminder on`
        `{prefix}vote_reminder off`

    Enable or disable DM boost reminders.
    """
    await UserSettings.settings.vote_remainder.command(ctx, ctx.author.id)

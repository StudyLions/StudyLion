import discord
from .module import module
from wards import guild_admin
from bot.cmdClient.checks.global_perms import in_guild
from settings.user_settings import UserSettings

from .webhook import on_dbl_vote
from .utils import *

@module.cmd(
    "forcevote",
    desc="Simulate Topgg Vote.",
    group="Guild Admin",
    aliases=('debugvote', 'topggvote')
)
@guild_admin()
async def cmd_forcevote(ctx):
    """
    Usage``:
        {prefix}forcevote
    Description:
        Simulate Topgg Vote without actually a confirmation from Topgg site.

        Can be used for force a vote for testing or if topgg has an error or production time bot error.
    """
    target = ctx.author
    # Identify the target
    if ctx.args:
        if not ctx.msg.mentions:
            return await ctx.error_reply("Please mention a user to simulate a vote!")
        target = ctx.msg.mentions[0]

    await on_dbl_vote({"user": target.id, "type": "test"})
    return await ctx.reply('Topgg vote simulation successful on {}'.format(target))


@module.cmd(
    "vote",
    desc="Get top.gg boost for 25% more LCs.",
    group="Economy",
    aliases=('topgg', 'topggvote', 'upvote')
)
@in_guild()
async def cmd_vote(ctx):
    """
    Usage``:
        {prefix}vote
    Description:
        Get Top.gg bot's link for +25% Economy boost.
    """
    target = ctx.author

    embed=discord.Embed(
        title="Claim your boost!",
        description='Please click [here](https://top.gg/bot/889078613817831495/vote) vote and support our bot!\n\nThank you! {}.'.format(lion_loveemote),
        colour=discord.Colour.orange()
    ).set_thumbnail(
        url="https://cdn.discordapp.com/attachments/908283085999706153/933012309532614666/lion-love.png"
    )
    return await ctx.reply(embed=embed)


@module.cmd(
    "vote_reminder",
    group="Personal Settings",
    desc="Turn on/off boost reminders."
)
async def cmd_remind_vote(ctx):
    """
    Usage:
        `{prefix}vote_reminder on`
        `{prefix}vote_reminder off`

    Enable or disable DM boost reminders.
    """    
    await UserSettings.settings.vote_remainder.command(ctx, ctx.author.id)

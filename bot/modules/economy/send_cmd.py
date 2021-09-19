import discord
import datetime
from cmdClient.checks import in_guild

from settings import GuildSettings
from core import Lion

from .module import module


@module.cmd(
    "send",
    group="Economy",
    desc="Send some coins to another member."
)
@in_guild()
async def cmd_send(ctx):
    """
    Usage``:
        {prefix}send <user mention> <amount>
    Description:
        Send the given number of coins to the mentioned user.
    Example:
        {prefix}send {ctx.author.mention} 1000000
    """
    # Extract target and amount
    # Handle a slightly more flexible input than stated
    splits = ctx.args.split()
    digits = [split.isdigit() for split in splits]
    mentions = ctx.msg.mentions
    if len(splits) < 2 or not any(digits) or not (all(digits) or mentions):
        return await _send_usage(ctx)

    if all(digits):
        # Both are digits, hopefully one is a member id, and one is an amount.
        target, amount = ctx.guild.get_member(int(splits[0])), int(splits[1])
        if not target:
            amount, target = int(splits[0]), ctx.guild.get_member(int(splits[1]))
        if not target:
            return await _send_usage(ctx)
    elif digits[0]:
        amount, target = int(splits[0]), mentions[0]
    elif digits[1]:
        target, amount = mentions[0], int(splits[1])

    # Fetch the associated lions
    target_lion = Lion.fetch(ctx.guild.id, target.id)
    source_lion = Lion.fetch(ctx.guild.id, ctx.author.id)

    # Check sanity conditions
    if amount > source_lion.coins:
        return await ctx.error_reply(
            "Sorry {}, you do not have enough LionCoins to do that.".format(ctx.author.mention)
        )
    if target == ctx.author:
        return await ctx.embed_reply("What is this, tax evasion?")
    if target == ctx.client.user:
        return await ctx.embed_reply("Thanks, but Ari looks after all my needs!")
    if target.bot:
        return await ctx.embed_reply("We are still waiting for {} to open an account.".format(target.mention))

    # Finally, send the amount and the ack message
    target_lion.addCoins(amount)
    source_lion.addCoins(-amount)

    embed = discord.Embed(
        title="Funds transferred",
        description="You have sent **{}** LionCoins to {}!".format(amount, target.mention),
        colour=discord.Colour.orange(),
        timestamp=datetime.datetime.utcnow()
    ).set_footer(text=str(ctx.author), icon_url=ctx.author.avatar_url)

    await ctx.reply(embed=embed, reference=ctx.msg)
    await GuildSettings(ctx.guild.id).event_log.log(
        "{} sent {} `{}` LionCoins.".format(
            ctx.author.mention,
            target.mention,
            amount
        ),
        title="Funds transferred"
    )


async def _send_usage(ctx):
    return await ctx.error_reply(
        "**Usage:** `{prefix}send <mention> <amount>`\n"
        "**Example:** {prefix}send {ctx.author.mention} 1000000".format(
            prefix=ctx.best_prefix,
            ctx=ctx
        )
    )

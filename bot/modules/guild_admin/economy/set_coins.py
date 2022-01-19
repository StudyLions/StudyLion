import discord
import datetime
from wards import guild_admin

from settings import GuildSettings
from core import Lion

from ..module import module

POSTGRES_INT_MAX = 2147483647

@module.cmd(
    "set_coins",
    group="Guild Admin",
    desc="Set coins on a member."
)
@guild_admin()
async def cmd_set(ctx):
    """
    Usage``:
        {prefix}set_coins <user mention> <amount>
    Description:
        Sets the given number of coins on the mentioned user.
        If a number greater than 0 is mentioned, will add coins.
        If a number less than 0 is mentioned, will remove coins.
        Note: LionCoins on a member cannot be negative.
    Example:
        {prefix}set_coins {ctx.author.mention} 100
        {prefix}set_coins {ctx.author.mention} -100
    """
    # Extract target and amount
    # Handle a slightly more flexible input than stated
    splits = ctx.args.split()
    digits = [isNumber(split) for split in splits[:2]]
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

    # Fetch the associated lion
    target_lion = Lion.fetch(ctx.guild.id, target.id)

    # Check sanity conditions
    if target == ctx.client.user:
        return await ctx.embed_reply("Thanks, but Ari looks after all my needs!")
    if target.bot:
        return await ctx.embed_reply("We are still waiting for {} to open an account.".format(target.mention))

    # Finally, send the amount and the ack message
    # Postgres `coins` column is `integer`, sanity check postgres int limits - which are smalled than python int range
    target_coins_to_set = target_lion.coins + amount
    if target_coins_to_set >= 0 and target_coins_to_set <= POSTGRES_INT_MAX:
        target_lion.addCoins(amount, ignorebonus=True)
    elif target_coins_to_set < 0:
        target_coins_to_set = -target_lion.coins # Coins cannot go -ve, cap to 0
        target_lion.addCoins(target_coins_to_set, ignorebonus=True)
        target_coins_to_set = 0
    else:
        return await ctx.embed_reply("Member coins cannot be more than {}".format(POSTGRES_INT_MAX))

    embed = discord.Embed(
        title="Funds Set",
        description="You have set LionCoins on {} to **{}**!".format(target.mention,target_coins_to_set),
        colour=discord.Colour.orange(),
        timestamp=datetime.datetime.utcnow()
    ).set_footer(text=str(ctx.author), icon_url=ctx.author.avatar_url)

    await ctx.reply(embed=embed, reference=ctx.msg)
    GuildSettings(ctx.guild.id).event_log.log(
        "{} set {}'s LionCoins to`{}`.".format(
            ctx.author.mention,
            target.mention,
            target_coins_to_set
        ),
        title="Funds Set"
    )

def isNumber(var):
    try:
        return isinstance(int(var), int)
    except:
        return False

async def _send_usage(ctx):
    return await ctx.error_reply(
        "**Usage:** `{prefix}set_coins <mention> <amount>`\n"
        "**Example:**\n"
        "  {prefix}set_coins {ctx.author.mention} 100\n"
        "  {prefix}set_coins {ctx.author.mention} -100".format(
            prefix=ctx.best_prefix,
            ctx=ctx
        )
    )

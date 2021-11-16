import datetime
import discord
from cmdClient.checks import in_guild

from utils.lib import strfdur
from data import tables
from core import Lion

from .module import module


@module.cmd(
    "stats",
    group="Statistics",
    desc="View a summary of your study statistics!",
    allow_before_ready=True
)
@in_guild()
async def cmd_stats(ctx):
    """
    Usage``:
        {prefix}stats
        {prefix}stats <user mention>
    Description:
        View the study statistics for yourself or the mentioned user.
    """
    if ctx.args:
        if not ctx.msg.mentions:
            return await ctx.error_reply("Please mention a user to view their statistics!")
        target = ctx.msg.mentions[0]
    else:
        target = ctx.author

    # Collect the required target data
    lion = Lion.fetch(ctx.guild.id, target.id)
    rank_data = tables.lion_ranks.select_one_where(
        userid=target.id,
        guildid=ctx.guild.id
    )

    # Extract and format data
    time = strfdur(lion.time)
    coins = lion.coins
    workouts = lion.data.workout_count
    if lion.data.last_study_badgeid:
        badge_row = tables.study_badges.fetch(lion.data.last_study_badgeid)
        league = "<@&{}>".format(badge_row.roleid)
    else:
        league = "No league yet!"

    time_lb_pos = rank_data['time_rank']
    coin_lb_pos = rank_data['coin_rank']

    # Build embed
    embed = discord.Embed(
        colour=discord.Colour.blue(),
        timestamp=datetime.datetime.utcnow(),
        title="Revision Statistics"
    ).set_footer(text=str(target), icon_url=target.avatar_url).set_thumbnail(url=target.avatar_url)
    embed.add_field(
        name="📚 Study Time",
        value=time
    )
    embed.add_field(
        name="🦁 Revision League",
        value=league
    )
    embed.add_field(
        name="🦁 LionCoins",
        value=coins
    )
    embed.add_field(
        name="🏆 Leaderboard Position",
        value="Time: {}\n LC: {}".format(time_lb_pos, coin_lb_pos)
    )
    embed.add_field(
        name="💪 Workouts",
        value=workouts
    )
    embed.add_field(
        name="📋 Attendence",
        value="TBD"
    )
    await ctx.reply(embed=embed)

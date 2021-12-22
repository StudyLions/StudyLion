from datetime import datetime, timedelta
import discord
from cmdClient.checks import in_guild

from utils.lib import prop_tabulate, utc_now
from data import tables
from data.conditions import LEQ
from core import Lion

from .tracking.data import session_history

from .module import module


@module.cmd(
    "stats",
    group="Statistics",
    desc="View your personal server study statistics!",
    aliases=('profile',),
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
    # Identify the target
    if ctx.args:
        if not ctx.msg.mentions:
            return await ctx.error_reply("Please mention a user to view their statistics!")
        target = ctx.msg.mentions[0]
    else:
        target = ctx.author

    # System sync
    Lion.sync()

    # Fetch the required data
    lion = Lion.fetch(ctx.guild.id, target.id)

    history = session_history.select_where(
        guildid=ctx.guild.id,
        userid=target.id,
        select_columns=(
            "start_time",
            "(start_time + duration * interval '1 second') AS end_time"
        ),
        _extra="ORDER BY start_time DESC"
    )

    # Current economy balance (accounting for current session)
    coins = lion.coins
    season_time = lion.time
    workout_total = lion.data.workout_count

    # Leaderboard ranks
    exclude = set(m.id for m in ctx.guild_settings.unranked_roles.members)
    exclude.update(ctx.client.user_blacklist())
    exclude.update(ctx.client.objects['ignored_members'][ctx.guild.id])
    if target.id in exclude:
        time_rank = None
        coin_rank = None
    else:
        time_rank, coin_rank = tables.lions.queries.get_member_rank(ctx.guild.id, target.id, list(exclude or [0]))

    # Study time
    # First get the all/month/week/day timestamps
    day_start = lion.day_start
    period_timestamps = (
        datetime(1970, 1, 1),
        day_start.replace(day=1),
        day_start - timedelta(days=day_start.weekday()),
        day_start
    )
    study_times = [0, 0, 0, 0]
    for i, timestamp in enumerate(period_timestamps):
        study_time = tables.session_history.queries.study_time_since(ctx.guild.id, target.id, timestamp)
        if not study_time:
            # So we don't make unecessary database calls
            break
        study_times[i] = study_time

    # Streak statistics
    streak = 0
    current_streak = None
    max_streak = 0

    day_attended = True if 'sessions' in ctx.client.objects and lion.session else None
    date = day_start
    daydiff = timedelta(days=1)

    periods = [(row['start_time'], row['end_time']) for row in history]

    i = 0
    while i < len(periods):
        row = periods[i]
        i += 1
        if row[1] > date:
            # They attended this day
            day_attended = True
            continue
        elif day_attended is None:
            # Didn't attend today, but don't break streak
            day_attended = False
            date -= daydiff
            i -= 1
            continue
        elif not day_attended:
            # Didn't attend the day, streak broken
            date -= daydiff
            i -= 1
            pass
        else:
            # Attended the day
            streak += 1

            # Move window to the previous day and try the row again
            day_attended = False
            prev_date = date
            date -= daydiff
            i -= 1

            # Special case, when the last session started in the previous day
            # Then the day is already attended
            if i > 1 and date < periods[i-2][0] <= prev_date:
                day_attended = True

            continue

        max_streak = max(max_streak, streak)
        if current_streak is None:
            current_streak = streak
        streak = 0

    # Handle loop exit state, i.e. the last streak
    if day_attended:
        streak += 1
    max_streak = max(max_streak, streak)
    if current_streak is None:
        current_streak = streak

    # Accountability stats
    accountability = tables.accountability_member_info.select_where(
        userid=target.id,
        start_at=LEQ(utc_now()),
        select_columns=("*", "(duration > 0 OR last_joined_at IS NOT NULL) AS attended"),
        _extra="ORDER BY start_at DESC"
    )
    if len(accountability):
        acc_duration = sum(row['duration'] for row in accountability)

        acc_attended = sum(row['attended'] for row in accountability)
        acc_total = len(accountability)
        acc_rate = (acc_attended * 100) / acc_total
    else:
        acc_duration = 0
        acc_rate = 0

    # Study League
    guild_badges = tables.study_badges.fetch_rows_where(guildid=ctx.guild.id)
    if lion.data.last_study_badgeid:
        current_badge = tables.study_badges.fetch(lion.data.last_study_badgeid)
    else:
        current_badge = None

    next_badge = min(
        (badge for badge in guild_badges
         if badge.required_time > (current_badge.required_time if current_badge else 0)),
        key=lambda badge: badge.required_time,
        default=None
    )

    # We have all the data
    # Now start building the embed
    embed = discord.Embed(
        colour=discord.Colour.orange(),
        title="Study Profile for {}".format(str(target))
    )
    embed.set_thumbnail(url=target.avatar_url)

    # Add studying since if they have studied
    if history:
        embed.set_footer(text="Studying Since")
        embed.timestamp = history[-1]['start_time']

    # Set the description based on season time and server rank
    if season_time:
        time_str = "**{}:{:02}**".format(
            season_time // 3600,
            (season_time // 60) % 60
        )
        if time_rank is None:
            rank_str = None
        elif time_rank == 1:
            rank_str = "1st"
        elif time_rank == 2:
            rank_str = "2nd"
        elif time_rank == 3:
            rank_str = "3rd"
        else:
            rank_str = "{}th".format(time_rank)

        embed.description = "{} has studied for **{}**{}{}".format(
            target.mention,
            time_str,
            " this season" if study_times[0] - season_time > 60 else "",
            ", and is ranked **{}** in the server!".format(rank_str) if rank_str else "."
        )
    else:
        embed.description = "{} hasn't studied in this server yet!".format(target.mention)

    # Build the stats table
    stats = {}

    stats['Coins Earned'] = "**{}** LC".format(
        coins,
        # "Rank `{}`".format(coin_rank) if coins and coin_rank else "Unranked"
    )
    if workout_total:
        stats['Workouts'] = "**{}** sessions".format(workout_total)
    if acc_duration:
        stats['Accountability'] = "**{}** hours (`{:.0f}%` attended)".format(
            acc_duration // 3600,
            acc_rate
        )
    stats['Study Streak'] = "**{}** days{}".format(
        current_streak,
        " (longest **{}** days)".format(max_streak) if max_streak else ''
    )

    stats_table = prop_tabulate(*zip(*stats.items()))

    # Build the time table
    time_table = prop_tabulate(
        ('Daily', 'Weekly', 'Monthly', 'All Time'),
        ["{:02}:{:02}".format(t // 3600, (t // 60) % 60) for t in reversed(study_times)]
    )

    # Populate the embed
    embed.add_field(name="Study Time", value=time_table)
    embed.add_field(name="Statistics", value=stats_table)

    # Add the study league field
    if current_badge or next_badge:
        current_str = (
            "You are currently in <@&{}>!".format(current_badge.roleid) if current_badge else "No league yet!"
        )
        if next_badge:
            needed = max(next_badge.required_time - season_time, 0)
            next_str = "Study for **{:02}:{:02}** more to achieve <@&{}>.".format(
                needed // 3600,
                (needed // 60) % 60,
                next_badge.roleid
            )
        else:
            next_str = "You have reached the highest league! Congratulations!"
        embed.add_field(
            name="Study League",
            value="{}\n{}".format(current_str, next_str),
            inline=False
        )
    await ctx.reply(embed=embed)

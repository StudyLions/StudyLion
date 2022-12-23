from datetime import timedelta
import asyncio

from data.conditions import GEQ

from modules.stats import goals

from ..module import module, ratelimit

from ...cards import WeeklyGoalCard, MonthlyGoalCard
from ...cards import WeeklyStatsCard, MonthlyStatsCard
from ...utils import get_avatar_key, image_as_file


async def _get_weekly_goals(ctx):
    # Fetch goal data
    goal_row = ctx.client.data.weekly_goals.fetch_or_create(
        (ctx.guild.id, ctx.author.id, ctx.alion.week_timestamp)
    )
    tasklist_rows = ctx.client.data.member_weekly_goal_tasks.select_where(
        guildid=ctx.guild.id,
        userid=ctx.author.id,
        weekid=ctx.alion.week_timestamp,
        _extra="ORDER BY taskid ASC"
    )
    tasklist = [
        (i, task['content'], task['completed'])
        for i, task in enumerate(tasklist_rows)
    ]

    day_start = ctx.alion.day_start
    week_start = day_start - timedelta(days=day_start.weekday())

    # Fetch study data
    week_study_time = ctx.client.data.session_history.queries.study_time_since(
        ctx.guild.id, ctx.author.id, week_start
    )
    study_hours = week_study_time // 3600

    # Fetch task data
    tasks_done = ctx.client.data.tasklist.select_one_where(
        userid=ctx.author.id,
        completed_at=GEQ(week_start),
        select_columns=('COUNT(*)',)
    )[0]

    # Fetch accountability data
    accountability = ctx.client.data.accountability_member_info.select_where(
        userid=ctx.author.id,
        start_at=GEQ(week_start),
        select_columns=("*", "(duration > 0 OR last_joined_at IS NOT NULL) AS attended"),
    )
    if len(accountability):
        acc_attended = sum(row['attended'] for row in accountability)
        acc_total = len(accountability)
        acc_rate = acc_attended / acc_total
    else:
        acc_rate = None

    goalpage = await WeeklyGoalCard.request(
        name=ctx.author.name,
        discrim=f"#{ctx.author.discriminator}",
        avatar=get_avatar_key(ctx.client, ctx.author.id),
        badges=ctx.alion.profile_tags,
        tasks_done=tasks_done,
        studied_hours=study_hours,
        attendance=acc_rate,
        tasks_goal=goal_row.task_goal,
        studied_goal=goal_row.study_goal,
        goals=tasklist,
        date=ctx.alion.day_start,
        skin=WeeklyGoalCard.skin_args_for(ctx)
    )
    return goalpage


@ratelimit.ward()
async def show_weekly_goals(ctx):
    image = await _get_weekly_goals(ctx)
    await ctx.reply(file=image_as_file(image, 'weekly_stats_1.png'))

goals.display_weekly_goals_for = show_weekly_goals


@module.cmd(
    "weekly",
    group="Statistics",
    desc="View your weekly study statistics!"
)
@ratelimit.ward()
async def cmd_weekly(ctx):
    """
    Usage``:
        {prefix}weekly
    Description:
        View your weekly study profile.
        See `{prefix}weeklygoals` to edit your goals!
    """
    day_start = ctx.alion.day_start
    last_week_start = day_start - timedelta(days=7 + day_start.weekday())

    history = ctx.client.data.session_history.select_where(
        guildid=ctx.guild.id,
        userid=ctx.author.id,
        start_time=GEQ(last_week_start - timedelta(days=1)),
        select_columns=(
            "start_time",
            "(start_time + duration * interval '1 second') AS end_time"
        ),
        _extra="ORDER BY start_time ASC"
    )
    timezone = ctx.alion.timezone
    sessions = [(row['start_time'].astimezone(timezone), row['end_time'].astimezone(timezone)) for row in history]

    page_1_task = asyncio.create_task(_get_weekly_goals(ctx))
    page_2_task = asyncio.create_task(
        WeeklyStatsCard.request(
            ctx.author.name,
            f"#{ctx.author.discriminator}",
            sessions,
            day_start,
            skin=WeeklyStatsCard.skin_args_for(ctx)
        )
    )

    await asyncio.gather(page_1_task, page_2_task)
    page_1 = page_1_task.result()
    page_2 = page_2_task.result()

    await ctx.reply(
        files=[
            image_as_file(page_1, "weekly_stats_1.png"),
            image_as_file(page_2, "weekly_stats_2.png")
        ]
    )


async def _get_monthly_goals(ctx):
    # Fetch goal data
    goal_row = ctx.client.data.monthly_goals.fetch_or_create(
        (ctx.guild.id, ctx.author.id, ctx.alion.month_timestamp)
    )
    tasklist_rows = ctx.client.data.member_monthly_goal_tasks.select_where(
        guildid=ctx.guild.id,
        userid=ctx.author.id,
        monthid=ctx.alion.month_timestamp,
        _extra="ORDER BY taskid ASC"
    )
    tasklist = [
        (i, task['content'], task['completed'])
        for i, task in enumerate(tasklist_rows)
    ]

    day_start = ctx.alion.day_start
    month_start = day_start.replace(day=1)

    # Fetch study data
    month_study_time = ctx.client.data.session_history.queries.study_time_since(
        ctx.guild.id, ctx.author.id, month_start
    )
    study_hours = month_study_time // 3600

    # Fetch task data
    tasks_done = ctx.client.data.tasklist.select_one_where(
        userid=ctx.author.id,
        completed_at=GEQ(month_start),
        select_columns=('COUNT(*)',)
    )[0]

    # Fetch accountability data
    accountability = ctx.client.data.accountability_member_info.select_where(
        userid=ctx.author.id,
        start_at=GEQ(month_start),
        select_columns=("*", "(duration > 0 OR last_joined_at IS NOT NULL) AS attended"),
    )
    if len(accountability):
        acc_attended = sum(row['attended'] for row in accountability)
        acc_total = len(accountability)
        acc_rate = acc_attended / acc_total
    else:
        acc_rate = None

    goalpage = await MonthlyGoalCard.request(
        name=ctx.author.name,
        discrim=f"#{ctx.author.discriminator}",
        avatar=get_avatar_key(ctx.client, ctx.author.id),
        badges=ctx.alion.profile_tags,
        tasks_done=tasks_done,
        studied_hours=study_hours,
        attendance=acc_rate,
        tasks_goal=goal_row.task_goal,
        studied_goal=goal_row.study_goal,
        goals=tasklist,
        date=ctx.alion.day_start,
        skin=MonthlyGoalCard.skin_args_for(ctx)
    )
    return goalpage


@ratelimit.ward()
async def show_monthly_goals(ctx):
    image = await _get_monthly_goals(ctx)
    await ctx.reply(file=image_as_file(image, 'monthly_stats_1.png'))

goals.display_monthly_goals_for = show_monthly_goals


@module.cmd(
    "monthly",
    group="Statistics",
    desc="View your monthly study statistics!"
)
async def cmd_monthly(ctx):
    """
    Usage``:
        {prefix}monthly
    Description:
        View your monthly study profile.
        See `{prefix}monthlygoals` to edit your goals!
    """
    day_start = ctx.alion.day_start
    period_start = day_start - timedelta(days=31*4)

    history = ctx.client.data.session_history.select_where(
        guildid=ctx.guild.id,
        userid=ctx.author.id,
        select_columns=(
            "start_time",
            "(start_time + duration * interval '1 second') AS end_time"
        ),
        _extra="ORDER BY start_time DESC"
    )
    timezone = ctx.alion.timezone
    sessions = [(row['start_time'].astimezone(timezone), row['end_time'].astimezone(timezone)) for row in history]
    if not sessions:
        return await ctx.error_reply(
            "No statistics to show, because you have never studied in this server before!"
        )

    # Streak statistics
    streak = 0
    current_streak = None
    max_streak = 0

    day_attended = True if 'sessions' in ctx.client.objects and ctx.alion.session else None
    date = day_start
    daydiff = timedelta(days=1)

    periods = sessions

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

    first_session_start = sessions[-1][0]
    sessions = [session for session in sessions if session[1] > period_start]
    page_1_task = asyncio.create_task(_get_monthly_goals(ctx))
    page_2_task = asyncio.create_task(MonthlyStatsCard.request(
        ctx.author.name,
        f"#{ctx.author.discriminator}",
        sessions,
        day_start.date(),
        current_streak or 0,
        max_streak or 0,
        first_session_start,
        skin=MonthlyStatsCard.skin_args_for(ctx)
    ))
    await asyncio.gather(page_1_task, page_2_task)
    page_1 = page_1_task.result()
    page_2 = page_2_task.result()
    await ctx.reply(
        files=[
            image_as_file(page_1, "monthly_stats_1.png"),
            image_as_file(page_2, "monthly_stats_2.png")
        ]
    )

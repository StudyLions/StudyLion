"""
Weekly and Monthly goal display and edit interface.
"""
from enum import Enum
import discord

from cmdClient.checks import in_guild
from cmdClient.lib import SafeCancellation

from utils.lib import parse_ranges

from .module import module
from .data import weekly_goals, weekly_tasks, monthly_goals, monthly_tasks


MAX_LENGTH = 200
MAX_TASKS = 10


class GoalType(Enum):
    WEEKLY = 0
    MONTHLY = 1


def index_range_parser(userstr, max):
    try:
        indexes = parse_ranges(userstr)
    except SafeCancellation:
        raise SafeCancellation(
            "Couldn't parse the provided task ids! "
            "Please list the task numbers or ranges separated by a comma, e.g. `0, 2-4`."
        ) from None

    return [index for index in indexes if index <= max]


@module.cmd(
    "weeklygoals",
    group="Statistics",
    desc="Set your weekly goals and view your progress!",
    aliases=('weeklygoal',),
    flags=('study=', 'tasks=')
)
@in_guild()
async def cmd_weeklygoals(ctx, flags):
    """
    Usage``:
        {prefix}weeklygoals [--study <hours>] [--tasks <number>]
        {prefix}weeklygoals add <task>
        {prefix}weeklygoals edit <taskid> <new task>
        {prefix}weeklygoals check <taskids>
        {prefix}weeklygoals remove <taskids>
    Description:
        Set yourself up to `10` goals for this week and keep yourself accountable!
        Use `add/edit/check/remove` to edit your goals, similarly to `{prefix}todo`.
        You can also add multiple tasks at once by writing them on multiple lines.

        You can also track your progress towards a number of hours studied with `--study`, \
            and aim for a number of tasks completed with `--tasks`.

        Run the command with no arguments or check your profile to see your progress!
    Examples``:
        {prefix}weeklygoals add Read chapters 1 to 10.
        {prefix}weeklygoals check 1
        {prefix}weeklygoals --study 48h --tasks 60
    """
    await goals_command(ctx, flags, GoalType.WEEKLY)


@module.cmd(
    "monthlygoals",
    group="Statistics",
    desc="Set your monthly goals and view your progress!",
    aliases=('monthlygoal',),
    flags=('study=', 'tasks=')
)
@in_guild()
async def cmd_monthlygoals(ctx, flags):
    """
    Usage``:
        {prefix}monthlygoals [--study <hours>] [--tasks <number>]
        {prefix}monthlygoals add <task>
        {prefix}monthlygoals edit <taskid> <new task>
        {prefix}monthlygoals check <taskids>
        {prefix}monthlygoals uncheck <taskids>
        {prefix}monthlygoals remove <taskids>
    Description:
        Set yourself up to `10` goals for this month and keep yourself accountable!
        Use `add/edit/check/remove` to edit your goals, similarly to `{prefix}todo`.
        You can also add multiple tasks at once by writing them on multiple lines.

        You can also track your progress towards a number of hours studied with `--study`, \
            and aim for a number of tasks completed with `--tasks`.

        Run the command with no arguments or check your profile to see your progress!
    Examples``:
        {prefix}monthlygoals add Read chapters 1 to 10.
        {prefix}monthlygoals check 1
        {prefix}monthlygoals --study 180h --tasks 60
    """
    await goals_command(ctx, flags, GoalType.MONTHLY)


async def goals_command(ctx, flags, goal_type):
    prefix = ctx.best_prefix
    if goal_type == GoalType.WEEKLY:
        name = 'week'
        goal_table = weekly_goals
        task_table = weekly_tasks
        rowkey = 'weekid'
        rowid = ctx.alion.week_timestamp

        tasklist = task_table.select_where(
            guildid=ctx.guild.id,
            userid=ctx.author.id,
            weekid=rowid,
            _extra="ORDER BY taskid ASC"
        )

        max_time = 7 * 16
    else:
        name = 'month'
        goal_table = monthly_goals
        task_table = monthly_tasks
        rowid = ctx.alion.month_timestamp
        rowkey = 'monthid'

        tasklist = task_table.select_where(
            guildid=ctx.guild.id,
            userid=ctx.author.id,
            monthid=rowid,
            _extra="ORDER BY taskid ASC"
        )

        max_time = 31 * 16

    # We ensured the `lion` existed with `ctx.alion` above
    # This also ensures a new tasklist can reference the period member goal key
    # TODO: Should creation copy the previous existing week?
    goal_row = goal_table.fetch_or_create((ctx.guild.id, ctx.author.id, rowid))

    if flags['study']:
        # Set study hour goal
        time = flags['study'].lower().strip('h ')
        if not time or not time.isdigit():
            return await ctx.error_reply(
                f"Please provide your {name}ly study goal in hours!\n"
                f"For example, `{prefix}{ctx.alias} --study 48h`"
            )
        hours = int(time)
        if hours > max_time:
            return await ctx.error_reply(
                "You can't set your goal this high! Please rest and keep a healthy lifestyle."
            )

        goal_row.study_goal = hours

    if flags['tasks']:
        # Set tasks completed goal
        count = flags['tasks']
        if not count or not count.isdigit():
            return await ctx.error_reply(
                f"Please provide the number of tasks you want to complete this {name}!\n"
                f"For example, `{prefix}{ctx.alias} --tasks 300`"
            )
        if int(count) > 2048:
            return await ctx.error_reply(
                "Your task goal is too high!"
            )
        goal_row.task_goal = int(count)

    if ctx.args:
        # If there are arguments, assume task/goal management
        # Extract the command if it exists, assume add operation if it doesn't
        splits = ctx.args.split(maxsplit=1)
        cmd = splits[0].lower().strip()
        args = splits[1].strip() if len(splits) > 1 else ''

        if cmd in ('check', 'done', 'complete'):
            if not args:
                # Show subcommand usage
                return await ctx.error_reply(
                    f"**Usage:**`{prefix}{ctx.alias} check <taskids>`\n"
                    f"**Example:**`{prefix}{ctx.alias} check 0, 2-4`"
                )
            if (indexes := index_range_parser(args, len(tasklist) - 1)):
                # Check the given indexes
                # If there are no valid indexes given, just do nothing and fall out to showing the goals
                task_table.update_where(
                    {'completed': True},
                    taskid=[tasklist[index]['taskid'] for index in indexes]
                )
        elif cmd in ('uncheck', 'undone', 'uncomplete'):
            if not args:
                # Show subcommand usage
                return await ctx.error_reply(
                    f"**Usage:**`{prefix}{ctx.alias} uncheck <taskids>`\n"
                    f"**Example:**`{prefix}{ctx.alias} uncheck 0, 2-4`"
                )
            if (indexes := index_range_parser(args, len(tasklist) - 1)):
                # Check the given indexes
                # If there are no valid indexes given, just do nothing and fall out to showing the goals
                task_table.update_where(
                    {'completed': False},
                    taskid=[tasklist[index]['taskid'] for index in indexes]
                )
        elif cmd in ('remove', 'delete', '-', 'rm'):
            if not args:
                # Show subcommand usage
                return await ctx.error_reply(
                    f"**Usage:**`{prefix}{ctx.alias} remove <taskids>`\n"
                    f"**Example:**`{prefix}{ctx.alias} remove 0, 2-4`"
                )
            if (indexes := index_range_parser(args, len(tasklist) - 1)):
                # Delete the given indexes
                # If there are no valid indexes given, just do nothing and fall out to showing the goals
                task_table.delete_where(
                    taskid=[tasklist[index]['taskid'] for index in indexes]
                )
        elif cmd == 'edit':
            if not args or len(splits := args.split(maxsplit=1)) < 2 or not splits[0].isdigit():
                # Show subcommand usage
                return await ctx.error_reply(
                    f"**Usage:**`{prefix}{ctx.alias} edit <taskid> <edited task>`\n"
                    f"**Example:**`{prefix}{ctx.alias} edit 2 Fix the scond task`"
                )
            index = int(splits[0])
            new_content = splits[1].strip()

            if index >= len(tasklist):
                return await ctx.error_reply(
                    f"Task `{index}` doesn't exist to edit!"
                )

            if len(new_content) > MAX_LENGTH:
                return await ctx.error_reply(
                    f"Please keep your goals under `{MAX_LENGTH}` characters long."
                )

            # Passed all checks, edit task
            task_table.update_where(
                {'content': new_content},
                taskid=tasklist[index]['taskid']
            )
        else:
            # Extract the tasks to add
            if cmd in ('add', '+'):
                if not args:
                    # Show subcommand usage
                    return await ctx.error_reply(
                        f"**Usage:**`{prefix}{ctx.alias} [add] <new task>`\n"
                        f"**Example:**`{prefix}{ctx.alias} add Read the Studylion help pages.`"
                    )
            else:
                args = ctx.args
            tasks = args.splitlines()

            # Check count
            if len(tasklist) + len(tasks) > MAX_TASKS:
                return await ctx.error_reply(
                    f"You can have at most **{MAX_TASKS}** {name}ly goals!"
                )

            # Check length
            if any(len(task) > MAX_LENGTH for task in tasks):
                return await ctx.error_reply(
                    f"Please keep your goals under `{MAX_LENGTH}` characters long."
                )

            # We passed the checks, add the tasks
            to_insert = [
                (ctx.guild.id, ctx.author.id, rowid, task)
                for task in tasks
            ]
            task_table.insert_many(
                *to_insert,
                insert_keys=('guildid', 'userid', rowkey, 'content')
            )
    elif not any((goal_row.study_goal, goal_row.task_goal, tasklist)):
        # The user hasn't set any goals for this time period
        # Prompt them with information about how to set a goal
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=f"**You haven't set any goals for this {name} yet! Try the following:**\n"
        )
        embed.add_field(
            name="Aim for a number of study hours with",
            value=f"`{prefix}{ctx.alias} --study 48h`"
        )
        embed.add_field(
            name="Aim for a number of tasks completed with",
            value=f"`{prefix}{ctx.alias} --tasks 300`",
            inline=False
        )
        embed.add_field(
            name=f"Set up to 10 custom goals for the {name}!",
            value=(
                f"`{prefix}{ctx.alias} add Write a 200 page thesis.`\n"
                f"`{prefix}{ctx.alias} edit 1 Write 2 pages of the 200 page thesis.`\n"
                f"`{prefix}{ctx.alias} done 0, 1, 3-4`\n"
                f"`{prefix}{ctx.alias} delete 2-4`"
            ),
            inline=False
        )
        return await ctx.reply(embed=embed)

    # Show the goals
    if goal_type == GoalType.WEEKLY:
        await display_weekly_goals_for(ctx)
    else:
        await display_monthly_goals_for(ctx)


async def display_weekly_goals_for(ctx):
    """
    Display the user's weekly goal summary and progress towards them
    TODO: Currently a stub, since the system is overidden by the GUI plugin
    """
    # Collect data
    lion = ctx.alion
    rowid = lion.week_timestamp
    goals = weekly_goals.fetch_or_create((ctx.guild.id, ctx.author.id, rowid))
    tasklist = weekly_tasks.select_where(
        guildid=ctx.guild.id,
        userid=ctx.author.id,
        weekid=rowid
    )
    ...


async def display_monthly_goals_for(ctx):
    ...

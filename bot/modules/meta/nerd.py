import datetime
import asyncio
import discord
import psutil
import sys
import gc

from data import NOTNULL
from data.queries import select_where
from utils.lib import prop_tabulate, utc_now

from LionContext import LionContext as Context

from .module import module


process = psutil.Process()
process.cpu_percent()


@module.cmd(
    "nerd",
    group="Meta",
    desc="Information and statistics about me!"
)
async def cmd_nerd(ctx: Context):
    """
    Usage``:
        {prefix}nerd
    Description:
        View nerdy information and statistics about me!
    """
    # Create embed
    embed = discord.Embed(
        colour=discord.Colour.orange(),
        title="Nerd Panel",
        description=(
            "Hi! I'm [StudyLion]({studylion}), a study management bot owned by "
            "[Ari Horesh]({ari}) and developed by [Conatum#5317]({cona}), with [contributors]({github})."
        ).format(
            studylion="http://studylions.com/",
            ari="https://arihoresh.com/",
            cona="https://github.com/Intery",
            github="https://github.com/StudyLions/StudyLion"
        )
    )

    # ----- Study stats -----
    # Current studying statistics
    current_students, current_channels, current_guilds= (
        ctx.client.data.current_sessions.select_one_where(
            select_columns=(
                "COUNT(*) AS studying_count",
                "COUNT(DISTINCT(channelid)) AS channel_count",
                "COUNT(DISTINCT(guildid)) AS guild_count"
            )
        )
    )

    # Past studying statistics
    past_sessions, past_students, past_duration, past_guilds = ctx.client.data.session_history.select_one_where(
        select_columns=(
            "COUNT(*) AS session_count",
            "COUNT(DISTINCT(userid)) AS user_count",
            "SUM(duration) / 3600 AS total_hours",
            "COUNT(DISTINCT(guildid)) AS guild_count"
        )
    )

    # Tasklist statistics
    tasks = ctx.client.data.tasklist.select_one_where(
        select_columns=(
            'COUNT(*)'
        )
    )[0]

    tasks_completed = ctx.client.data.tasklist.select_one_where(
        completed_at=NOTNULL,
        select_columns=(
            'COUNT(*)'
        )
    )[0]

    # Timers
    timer_count, timer_guilds = ctx.client.data.timers.select_one_where(
        select_columns=("COUNT(*)", "COUNT(DISTINCT(guildid))")
    )

    study_fields = {
        "Currently": f"`{current_students}` people working in `{current_channels}` rooms of `{current_guilds}` guilds",
        "Recorded": f"`{past_duration}` hours from `{past_students}` people across `{past_sessions}` sessions",
        "Tasks": f"`{tasks_completed}` out of `{tasks}` tasks completed",
        "Timers": f"`{timer_count}` timers running in `{timer_guilds}` communities"
    }
    study_table = prop_tabulate(*zip(*study_fields.items()))

    # ----- Shard statistics -----
    shard_number = ctx.client.shard_id
    shard_count = ctx.client.shard_count
    guilds = len(ctx.client.guilds)
    member_count = sum(guild.member_count for guild in ctx.client.guilds)
    commands = len(ctx.client.cmds)
    aliases = len(ctx.client.cmd_names)
    dpy_version = discord.__version__
    py_version = sys.version.split()[0]
    data_version, data_time, _ = select_where(
        "VersionHistory",
        _extra="ORDER BY time DESC LIMIT 1"
    )[0]
    data_timestamp = int(data_time.replace(tzinfo=datetime.timezone.utc).timestamp())

    shard_fields = {
        "Shard": f"`{shard_number}` of `{shard_count}`",
        "Guilds": f"`{guilds}` servers with `{member_count}` members (on this shard)",
        "Commands": f"`{commands}` commands with `{aliases}` keywords",
        "Version": f"`v{data_version}`, last updated <t:{data_timestamp}:F>",
        "Py version": f"`{py_version}` running discord.py `{dpy_version}`"
    }
    shard_table = prop_tabulate(*zip(*shard_fields.items()))


    # ----- Execution statistics -----
    running_commands = len(ctx.client.active_contexts)
    tasks = len(asyncio.all_tasks())
    objects = len(gc.get_objects())
    cpu_percent = process.cpu_percent()
    mem_percent = int(process.memory_percent())
    uptime = int(utc_now().timestamp() - process.create_time())

    execution_fields = {
        "Running": f"`{running_commands}` commands",
        "Waiting for": f"`{tasks}` tasks to complete",
        "Objects": f"`{objects}` loaded in memory",
        "Usage": f"`{cpu_percent}%` CPU, `{mem_percent}%` MEM",
        "Uptime": f"`{uptime // (24 * 3600)}` days, `{uptime // 3600 % 24:02}:{uptime // 60 % 60:02}:{uptime % 60:02}`"
    }
    execution_table = prop_tabulate(*zip(*execution_fields.items()))

    # ----- Combine and output -----
    embed.add_field(name="Study Stats", value=study_table, inline=False)
    embed.add_field(name=f"Shard Info", value=shard_table, inline=False)
    embed.add_field(name=f"Process Stats", value=execution_table, inline=False)

    await ctx.reply(embed=embed)

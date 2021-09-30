from io import StringIO

import discord
from wards import guild_admin
from data import tables
from core import Lion

from .module import module


@module.cmd("studyreset",
            desc="Perform a reset of the server's study statistics.",
            group="Guild Admin")
@guild_admin()
async def cmd_statreset(ctx):
    """
    Usage``:
        {prefix}studyreset
    Description:
        Perform a complete reset of the server's study statistics.
        That is, deletes the tracked time of all members and removes their study badges.

        This may be used to set "seasons" of study.

        Before the reset, I will send a csv file with the current member statistics.

        **This is not reversible.**
    """
    if not await ctx.ask("Are you sure you want to reset the study time and badges for all members? "
                         "**THIS IS NOT REVERSIBLE!**"):
        return
    # Build the data csv
    rows = tables.lions.select_where(
        select_columns=('userid', 'tracked_time', 'coins', 'workout_count', 'b.roleid AS badge_roleid'),
        _extra=(
            "LEFT JOIN study_badges b ON last_study_badgeid = b.badgeid "
            "WHERE members.guildid={}"
        ).format(ctx.guild.id)
    )
    header = "userid, tracked_time, coins, workouts, rank_roleid\n"
    csv_rows = [
        ','.join(str(data) for data in row)
        for row in rows
    ]

    with StringIO() as stats_file:
        stats_file.write(header)
        stats_file.write('\n'.join(csv_rows))
        stats_file.seek(0)

        out_file = discord.File(stats_file, filename="guild_{}_member_statistics.csv".format(ctx.guild.id))
        await ctx.reply(file=out_file)

    # Reset the statistics
    tables.lions.update_where(
        {'tracked_time': 0},
        guildid=ctx.guild.id
    )

    Lion.sync()

    await ctx.embed_reply(
        "The member study times have been reset!\n"
        "(It may take a while for the studybadges to update.)"
    )

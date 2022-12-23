import importlib
from datetime import datetime, timedelta

from data.conditions import GEQ

from ..module import module

from .. import drawing
from ..utils import get_avatar, image_as_file


@module.cmd(
    'tasktest'
)
async def cmd_tasktest(ctx):
    importlib.reload(drawing.weekly)
    WeeklyStatsPage = drawing.weekly.WeeklyStatsPage

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

    page = WeeklyStatsPage(
        ctx.author.name,
        f"#{ctx.author.discriminator}",
        sessions,
        day_start
    )
    image = page.draw()

    await ctx.reply(file=image_as_file(image, 'weekly_stats.png'))

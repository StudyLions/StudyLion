from typing import Optional
from datetime import timedelta

from data import ORDER
from meta import LionBot
from gui.cards import WeeklyStatsCard
from gui.base import CardMode

from ..data import StatsData


async def get_weekly_card(bot: LionBot, userid: int, guildid: int, offset: int, mode: CardMode) -> WeeklyStatsCard:
    data: StatsData = bot.get_cog('StatsCog').data

    if guildid:
        lion = await bot.core.lions.fetch_member(guildid, userid)
        user = await lion.fetch_member()
    else:
        lion = await bot.core.lions.fetch_user(userid)
        user = await bot.fetch_user(userid)
    today = lion.today
    week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=offset)
    days = [week_start + timedelta(i) for i in range(-7, 7 if offset else (today.weekday() + 1))]

    # TODO: Select statistics model based on mode
    model = data.VoiceSessionStats

    # Get user session rows
    query = model.table.select_where()
    if guildid:
        query = query.where(userid=userid, guildid=guildid).order_by('start_time', ORDER.ASC)
    else:
        query = query.where(userid=userid)
    sessions = await query

    # Extract quantities per-day
    day_stats = await model.study_times_between(guildid or None, userid, *days)
    for i in range(14 - len(day_stats)):
        day_stats.append(0)

    # Get member profile
    if user:
        username = (user.display_name, user.discriminator)
    else:
        username = (lion.data.display_name, '#????')

    card = WeeklyStatsCard(
        user=username,
        timezone=str(lion.timezone),
        now=lion.now.timestamp(),
        week=week_start.timestamp(),
        daily=tuple(map(lambda n: n/3600, day_stats)),
        sessions=[
            (int(session['start_time'].timestamp()), int(session['end_time'].timestamp()))
            for session in sessions
        ],
        skin={'mode': mode}
    )
    return card

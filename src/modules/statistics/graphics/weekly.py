from typing import Optional
from datetime import timedelta

from data import ORDER
from meta import LionBot
from gui.cards import WeeklyStatsCard
from gui.base import CardMode
from tracking.text.data import TextTrackerData

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
    days = [week_start + timedelta(i) for i in range(-7, 8 if offset else (today.weekday() + 2))]

    # TODO: Select statistics model based on mode
    if mode is CardMode.VOICE:
        model = data.VoiceSessionStats
        day_stats = await model.study_times_between(guildid or None, userid, *days)
        day_stats = list(map(lambda n: n // 3600, day_stats))
    elif mode is CardMode.TEXT:
        model = TextTrackerData.TextSessions
        if guildid:
            day_stats = await model.member_messages_between(guildid, userid, *days)
        else:
            day_stats = await model.user_messages_between(userid, *days)
    else:
        # TODO: ANKI
        model = data.VoiceSessionStats
        day_stats = await model.study_times_between(guildid or None, userid, *days)
        day_stats = list(map(lambda n: n // 3600, day_stats))

    # Get user session rows
    query = model.table.select_where(model.start_time >= days[0])
    if guildid:
        query = query.where(userid=userid, guildid=guildid).order_by('start_time', ORDER.ASC)
    else:
        query = query.where(userid=userid)
    sessions = await query

    # Extract quantities per-day
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
        daily=tuple(map(int, day_stats)),
        sessions=[
            (int(session['start_time'].timestamp()), int(session['start_time'].timestamp() + int(session['duration'])))
            for session in sessions
        ],
        skin={'mode': mode}
    )
    return card

from typing import Optional
from datetime import datetime, timedelta

import discord

from meta import LionBot
from gui.cards import StatsCard

from ..data import StatsData


async def get_stats_card(bot: LionBot, userid: int, guildid: int):
    data: StatsData = bot.get_cog('StatsCog').data

    # TODO: Workouts
    # TODO: Leaderboard rankings
    guildid = guildid or 0

    lion = await bot.core.lions.fetch(guildid, userid)

    # Calculate the period timestamps, i.e. start time for each summary period
    # TODO: Don't do the alltime one like this, not efficient anymore
    # TODO: Unless we rewrite study_time_since again?
    today = lion.today
    month_start = today.replace(day=1)
    period_timestamps = (
        datetime(1970, 1, 1),
        month_start,
        today - timedelta(days=today.weekday()),
        today
    )

    # Extract the study times for each period
    study_times = await data.VoiceSessionStats.study_times_since(guildid, userid, *period_timestamps)
    print("Study times", study_times)

    # Calculate streak data by requesting times per day
    # First calculate starting timestamps for each day
    days = list(range(0, today.day + 2))
    day_timestamps = [month_start + timedelta(days=day - 1) for day in days]
    study_times = await data.VoiceSessionStats.study_times_between(guildid, userid, *day_timestamps)
    print("Study times", study_times)

    # Then extract streak tuples
    streaks = []
    streak_start = None
    for day, stime in zip(days, study_times):
        stime = stime or 0
        if stime > 0 and streak_start is None:
            streak_start = day
        elif stime == 0 and streak_start is not None:
            streaks.append((streak_start, day-1))
            streak_start = None
    if streak_start is not None:
        streaks.append((streak_start, today.day))

    card = StatsCard(
        (0, 0),
        list(reversed(study_times)),
        100,
        streaks,
    )
    return card

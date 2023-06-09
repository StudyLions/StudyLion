from typing import Optional
from datetime import datetime, timedelta

import discord

from meta import LionBot
from gui.cards import StatsCard
from gui.base import CardMode

from ..data import StatsData


async def get_stats_card(bot: LionBot, userid: int, guildid: int, mode: CardMode):
    data: StatsData = bot.get_cog('StatsCog').data

    # TODO: Workouts
    # TODO: Leaderboard rankings for this season or all time
    guildid = guildid or 0

    lion = await bot.core.lions.fetch_member(guildid, userid)

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
    if mode in (CardMode.STUDY, CardMode.VOICE):
        model = data.VoiceSessionStats
        refkey = (guildid, userid)
        ref_since = model.study_times_since
        ref_between = model.study_times_between
    elif mode is CardMode.TEXT:
        if guildid:
            model = data.MemberExp
            refkey = (guildid, userid)
        else:
            model = data.UserExp
            refkey = (userid,)
        ref_since = model.xp_since
        ref_between = model.xp_between
    else:
        # TODO ANKI
        model = data.VoiceSessionStats
        refkey = (guildid, userid)
        ref_since = model.study_times_since
        ref_between = model.study_times_between

    study_times = await ref_since(*refkey, *period_timestamps)
    print("Period study times: ", study_times)

    # Get leaderboard position
    # TODO: Efficiency
    if guildid:
        lguild = await bot.core.lions.fetch_guild(guildid)
        season_start = lguild.data.season_start
        if season_start is not None:
            data = await model.leaderboard_since(guildid, season_start)
        else:
            data = await model.leaderboard_all(guildid)
        position = next((i + 1 for i, (uid, _) in enumerate(data) if uid == userid), None)
    else:
        position = None

    # Calculate streak data by requesting times per day
    # First calculate starting timestamps for each day
    days = list(range(0, today.day + 2))
    day_timestamps = [month_start + timedelta(days=day - 1) for day in days]
    study_times_month = await ref_between(*refkey, *day_timestamps)

    # Then extract streak tuples
    streaks = []
    streak_start = None
    for day, stime in zip(days, study_times_month):
        stime = stime or 0
        if stime > 0 and streak_start is None:
            streak_start = day
        elif stime == 0 and streak_start is not None:
            streaks.append((streak_start, day-1))
            streak_start = None
    if streak_start is not None:
        streaks.append((streak_start, today.day))

    card = StatsCard(
        (position, 0),
        list(reversed(study_times)),
        100,
        streaks,
        skin={'mode': mode}
    )
    return card

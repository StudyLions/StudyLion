from typing import Optional
from datetime import timedelta
import calendar

from data import ORDER
from meta import LionBot
from gui.cards import MonthlyStatsCard
from gui.base import CardMode

from ..data import StatsData
from ..lib import apply_month_offset


async def get_monthly_card(bot: LionBot, userid: int, guildid: int, offset: int, mode: CardMode) -> MonthlyStatsCard:
    data: StatsData = bot.get_cog('StatsCog').data

    lion = await bot.core.lions.fetch_member(guildid, userid)
    today = lion.today
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    target = apply_month_offset(month_start, offset)
    target_end = (target + timedelta(days=40)).replace(day=1, hour=0, minute=0) - timedelta(days=1)

    months = [target]
    for i in range(0, 3):
        months.append((months[-1] - timedelta(days=1)).replace(day=1))
    months.reverse()

    monthly = [
        [0]*(calendar.monthrange(month.year, month.month)[1]) for month in months
    ]

    # TODO: Select model based on card mode
    model = data.VoiceSessionStats

    # Get first session
    query = model.table.select_where().order_by('start_time', ORDER.ASC).limit(1)
    if guildid:
        query = query.where(userid=userid, guildid=guildid)
    else:
        query = query.where(userid=userid)
    results = await query
    first_session = results[0]['start_time'] if results else None
    if not first_session:
        current_streak = 0
        longest_streak = 0
    else:
        first_day = first_session.replace(hour=0, minute=0, second=0, microsecond=0)
        first_month = first_day.replace(day=1)

        # Build list of day starts up to now, or end of requested month
        requests = []
        end_of_req = target_end if offset else today
        day = first_day
        while day <= end_of_req:
            day = day + timedelta(days=1)
            requests.append(day)

        # Request times between requested days
        day_stats = await model.study_times_between(guildid or None, userid, *requests)

        # Compute current streak and longest streak
        current_streak = 0
        longest_streak = 0
        for day in day_stats:
            if day > 0:
                current_streak += 1
                longest_streak = max(current_streak, longest_streak)
            else:
                current_streak = 0

        # Populate monthly
        offsets = {(month.year, month.month): i for i, month in enumerate(months)}
        for day, stat in zip(reversed(requests[:-1]), reversed(day_stats)):
            if day < months[0]:
                break
            i = offsets[(day.year, day.month)]
            monthly[i][day.day - 1] = stat / 3600

    # Get member profile
    if member := await lion.fetch_member():
        username = (member.display_name, member.discriminator)
    else:
        username = (lion.data.display_name, '#????')

    # Request card
    card = MonthlyStatsCard(
        user=username,
        timezone=str(lion.timezone),
        now=lion.now.timestamp(),
        month=int(target.timestamp()),
        monthly=monthly,
        current_streak=current_streak,
        longest_streak=longest_streak,
        skin={'mode': mode}
    )
    return card

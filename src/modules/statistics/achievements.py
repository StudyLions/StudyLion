from typing import Optional, TYPE_CHECKING
import asyncio
import datetime as dt

import pytz
import discord

from data import ORDER, NULL
from meta import conf, LionBot
from meta.logger import log_wrap
from babel.translator import LazyStr

from . import babel, logger

if TYPE_CHECKING:
    from .cog import StatsCog

_p = babel._p


emojis = [
    (conf.emojis.active_achievement_1, conf.emojis.inactive_achievement_1),
    (conf.emojis.active_achievement_2, conf.emojis.inactive_achievement_2),
    (conf.emojis.active_achievement_3, conf.emojis.inactive_achievement_3),
    (conf.emojis.active_achievement_4, conf.emojis.inactive_achievement_4),
    (conf.emojis.active_achievement_5, conf.emojis.inactive_achievement_5),
    (conf.emojis.active_achievement_6, conf.emojis.inactive_achievement_6),
    (conf.emojis.active_achievement_7, conf.emojis.inactive_achievement_7),
    (conf.emojis.active_achievement_8, conf.emojis.inactive_achievement_8),
]

def progress_bar(value, minimum, maximum, width=10) -> str:
    """
    Build a text progress bar representing `value` between `minimum` and `maximum`.
    """
    emojis = conf.emojis

    proportion = (value - minimum) / (maximum - minimum)
    sections = min(max(int(proportion * width), 0), width)

    bar = []
    # Starting segment
    bar.append(str(emojis.progress_left_empty) if sections == 0 else str(emojis.progress_left_full))

    # Full segments up to transition or end
    if sections >= 2:
        bar.append(str(emojis.progress_middle_full) * (sections - 2))

    # Transition, if required
    if 1 < sections < width:
        bar.append(str(emojis.progress_middle_transition))

    # Empty sections up to end
    if sections < width:
        bar.append(str(emojis.progress_middle_empty) * (width - max(sections, 1) - 1))

    # End section
    bar.append(str(emojis.progress_right_empty) if sections < width else str(emojis.progress_right_full))

    # Join all the sections together and return
    return ''.join(bar)


class Achievement:
    """
    ABC for a member achievement.
    """
    # Achievement title
    _name: LazyStr

    # Text describing achievement
    _subtext: LazyStr

    # Congratulations text
    _congrats: LazyStr = _p(
        'achievement|congrats',
        "Congratulations! You have completed this challenge."
    )

    # Index used for visual display of achievement
    emoji_index: int

    # Achievement threshold
    threshold: int

    def __init__(self, bot: LionBot, guildid: int, userid: int):
        self.bot = bot
        self.guildid = guildid
        self.userid = userid

        self.value: Optional[int] = None

    @property
    def achieved(self) -> bool:
        if self.value is None:
            raise ValueError("Cannot get achievement status with no value.")
        return self.value >= self.threshold

    @property
    def progress_text(self) -> str:
        if self.value is None:
            raise ValueError("Cannot get progress text with no value.")
        return f"{int(self.value)}/{int(self.threshold)}"

    @property
    def name(self) -> str:
        return self.bot.translator.t(self._name)

    @property
    def subtext(self) -> str:
        return self.bot.translator.t(self._subtext)

    @property
    def congrats(self) -> str:
        return self.bot.translator.t(self._congrats)

    @property
    def emoji(self):
        return emojis[self.emoji_index][int(not self.achieved)]

    @classmethod
    async def fetch(cls, bot: LionBot, guildid: int, userid: int):
        self = cls(bot, guildid, userid)
        await self.update()
        return self

    def make_field(self):
        name = f"{self.emoji} {self.name} ({self.progress_text})"
        value = "**0** {bar} **{threshold}**\n*{subtext}*".format(
            subtext=self.congrats if self.achieved else self.subtext,
            bar=progress_bar(self.value, 0, self.threshold),
            threshold=self.threshold
        )
        return (name, value)

    async def update(self):
        self.value = await self._calculate()

    async def _calculate(self) -> int:
        raise NotImplementedError


class Workout(Achievement):
    _name = _p(
        'achievement:workout|name',
        "It's about Power"
    )
    _subtext = _p(
        'achievement:workout|subtext',
        "Workout 50 times"
    )

    threshold = 50
    emoji_index = 3

    @log_wrap(action='Calc Workout')
    async def _calculate(self):
        """
        Count the number of completed workout sessions this user has.
        """
        record = await self.bot.core.data.workouts.select_one_where(
            guildid=self.guildid, userid=self.userid
        ).select(total='COUNT(*)')
        return int(record['total'] or 0)


class VoiceHours(Achievement):
    _name = _p(
        'achievement:voicehours|name',
        "Dream Big"
    )
    _subtext = _p(
        'achievement:voicehours|subtext',
        "Study a total of 1000 hours"
    )

    threshold = 1000
    emoji_index = 0

    @log_wrap(action='Calc VoiceHours')
    async def _calculate(self):
        """
        Returns the total number of hours this member has spent in voice.
        """
        stats: 'StatsCog' = self.bot.get_cog('StatsCog')
        records = await stats.data.VoiceSessionStats.table.select_where(
            guildid=self.guildid, userid=self.userid
        ).select(total='SUM(duration) / 3600').with_no_adapter()
        hours = records[0]['total'] if records else 0
        return int(hours or 0)


class VoiceStreak(Achievement):
    _name = _p(
        'achievement:voicestreak|name',
        "Consistency is Key"
    )
    _subtext = _p(
        'achievement:voicestreak|subtext',
        "Reach a 100-day voice streak"
    )

    threshold = 100
    emoji_index = 1

    @log_wrap(action='Calc VoiceStreak')
    async def _calculate(self):
        stats: 'StatsCog' = self.bot.get_cog('StatsCog')

        # TODO: make this more efficient by calc in database..
        history = await stats.data.VoiceSessionStats.table.select_where(
            guildid=self.guildid, userid=self.userid
        ).select(
            'start_time', 'end_time'
        ).order_by('start_time', ORDER.DESC).with_no_adapter()

        lion = await self.bot.core.lions.fetch_member(self.guildid, self.userid)

        # Streak statistics
        streak = 0
        max_streak = 0
        current_streak = None

        day_attended = None
        date = lion.today
        daydiff = dt.timedelta(days=1)

        periods = [(row['start_time'], row['end_time']) for row in history]

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

            if current_streak is None:
                current_streak = streak
            max_streak = max(max_streak, streak)
            streak = 0

        # Handle loop exit state, i.e. the last streak
        if day_attended:
            streak += 1
        max_streak = max(max_streak, streak)
        if current_streak is None:
            current_streak = streak

        return max_streak if max_streak >= self.threshold else current_streak

class Voting(Achievement):
    _name = _p(
        'achievement:voting|name',
        "We're a Team"
    )
    _subtext = _p(
        'achievement:voting|subtext',
        "Vote 100 times on top.gg"
    )

    threshold = 100
    emoji_index = 6

    @log_wrap(action='Calc Voting')
    async def _calculate(self):
        record = await self.bot.core.data.topgg.select_one_where(
            userid=self.userid
        ).select(total='COUNT(*)')
        return int(record['total'] or 0)


class VoiceDays(Achievement):
    _name = _p(
        'achievement:days|name',
        "Aim For The Moon"
    )
    _subtext = _p(
        'achievement:days|subtext',
        "Join Voice on 90 different days"
    )

    threshold = 90
    emoji_index = 2

    @log_wrap(action='Calc VoiceDays')
    async def _calculate(self):
        stats: 'StatsCog' = self.bot.get_cog('StatsCog')

        lion = await self.bot.core.lions.fetch_member(self.guildid, self.userid)
        offset = int(lion.today.utcoffset().total_seconds())

        records = await stats.data.VoiceSessionStats.table.select_where(
            guildid=self.guildid, userid=self.userid
        ).select(
            total="COUNT(DISTINCT(date_trunc('day', (start_time AT TIME ZONE 'utc') + interval '{} seconds')))".format(offset)
        ).with_no_adapter()
        days = records[0]['total'] if records else 0
        return int(days or 0)


class TasksComplete(Achievement):
    _name = _p(
        'achievement:tasks|name',
        "One Step at a Time"
    )
    _subtext = _p(
        'achievement:tasks|subtext',
        "Complete 1000 tasks"
    )

    threshold = 1000
    emoji_index = 7

    @log_wrap(action='Calc TasksComplete')
    async def _calculate(self):
        cog = self.bot.get_cog('TasklistCog')
        if cog is None:
            raise ValueError("Cannot calc TasksComplete without Tasklist Cog")

        records = await cog.data.Task.table.select_where(
            cog.data.Task.completed_at != NULL,
            userid=self.userid,
        ).select(
            total="COUNT(*)"
        ).with_no_adapter()

        completed = records[0]['total'] if records else 0
        return int(completed or 0)


class ScheduledSessions(Achievement):
    _name = _p(
        'achievement:schedule|name',
        "Be Accountable"
    )
    _subtext = _p(
        'achievement:schedule|subtext',
        "Attend 500 Scheduled Sessions"
    )

    threshold = 500
    emoji_index = 4

    @log_wrap(action='Calc ScheduledSessions')
    async def _calculate(self):
        cog = self.bot.get_cog('ScheduleCog')
        if not cog:
            raise ValueError("Cannot calc scheduled sessions without ScheduleCog.")

        model = cog.data.ScheduleSessionMember
        records = await model.table.select_where(
            userid=self.userid, guildid=self.guildid, attended=True
        ).select(
            total='COUNT(*)'
        ).with_no_adapter()

        return int((records[0]['total'] or 0) if records else 0)


class MonthlyHours(Achievement):
    _name = _p(
        'achievement:monthlyhours|name',
        "The 30 Days Challenge"
    )
    _subtext = _p(
        'achievement:monthlyhours|subtext',
        "Be active for 100 hours in a month"
    )

    threshold = 100
    emoji_index = 5

    @log_wrap(action='Calc MonthlyHours')
    async def _calculate(self):
        stats: 'StatsCog' = self.bot.get_cog('StatsCog')

        lion = await self.bot.core.lions.fetch_member(self.guildid, self.userid)

        records = await stats.data.VoiceSessionStats.table.select_where(
            userid=self.userid,
            guildid=self.guildid,
        ).select(
            _first='MIN(start_time)'
        ).with_no_adapter()
        first_session = records[0]['_first'] if records else None
        if not first_session:
            return 0

        # Build the list of month start timestamps
        month_start = lion.month_start
        months = [month_start.astimezone(pytz.utc)]

        while month_start >= first_session:
            month_start -= dt.timedelta(days=1)
            month_start = month_start.replace(day=1)
            months.append(month_start.astimezone(pytz.utc))

        # Query the study times
        times = await stats.data.VoiceSessionStats.study_times_between(
            self.guildid, self.userid, *reversed(months), lion.now
        )
        max_time = max(times) // 3600
        return max_time if max_time >= self.threshold else times[-1] // 3600


achievements = [
    Workout,
    VoiceHours,
    VoiceStreak,
    Voting,
    VoiceDays,
    TasksComplete,
    ScheduledSessions,
    MonthlyHours,
]
achievements.sort(key=lambda cls: cls.emoji_index)


@log_wrap(action='Get Achievements')
async def get_achievements_for(bot: LionBot, guildid: int, userid: int):
    """
    Asynchronously fetch achievements for the given member.
    """
    member_achieved = [
        ach(bot, guildid, userid) for ach in achievements
    ]
    update_tasks = [
        asyncio.create_task(ach.update()) for ach in member_achieved
    ]
    await asyncio.gather(*update_tasks)
    return member_achieved

from typing import NamedTuple, Optional, Union
from datetime import timedelta

import pytz
import discord

from cmdClient.checks import in_guild
from LionContext import LionContext

from meta import client, conf
from core import Lion
from data.conditions import NOTNULL, LEQ
from utils.lib import utc_now

from .module import module


class AchievementLevel(NamedTuple):
    name: str
    threshold: Union[int, float]
    emoji: discord.PartialEmoji


class Achievement:
    """
    ABC for a member or user achievement.
    """
    # Name of the achievement
    name: str = None

    # List of levels for the achievement. Must always contain a 0 level!
    levels: list[AchievementLevel] = None

    def __init__(self, guildid: int, userid: int):
        self.guildid = guildid
        self.userid = userid

        # Current status of the achievement. None until calculated by `update`.
        self.value: int = None

        # Current level index in levels. None until calculated by `update`.
        self.level_id: int = None

    @staticmethod
    def progress_bar(value, minimum, maximum, width=15) -> str:
        """
        Build a text progress bar representing `value` between `minimum` and `maximum`.
        """
        emojis = conf.emojis

        proportion = (value - minimum) / (maximum - minimum)
        sections = max(int(proportion * width), 0)

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
        bar.append(str(emojis.progress_middle_empty) * (width - max(sections, 1)))

        # End section
        bar.append(str(emojis.progress_right_empty) if sections < width else str(emojis.progress_right_full))

        # Join all the sections together and return
        return ''.join(bar)

    @property
    def progress_text(self) -> str:
        """
        A brief textual description of the current progress.
        Intended to be overridden by achievement implementations.
        """
        if self.next_level:
            return f"{int(self.value)}/{self.next_level.threshold}"
        else:
            return f"{int(self.value)}, at the maximum level!"

    def progress_field(self) -> tuple[str, str]:
        """
        Builds the progress field for the achievement display.
        """
        # TODO: Not adjusted for levels
        # TODO: Add hint if progress is empty?
        name = f"{self.levels[1].emoji} {self.name} ({self.progress_text})"
        value = "**0** {progress_bar} **{threshold}**".format(
            progress_bar=self.progress_bar(self.value, self.levels[0].threshold, self.levels[1].threshold),
            threshold=self.levels[1].threshold
        )
        return (name, value)

    @classmethod
    async def fetch(cls, guildid: int, userid: int) -> 'Achievement':
        """
        Fetch an Achievement status for the given member.
        """
        return await cls(guildid, userid).update()

    @property
    def level(self) -> AchievementLevel:
        """
        The current `AchievementLevel` for this member achievement.
        """
        if self.level_id is None:
            raise ValueError("Cannot obtain level before first update!")
        return self.levels[self.level_id]

    @property
    def next_level(self) -> Optional[AchievementLevel]:
        """
        The next `AchievementLevel` for this member achievement,
        or `None` if it is at the maximum level.
        """
        if self.level_id is None:
            raise ValueError("Cannot obtain level before first update!")

        if self.level_id == len(self.levels) - 1:
            return None
        else:
            return self.levels[self.level_id + 1]

    async def update(self) -> 'Achievement':
        """
        Calculate and store the current member achievement status.
        Returns `self` for easy chaining.
        """
        # First fetch the value
        self.value = await self._calculate_value()

        # Then determine the current level
        # Using 0 as a fallback in case the value is negative
        self.level_id = next(
            (i for i, level in reversed(list(enumerate(self.levels))) if level.threshold <= self.value),
            0
        )

        # And return `self` for chaining
        return self

    async def _calculate_value(self) -> Union[int, float]:
        """
        Calculate the current `value` of the member achievement.
        Must be overridden by Achievement implementations.
        """
        raise NotImplementedError


class Workout(Achievement):
    name = "Workouts"

    levels = [
        AchievementLevel("Level 0", 0, None),
        AchievementLevel("Level 1", 50, conf.emojis.active_achievement_1),
    ]

    async def _calculate_value(self) -> int:
        """
        Returns the total number of workouts from this user.
        """
        return client.data.workout_sessions.select_one_where(
            userid=self.userid,
            select_columns="COUNT(*)"
        )[0]


class StudyHours(Achievement):
    name = "Study Hours"

    levels = [
        AchievementLevel("Level 0", 0, None),
        AchievementLevel("Level 1", 1000, conf.emojis.active_achievement_2),
    ]

    async def _calculate_value(self) -> float:
        """
        Returns the total number of hours this user has studied.
        """
        past_session_total = client.data.session_history.select_one_where(
            userid=self.userid,
            select_columns="SUM(duration)"
        )[0] or 0
        current_session_total = client.data.current_sessions.select_one_where(
            userid=self.userid,
            select_columns="SUM(EXTRACT(EPOCH FROM (NOW() - start_time)))"
        )[0] or 0

        session_total = past_session_total + current_session_total
        hours = session_total / 3600
        return hours


class StudyStreak(Achievement):
    name = "Study Streak"

    levels = [
        AchievementLevel("Level 0", 0, None),
        AchievementLevel("Level 1", 100, conf.emojis.active_achievement_3)
    ]

    async def _calculate_value(self) -> int:
        """
        Return the user's maximum global study streak.
        """
        lion = Lion.fetch(self.guildid, self.userid)
        history = client.data.session_history.select_where(
            userid=self.userid,
            select_columns=(
                "start_time",
                "(start_time + duration * interval '1 second') AS end_time"
            ),
            _extra="ORDER BY start_time DESC"
        )

        # Streak statistics
        streak = 0
        max_streak = 0

        day_attended = True if 'sessions' in client.objects and lion.session else None
        date = lion.day_start
        daydiff = timedelta(days=1)

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

            max_streak = max(max_streak, streak)
            streak = 0

        # Handle loop exit state, i.e. the last streak
        if day_attended:
            streak += 1
        max_streak = max(max_streak, streak)

        return max_streak


class Voting(Achievement):
    name = "Voting"

    levels = [
        AchievementLevel("Level 0", 0, None),
        AchievementLevel("Level 1", 100, conf.emojis.active_achievement_4)
    ]

    async def _calculate_value(self) -> int:
        """
        Returns the number of times the user has voted for the bot.
        """
        return client.data.topgg.select_one_where(
            userid=self.userid,
            select_columns="COUNT(*)"
        )[0]


class DaysStudying(Achievement):
    name = "Days Studied"

    levels = [
        AchievementLevel("Level 0", 0, None),
        AchievementLevel("Level 1", 90, conf.emojis.active_achievement_5)
    ]

    async def _calculate_value(self) -> int:
        """
        Returns the number of days the user has studied in total.
        """
        lion = Lion.fetch(self.guildid, self.userid)
        offset = int(lion.day_start.utcoffset().total_seconds())
        with client.data.session_history.conn as conn:
            cursor = conn.cursor()
            # TODO: Consider DST offset.
            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT(date_trunc('day', (time AT TIME ZONE 'utc') + interval '{} seconds')))
                FROM (
                    (SELECT start_time AS time FROM session_history WHERE userid=%s)
                    UNION
                    (SELECT (start_time + duration * interval '1 second') AS time FROM session_history WHERE userid=%s)
                ) AS times;
                """.format(offset),
                (self.userid, self.userid)
            )
            data = cursor.fetchone()
            return data[0]


class TasksComplete(Achievement):
    name = "Completed Tasks"

    levels = [
        AchievementLevel("Level 0", 0, None),
        AchievementLevel("Level 1", 1000, conf.emojis.active_achievement_6)
    ]

    async def _calculate_value(self) -> int:
        """
        Returns the number of tasks the user has completed.
        """
        return client.data.tasklist.select_one_where(
            userid=self.userid,
            completed_at=NOTNULL
        )[0]


class ScheduledSessions(Achievement):
    name = "Scheduled Sessions Attended"

    levels = [
        AchievementLevel("Level 0", 0, None),
        AchievementLevel("Level 1", 500, conf.emojis.active_achievement_7)
    ]

    async def _calculate_value(self) -> int:
        """
        Returns the number of scheduled sesions the user has attended.
        """
        return client.data.accountability_member_info.select_one_where(
            userid=self.userid,
            start_at=LEQ(utc_now()),
            select_columns="COUNT(*)",
            _extra="AND (duration > 0 OR last_joined_at IS NOT NULL)"
        )[0]


class MonthlyHours(Achievement):
    name = "Maximum Monthly Hours"

    levels = [
        AchievementLevel("Level 0", 0, None),
        AchievementLevel("Level 1", 100, conf.emojis.active_achievement_8)
    ]

    async def _calculate_value(self) -> float:
        """
        Returns the maximum number of hours the user has studied in a month.
        """
        # Get the first session so we know how far back to look
        first_session = client.data.session_history.select_one_where(
            userid=self.userid,
            select_columns="MIN(start_time)"
        )[0]

        # Get the user's timezone
        lion = Lion.fetch(self.guildid, self.userid)

        # If the first session doesn't exist, simulate an existing session (to avoid an extra lookup)
        first_session = first_session or lion.day_start - timedelta(days=1)

        # Build the list of month start timestamps
        month_start = lion.day_start.replace(day=1)
        months = [month_start.astimezone(pytz.utc)]

        while month_start >= first_session:
            month_start -= timedelta(days=1)
            month_start = month_start.replace(day=1)
            months.append(month_start.astimezone(pytz.utc))

        # Query the study times
        data = client.data.session_history.queries.study_times_since(
            self.guildid, self.userid, *months
        )
        cumulative_times = [row[0] for row in data]
        times = [nxt - crt for nxt, crt in zip(cumulative_times[1:], cumulative_times[0:])]
        max_time = max(cumulative_times[0], *times) if len(months) > 1 else cumulative_times[0]

        return max_time / 3600


# Define the displayed achivement order
achievements = [
    Workout,
    StudyHours,
    StudyStreak,
    Voting,
    DaysStudying,
    TasksComplete,
    ScheduledSessions,
    MonthlyHours
]


async def get_achievements_for(member):
    status = [
        await ach.fetch(member.guild.id, member.id)
        for ach in achievements
    ]
    return status


@module.cmd(
    name="achievements",
    desc="View your progress towards the achievements!",
    group="Statistics",
)
@in_guild()
async def cmd_achievements(ctx: LionContext):
    """
    Usage``:
        {prefix}achievements
    Description:
        View your progress towards attaining the achievement badges shown on your `profile`.
    """
    status = await get_achievements_for(ctx.author)

    embed = discord.Embed(
        title="Achievements",
        colour=discord.Colour.orange()
    )
    for achievement in status:
        name, value = achievement.progress_field()
        embed.add_field(
            name=name, value=value, inline=False
        )
    await ctx.reply(embed=embed)

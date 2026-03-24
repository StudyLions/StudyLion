# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-18
# Purpose: Premium pomodoro gamification - streak tracking,
#          Focus Power, milestone detection
# ============================================================
import logging
from datetime import date, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from meta import LionBot

logger = logging.getLogger(__name__)


MILESTONES = [50, 100, 250, 500, 1000, 2500, 5000]

FOCUS_POWER_MULTIPLIERS = {
    0: 1.0,
    1: 1.2,
    2: 1.2,
    3: 1.5,
    4: 1.5,
    5: 2.0,  # 5+ cycles unbroken
}

MILESTONE_MESSAGES = {
    50: "has completed **50 pomodoro cycles**! A dedicated learner! 📖",
    100: "has reached **100 pomodoro cycles**! A true scholar! 🎓",
    250: "has crushed **250 pomodoro cycles**! Unstoppable focus! 🔥",
    500: "has achieved **500 pomodoro cycles**! A focus legend! ⭐",
    1000: "has hit **1,000 pomodoro cycles**! Absolutely incredible! 🏆",
    2500: "has reached **2,500 pomodoro cycles**! A true master of concentration! 💎",
    5000: "has completed **5,000 pomodoro cycles**! The ultimate study champion! 👑",
}


def get_focus_power_multiplier(focus_power: int) -> float:
    max_level = max(FOCUS_POWER_MULTIPLIERS)
    level = min(focus_power, max_level)
    return FOCUS_POWER_MULTIPLIERS[level]


def _parse_date(value) -> Optional[date]:
    """Safely convert a stored date value to a date object."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _iso_week(d: date) -> tuple:
    """Return (year, week_number) using ISO calendar (Mon-Sun weeks)."""
    iso = d.isocalendar()
    return (iso[0], iso[1])


async def update_streak(bot: 'LionBot', userid: int, focus_minutes: int):
    """
    Called when a user completes a focus cycle in a premium guild.
    Updates daily/weekly streak counters and running totals.
    """
    data = bot.get_cog('TimerCog').data

    row = await data.PomodoroStreak.fetch(userid)
    if row is None:
        row = await data.PomodoroStreak.create(
            userid=userid,
            current_daily_streak=1,
            longest_daily_streak=1,
            current_weekly_streak=1,
            longest_weekly_streak=1,
            last_pomodoro_date=date.today(),
            total_cycles_completed=1,
            total_focus_minutes=focus_minutes,
            focus_power=0,
        )
        return row

    today = date.today()
    last_date = _parse_date(row.last_pomodoro_date)

    new_daily = row.current_daily_streak or 0
    new_longest_daily = row.longest_daily_streak or 0
    new_weekly = row.current_weekly_streak or 0
    new_longest_weekly = row.longest_weekly_streak or 0
    new_total_cycles = (row.total_cycles_completed or 0) + 1
    new_total_minutes = (row.total_focus_minutes or 0) + focus_minutes

    if last_date is not None:
        days_diff = (today - last_date).days

        if days_diff == 0:
            pass
        elif days_diff == 1:
            new_daily += 1
            if new_daily > new_longest_daily:
                new_longest_daily = new_daily
        else:
            new_daily = 1

        last_week = _iso_week(last_date)
        this_week = _iso_week(today)
        if last_week != this_week:
            week_diff = (this_week[0] * 52 + this_week[1]) - (last_week[0] * 52 + last_week[1])
            if week_diff == 1:
                new_weekly += 1
                if new_weekly > new_longest_weekly:
                    new_longest_weekly = new_weekly
            elif week_diff > 1:
                new_weekly = 1
    else:
        new_daily = 1
        new_longest_daily = max(new_longest_daily, 1)
        new_weekly = 1
        new_longest_weekly = max(new_longest_weekly, 1)

    await row.update(
        current_daily_streak=new_daily,
        longest_daily_streak=new_longest_daily,
        current_weekly_streak=new_weekly,
        longest_weekly_streak=new_longest_weekly,
        last_pomodoro_date=today,
        total_cycles_completed=new_total_cycles,
        total_focus_minutes=new_total_minutes,
    )
    return row


async def increment_focus_power(bot: 'LionBot', userid: int) -> int:
    """
    Increments the user's focus_power by 1 (called after each
    unbroken focus cycle). Returns the new focus_power value.
    """
    data = bot.get_cog('TimerCog').data

    row = await data.PomodoroStreak.fetch(userid)
    if row is None:
        row = await data.PomodoroStreak.create(
            userid=userid,
            focus_power=1,
        )
        return 1

    new_power = (row.focus_power or 0) + 1
    await row.update(focus_power=new_power)
    return new_power


async def reset_focus_power(bot: 'LionBot', userid: int):
    """
    Resets focus_power to 0 (called when a user leaves during
    a focus period, breaking their unbroken cycle chain).
    """
    data = bot.get_cog('TimerCog').data

    row = await data.PomodoroStreak.fetch(userid)
    if row is not None and (row.focus_power or 0) > 0:
        await row.update(focus_power=0)


async def check_milestones(
    bot: 'LionBot',
    userid: int,
    guildid: int,
    total_cycles: int,
) -> list:
    """
    Check if the user has crossed any milestone thresholds that
    haven't been recorded yet. Returns a list of (threshold, message)
    tuples for newly earned milestones.
    """
    data = bot.get_cog('TimerCog').data
    earned = []

    for threshold in MILESTONES:
        if total_cycles < threshold:
            break

        existing = await data.PomodoroMilestone.fetch_where(
            userid=userid,
            guildid=guildid,
            milestone_type='cycles',
            milestone_value=threshold,
        )
        if existing:
            continue

        await data.PomodoroMilestone.create(
            userid=userid,
            guildid=guildid,
            milestone_type='cycles',
            milestone_value=threshold,
        )
        earned.append((threshold, MILESTONE_MESSAGES[threshold]))

    return earned


async def announce_milestone(
    bot: 'LionBot',
    guildid: int,
    userid: int,
    threshold: int,
    message: str,
    channel_id: Optional[int] = None,
):
    """
    Sends a milestone announcement embed to the notification channel.
    Non-critical -- failures are logged but never raised.
    """
    import discord

    try:
        embed = discord.Embed(
            title="\U0001f3c5 Pomodoro Milestone!",
            description=f"<@{userid}> {message}",
            color=0xDDB21D,
        )

        channel = None
        if channel_id:
            channel = bot.get_channel(channel_id)

        if channel is None:
            data = bot.get_cog('TimerCog').data
            guild = bot.get_guild(guildid)
            if guild is None:
                logger.warning(
                    "Cannot announce milestone: guild %s not found on this shard",
                    guildid,
                )
                return

            timers = await data.Timer.fetch_where(guildid=guildid)
            for timer_row in timers:
                if timer_row.notification_channelid:
                    channel = bot.get_channel(timer_row.notification_channelid)
                    if channel is not None:
                        break

        if channel is None:
            logger.warning(
                "No notification channel found for milestone in guild %s",
                guildid,
            )
            return

        await channel.send(embed=embed)
    except Exception:
        logger.warning(
            "Failed to announce pomodoro milestone (guild=%s, user=%s, threshold=%s)",
            guildid, userid, threshold,
            exc_info=True,
        )


async def get_streak_data(bot: 'LionBot', userid: int) -> dict:
    """
    Fetches the streak data for display on the timer card or dashboard.
    Returns a dict of stats, defaulting to zeros if no row exists.
    """
    data = bot.get_cog('TimerCog').data

    row = await data.PomodoroStreak.fetch(userid)
    if row is None:
        return {
            'current_daily_streak': 0,
            'longest_daily_streak': 0,
            'current_weekly_streak': 0,
            'longest_weekly_streak': 0,
            'focus_power': 0,
            'total_cycles_completed': 0,
            'total_focus_minutes': 0,
        }

    return {
        'current_daily_streak': row.current_daily_streak or 0,
        'longest_daily_streak': row.longest_daily_streak or 0,
        'current_weekly_streak': row.current_weekly_streak or 0,
        'longest_weekly_streak': row.longest_weekly_streak or 0,
        'focus_power': row.focus_power or 0,
        'total_cycles_completed': row.total_cycles_completed or 0,
        'total_focus_minutes': row.total_focus_minutes or 0,
    }

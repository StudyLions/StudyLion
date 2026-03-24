# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-18
# Purpose: Weekly pomodoro DM digest - personal stats sent every Monday
# ============================================================
import logging
import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meta import LionBot

logger = logging.getLogger(__name__)

DIGEST_SEND_HOUR_UTC = 8   # Monday at 08:00 UTC
MAX_DMS_PER_SECOND = 30


class PomodoroDigest:
    """
    Background task that sends weekly study-report DMs to premium pomodoro users.
    Runs only on shard 0.
    """

    def __init__(self, bot: 'LionBot'):
        self.bot = bot
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if getattr(self.bot, 'shard_id', 0) != 0:
            logger.debug("Not shard 0 — skipping digest loop")
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("PomodoroDigest background loop started")

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("PomodoroDigest background loop stopped")

    async def _loop(self) -> None:
        """Sleep until Monday 08:00 UTC, send digests, repeat."""
        try:
            while True:
                now = datetime.utcnow()
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0 and now.hour >= DIGEST_SEND_HOUR_UTC:
                    days_until_monday = 7

                next_monday = (now + timedelta(days=days_until_monday)).replace(
                    hour=DIGEST_SEND_HOUR_UTC, minute=0, second=0, microsecond=0,
                )
                sleep_seconds = (next_monday - now).total_seconds()
                logger.debug("Digest loop sleeping %.0f seconds until %s", sleep_seconds, next_monday)
                await asyncio.sleep(sleep_seconds)

                await self._send_weekly_digests()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Fatal error in digest loop", exc_info=True)

    async def _send_weekly_digests(self) -> None:
        """Fetch eligible users and send each a weekly DM digest."""
        from .data import TimerData

        try:
            rows = await TimerData.PomodoroStreak.fetch_where(
                "total_cycles_completed > 0",
            )
        except Exception:
            logger.error("Failed to query pomodoro_streaks for digest", exc_info=True)
            return

        now = datetime.utcnow()
        week_start = now - timedelta(days=7)
        sent = 0

        for row in rows:
            try:
                userid = row.userid
                stats = await self._gather_weekly_stats(userid, week_start, now, row)
                if stats is None:
                    continue

                embed = await self._build_digest_embed(userid, stats)
                await self._send_dm(userid, embed)
                sent += 1

                if sent % MAX_DMS_PER_SECOND == 0:
                    await asyncio.sleep(1.0)
            except Exception:
                logger.warning(
                    "Failed to send digest to user %s", row.userid, exc_info=True,
                )

        logger.info("Weekly digest complete — sent %d DMs", sent)

    async def _gather_weekly_stats(
        self, userid: int, week_start: datetime, week_end: datetime, streak_row
    ) -> dict | None:
        """
        Build the stats dict for one user's past week.
        Returns None if the user had no activity.
        """
        try:
            from data import Registry
            pool = Registry.get_pool()

            query = """
                SELECT
                    COALESCE(SUM(
                        EXTRACT(EPOCH FROM (
                            LEAST(channel_left, $3) - GREATEST(channel_joined, $2)
                        )) / 60.0
                    ), 0) AS total_minutes,
                    COUNT(*) AS session_count,
                    MAX(channel_joined::date) AS best_day
                FROM tracked_sessions
                WHERE userid = $1
                  AND channel_joined >= $2
                  AND channel_joined < $3
            """
            record = await pool.fetchrow(query, userid, week_start, week_end)

            total_minutes = float(record['total_minutes']) if record else 0.0
            if total_minutes <= 0:
                return None

            focus_length = 25
            cycles_this_week = int(total_minutes / focus_length) if focus_length > 0 else 0

            prev_start = week_start - timedelta(days=7)
            prev_record = await pool.fetchrow(query, userid, prev_start, week_start)
            prev_minutes = float(prev_record['total_minutes']) if prev_record else 0.0

            if prev_minutes > 0:
                change_pct = ((total_minutes - prev_minutes) / prev_minutes) * 100
            else:
                change_pct = None

            return {
                'total_focus_hours': round(total_minutes / 60, 1),
                'cycles_this_week': cycles_this_week,
                'best_day': record['best_day'],
                'current_daily_streak': streak_row.current_daily_streak,
                'change_pct': change_pct,
            }
        except Exception:
            logger.warning("Failed to gather weekly stats for user %s", userid, exc_info=True)
            return None

    async def _build_digest_embed(self, userid: int, stats: dict):
        """Create the weekly-digest Discord embed."""
        import discord

        embed = discord.Embed(
            title="📊 Your Weekly Study Report",
            colour=discord.Colour(0xDDB21D),
        )

        embed.add_field(
            name="Focus Hours",
            value=f"**{stats['total_focus_hours']}** h",
            inline=True,
        )
        embed.add_field(
            name="Cycles",
            value=str(stats['cycles_this_week']),
            inline=True,
        )

        best_day = stats.get('best_day')
        if best_day is not None:
            embed.add_field(
                name="Best Day",
                value=best_day.strftime("%A"),
                inline=True,
            )

        embed.add_field(
            name="Current Streak",
            value=f"🔥 {stats['current_daily_streak']} day(s)",
            inline=True,
        )

        change = stats.get('change_pct')
        if change is not None:
            arrow = "📈" if change >= 0 else "📉"
            embed.add_field(
                name="vs Last Week",
                value=f"{arrow} {change:+.0f}%",
                inline=True,
            )
        else:
            embed.add_field(
                name="vs Last Week",
                value="🆕 First week tracked!",
                inline=True,
            )

        embed.set_footer(text='Opt out: /pomodoro digest off')

        user = self.bot.get_user(userid)
        if user and user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)

        return embed

    async def _send_dm(self, userid: int, embed) -> None:
        """Attempt to DM a user. Silently skip if DMs are disabled."""
        import discord

        try:
            user = self.bot.get_user(userid)
            if user is None:
                user = await self.bot.fetch_user(userid)
            await user.send(embed=embed)
        except discord.Forbidden:
            pass
        except discord.NotFound:
            logger.debug("User %s not found, skipping digest DM", userid)
        except Exception:
            logger.warning("Unexpected error sending digest DM to %s", userid, exc_info=True)

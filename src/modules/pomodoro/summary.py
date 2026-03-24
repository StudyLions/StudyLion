# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-18
# Purpose: Session summary card generation for premium pomodoro (individual + group)
# ============================================================
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .timer import Timer
    from meta import LionBot

logger = logging.getLogger(__name__)


async def generate_individual_summary(
    bot: 'LionBot',
    timer: 'Timer',
    userid: int,
    session_minutes: float,
    focus_minutes: float,
) -> Optional[dict]:
    """
    Generate data for an individual session summary card.

    Returns a dict with user stats, streak info, and newly earned milestones,
    or None if data fetching fails.
    """
    try:
        focus_length_minutes = timer.data.focus_length / 60
        cycles_completed = int(focus_minutes / focus_length_minutes) if focus_length_minutes > 0 else 0

        from .gamification import get_streak_data, check_milestones

        streak_data = await get_streak_data(bot, userid)
        new_milestones = await check_milestones(bot, userid, timer.data.guildid)

        return {
            'timer_name': timer.base_name,
            'user_id': userid,
            'session_minutes': round(session_minutes, 1),
            'focus_minutes': round(focus_minutes, 1),
            'cycles_completed': cycles_completed,
            'streak_data': streak_data,
            'new_milestones': new_milestones,
        }
    except Exception:
        logger.warning(
            "Failed to generate individual summary for user %s on timer %s",
            userid, timer.data.channelid, exc_info=True,
        )
        return None


async def generate_group_summary(
    bot: 'LionBot',
    timer: 'Timer',
) -> Optional[dict]:
    """
    Generate data for a group session summary card (when a timer stops).

    Aggregates stats across all members who participated.
    Returns None on failure.
    """
    try:
        from .gamification import get_streak_data

        focus_length_minutes = timer.data.focus_length / 60
        members_data = []
        total_focus = 0.0
        total_cycles = 0
        top_studier_id = None
        top_focus = 0.0

        for member in timer.members:
            # Placeholder: actual per-member tracking will be wired in by the timer
            member_focus = 0.0
            member_session = 0.0

            streak_data = await get_streak_data(bot, member.id)
            cycles = int(member_focus / focus_length_minutes) if focus_length_minutes > 0 else 0

            members_data.append({
                'userid': member.id,
                'session_minutes': round(member_session, 1),
                'focus_minutes': round(member_focus, 1),
                'streak_data': streak_data,
            })

            total_focus += member_focus
            total_cycles += cycles

            if member_focus > top_focus:
                top_focus = member_focus
                top_studier_id = member.id

        return {
            'timer_name': timer.base_name,
            'members': members_data,
            'total_focus_minutes': round(total_focus, 1),
            'total_cycles': total_cycles,
            'top_studier_id': top_studier_id,
        }
    except Exception:
        logger.warning(
            "Failed to generate group summary for timer %s",
            timer.data.channelid, exc_info=True,
        )
        return None


async def send_summary_embed(
    bot: 'LionBot',
    channel_id: int,
    summary_data: dict,
    is_group: bool = False,
) -> None:
    """
    Build and send a Discord embed with session summary data.

    Non-critical — failures are logged and silently swallowed.
    """
    try:
        import discord

        if is_group:
            color = discord.Colour(0x78B7EF)
            title = f"📋 Group Session Summary — {summary_data['timer_name']}"
        else:
            color = discord.Colour(0xDDB21D)
            title = f"🎯 Session Summary — {summary_data['timer_name']}"

        embed = discord.Embed(title=title, colour=color)

        if is_group:
            for m in summary_data.get('members', []):
                user = bot.get_user(m['userid'])
                name = str(user) if user else f"User {m['userid']}"
                embed.add_field(
                    name=name,
                    value=(
                        f"Focus: **{m['focus_minutes']:.0f}** min\n"
                        f"Session: **{m['session_minutes']:.0f}** min"
                    ),
                    inline=True,
                )

            embed.add_field(
                name="Total Focus Time",
                value=f"**{summary_data['total_focus_minutes']:.0f}** minutes",
                inline=False,
            )
            embed.add_field(
                name="Total Cycles",
                value=str(summary_data['total_cycles']),
                inline=True,
            )

            top_id = summary_data.get('top_studier_id')
            if top_id:
                top_user = bot.get_user(top_id)
                embed.add_field(
                    name="⭐ Top Studier",
                    value=str(top_user) if top_user else f"<@{top_id}>",
                    inline=True,
                )
        else:
            embed.add_field(
                name="Focus Time",
                value=f"**{summary_data['focus_minutes']:.0f}** minutes",
                inline=True,
            )
            embed.add_field(
                name="Cycles",
                value=str(summary_data['cycles_completed']),
                inline=True,
            )

            streak = summary_data.get('streak_data', {})
            embed.add_field(
                name="Streak",
                value=f"🔥 {streak.get('current_daily_streak', 0)} day(s)",
                inline=True,
            )
            embed.add_field(
                name="Focus Power",
                value=str(streak.get('focus_power', 0)),
                inline=True,
            )

            milestones = summary_data.get('new_milestones', [])
            if milestones:
                milestone_text = "\n".join(f"🏆 {ms}" for ms in milestones)
                embed.add_field(
                    name="New Milestones!",
                    value=milestone_text,
                    inline=False,
                )

        channel = bot.get_channel(channel_id)
        if channel is not None:
            await channel.send(embed=embed)
        else:
            logger.debug("Summary channel %s not found, skipping send", channel_id)
    except Exception:
        logger.warning(
            "Failed to send summary embed to channel %s", channel_id, exc_info=True,
        )

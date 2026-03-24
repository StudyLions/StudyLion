import logging
from typing import TYPE_CHECKING

from meta import LionBot
from utils.lib import utc_now

from gui.cards import FocusTimerCard, BreakTimerCard

if TYPE_CHECKING:
    from .timer import Timer, Stage
    from tracking.voice.cog import VoiceTrackerCog

logger = logging.getLogger(__name__)


# --- AI-MODIFIED (2026-03-18) ---
# Purpose: Accept premium params, fetch extra data for premium cards,
#          pass through to card constructor. Non-premium path is unchanged.
async def get_timer_card(
    bot: LionBot, timer: 'Timer', stage: 'Stage',
    premium: bool = False, refresh_interval: int = 300, cycle_count: int = 0
):
    voicecog: 'VoiceTrackerCog' = bot.get_cog('VoiceTrackerCog')

    name = timer.base_name
    if stage is not None:
        duration = stage.duration
        remaining = (stage.end - utc_now()).total_seconds()
    else:
        remaining = duration = timer.data.focus_length

    card_users = []
    guildid = timer.data.guildid
    for member in timer.members:
        if voicecog is not None:
            session = voicecog.get_session(guildid, member.id)
            tag = session.tag
            # --- AI-MODIFIED (2026-03-23) ---
            # Purpose: Clamp to zero so pending sessions (start_time in the future,
            # e.g. after daily voice cap expiry) don't display negative durations
            if session.start_time:
                session_duration = max(0, (utc_now() - session.start_time).total_seconds())
            else:
                session_duration = 0
            # --- END AI-MODIFIED ---
        else:
            session_duration = 0
            tag = None

        card_user = (
            (member.id, (member.avatar or member.default_avatar).key),
            session_duration,
            tag,
        )
        card_users.append(card_user)

    if stage is None or stage.focused:
        card_cls = FocusTimerCard
    else:
        card_cls = BreakTimerCard

    skin = await bot.get_cog('CustomSkinCog').get_skinargs_for(
        timer.data.guildid, None, card_cls.card_id
    )

    premium_kwargs = {}
    if premium:
        try:
            theme_name = 'default'
            streak_data = {}
            group_stats = {}

            config = await timer.premium_config()
            if config:
                theme_name = config.timer_theme or 'default'

            from .gamification import get_streak_data
            for member in timer.members:
                sd = await get_streak_data(bot, member.id)
                streak_data[member.id] = sd

            total_time = sum(u[1] for u in card_users)
            group_stats = {
                'total_time': total_time,
                'member_count': len(card_users),
            }

            premium_kwargs = dict(
                premium=True,
                refresh_interval=refresh_interval,
                theme_name=theme_name,
                cycle_count=cycle_count,
                streak_data=streak_data,
                group_stats=group_stats,
            )
        except Exception:
            logger.warning("Premium data fetch failed, rendering standard card")
            premium_kwargs = {}

    return card_cls(
        name,
        remaining,
        duration,
        users=card_users,
        **premium_kwargs,
    )
# --- END AI-MODIFIED ---

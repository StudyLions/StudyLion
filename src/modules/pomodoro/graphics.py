from typing import TYPE_CHECKING

from meta import LionBot
from utils.lib import utc_now

from gui.cards import FocusTimerCard, BreakTimerCard

if TYPE_CHECKING:
    from .timer import Timer, Stage
    from tracking.voice.cog import VoiceTrackerCog


async def get_timer_card(bot: LionBot, timer: 'Timer', stage: 'Stage'):
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
            if session.start_time:
                session_duration = (utc_now() - session.start_time).total_seconds()
            else:
                session_duration = 0
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

    return card_cls(
        name,
        remaining,
        duration,
        users=card_users,
    )

from collections import namedtuple
from core.data import RankType
from core.lion_guild import VoiceMode

from meta import conf, LionBot
from babel.translator import ctx_translator

from .. import babel

_p = babel._p

RankBase = namedtuple("RankBase", ("name", "required", "reward", "message", "colour"))

"""
Reward message defaults
"""

voice_reward_msg = _p(
    'ui:rank_editor|input:message|default|type:voice',
    "Congratulations {user_mention}!\n"
    "For working hard for **{requires}**, you have achieved the rank of "
    "**{role_name}** in **{guild_name}**! Keep up the good work."
)

xp_reward_msg = _p(
    'ui:rank_editor|input:message|default|type:xp',
    "Congratulations {user_mention}!\n"
    "For earning **{requires}**, you have achieved the guild rank of "
    "**{role_name}** in **{guild_name}**!"
)

msg_reward_msg = _p(
    'ui:rank_editor|input:message|default|type:msg',
    "Congratulations {user_mention}!\n"
    "For sending **{requires}**, you have achieved the guild rank of "
    "**{role_name}** in **{guild_name}**!"
)


"""
Rank templates based on voice activity
"""

study_voice_template = [
    RankBase(
        name=_p('rank_autocreate|template|type:study_voice|level:1',
                "Voice Level 1 (1h)"),
        required=3600,
        reward=1000,
        message=voice_reward_msg,
        colour="#1f28e2"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:study_voice|level:2',
                "Voice Level 2 (3h)"),
        required=10800,
        reward=2000,
        message=voice_reward_msg,
        colour="#006bff"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:study_voice|level:3',
                "Voice Level 3 (6h)"),
        required=21600,
        reward=3000,
        message=voice_reward_msg,
        colour="#0091ff"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:study_voice|level:4',
                "Voice Level 4 (10h)"),
        required=36000,
        reward=4000,
        message=voice_reward_msg,
        colour="#00adf5"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:study_voice|level:5',
                "Voice Level 5 (20h)"),
        required=72000,
        reward=5000,
        message=voice_reward_msg,
        colour="#00c6bf"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:study_voice|level:6',
                "Voice Level 6 (40h)"),
        required=144000,
        reward=6000,
        message=voice_reward_msg,
        colour="#00db86"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:study_voice|level:7',
                "Voice Level 7 (80h)"),
        required=288000,
        reward=7000,
        message=voice_reward_msg,
        colour="#7cea5a"
        )
]

general_voice_template = [
    RankBase(
        name=_p('rank_autocreate|template|type:general_voice|level:1',
                "Voice Level 1 (1h)"),
        required=3600,
        reward=1000,
        message=voice_reward_msg,
        colour="#1f28e2"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:general_voice|level:2',
                "Voice Level 2 (2h)"),
        required=7200,
        reward=2000,
        message=voice_reward_msg,
        colour="#006bff"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:general_voice|level:3',
                "Voice Level 3 (4h)"),
        required=14400,
        reward=3000,
        message=voice_reward_msg,
        colour="#0091ff"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:general_voice|level:4',
                "Voice Level 4 (8h)"),
        required=28800,
        reward=4000,
        message=voice_reward_msg,
        colour="#00adf5"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:general_voice|level:5',
                "Voice Level 5 (16h)"),
        required=57600,
        reward=5000,
        message=voice_reward_msg,
        colour="#00c6bf"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:general_voice|level:6',
                "Voice Level 6 (32h)"),
        required=115200,
        reward=6000,
        message=voice_reward_msg,
        colour="#00db86"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:general_voice|level:7',
                "Voice Level 7 (64h)"),
        required=230400,
        reward=7000,
        message=voice_reward_msg,
        colour="#7cea5a"
        )
]

"""
Rank templates based on message XP earned
"""

xp_template = [
    RankBase(
        name=_p('rank_autocreate|template|type:xp|level:1',
                "XP Level 1 (2000)"),
        required=2000,
        reward=1000,
        message=xp_reward_msg,
        colour="#1f28e2"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:xp|level:2',
                "XP Level 2 (4000)"),
        required=4000,
        reward=2000,
        message=xp_reward_msg,
        colour="#006bff"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:xp|level:3',
                "XP Level 3 (8000)"),
        required=8000,
        reward=3000,
        message=xp_reward_msg,
        colour="#0091ff"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:xp|level:4',
                "XP Level 4 (16000)"),
        required=16000,
        reward=4000,
        message=xp_reward_msg,
        colour="#00adf5"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:xp|level:5',
                "XP Level 5 (32000)"),
        required=32000,
        reward=5000,
        message=xp_reward_msg,
        colour="#00c6bf"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:xp|level:6',
                "XP Level 6 (64000)"),
        required=64000,
        reward=6000,
        message=xp_reward_msg,
        colour="#00db86"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:xp|level:7',
                "XP Level 7 (128000)"),
        required=128000,
        reward=7000,
        message=xp_reward_msg,
        colour="#7cea5a"
        )
]

"""
Rank templates based on messages sent
"""

msg_template = [
    RankBase(
        name=_p('rank_autocreate|template|type:msg|level:1',
                "Message Level 1 (200)"),
        required=200,
        reward=1000,
        message=msg_reward_msg,
        colour="#1f28e2"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:msg|level:2',
                "Message Level 2 (400)"),
        required=400,
        reward=2000,
        message=msg_reward_msg,
        colour="#006bff"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:msg|level:3',
                "Message Level 3 (800)"),
        required=800,
        reward=3000,
        message=msg_reward_msg,
        colour="#0091ff"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:msg|level:4',
                "Message Level 4 (1600)"),
        required=1600,
        reward=4000,
        message=msg_reward_msg,
        colour="#00adf5"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:msg|level:5',
                "Message Level 5 (3200)"),
        required=3200,
        reward=5000,
        message=msg_reward_msg,
        colour="#00c6bf"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:msg|level:6',
                "Message Level 6 (6400)"),
        required=6400,
        reward=6000,
        message=msg_reward_msg,
        colour="#00db86"
        ),
    RankBase(
        name=_p('rank_autocreate|template|type:msg|level:7',
                "Message Level 7 (12800)"),
        required=12800,
        reward=7000,
        message=msg_reward_msg,
        colour="#7cea5a"
        )
]


def get_guild_template(rank_type: RankType, voice_mode: VoiceMode):
    """
    Returns the best fit rank template
    based on the guild's rank type and voice mode.
    """
    if rank_type == RankType.VOICE:
        if voice_mode == VoiceMode.STUDY:
            return study_voice_template
        if voice_mode == VoiceMode.VOICE:
            return general_voice_template
    if rank_type == RankType.XP:
        return xp_template
    if rank_type == RankType.MESSAGE:
        return msg_template
    return None

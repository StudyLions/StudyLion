from typing import Optional

from core.data import RankType
from utils.lib import strfdur
from babel.translator import ctx_translator

from . import babel
from .data import RankData

_p = babel._p

rank_message_keys = [
    ("{role_name}", _p('formatstring:rank_message|key:role_name', "{role_name}")),
    ("{guild_name}", _p('formatstring:rank_message|key:guild_name', "{guild_name}")),
    ("{user_name}", _p('formatstring:rank_message|key:user_name', "{user_name}")),
    ("{role_id}", _p('formatstring:rank_message|key:role_id', "{role_id}")),
    ("{guild_id}", _p('formatstring:rank_message|key:guild_id', "{guild_id}")),
    ("{user_id}", _p('formatstring:rank_message|key:user_id', "{user_id}")),
    ("{role_mention}", _p('formatstring:rank_message|key:role_mention', "{role_mention}")),
    ("{user_mention}", _p('formatstring:rank_message|key:user_mention', "{user_mention}")),
    ("{requires}", _p('formatstring:rank_message|key:requires', "{rank_requires}")),
]


def rank_model_from_type(rank_type: RankType):
    if rank_type is RankType.VOICE:
        model = RankData.VoiceRank
    elif rank_type is RankType.MESSAGE:
        model = RankData.MsgRank
    elif rank_type is RankType.XP:
        model = RankData.XPRank
    return model


def stat_data_to_value(rank_type: RankType, data: int) -> float:
    if rank_type is RankType.VOICE:
        value = round(data / 36) / 100
    else:
        value = data
    return value


def format_stat_range(rank_type: RankType, start_data: int, end_data: Optional[int] = None, short=True) -> str:
    """
    Format the given statistic range into a string, depending on the provided rank type.
    """
    # TODO: LOCALISE
    if rank_type is RankType.VOICE:
        """
        5 - 10 hrs
        5 - 10 hours
        5h10m - 6h
        5h10m - 6 hours
        """
        if end_data is not None:
            if not start_data % 3600 and not end_data % 3600:
                # Both start and end are an even number of hours
                # Just divide them by 3600 and stick hrs or hours on the end.
                start = start_data // 3600
                end = end_data // 3600
                suffix = "hrs" if short else "hours"
                formatted = f"{start} - {end} {suffix}"
            else:
                # Not even values, thus strfdur both
                start = strfdur(start_data, short=short)
                end = strfdur(end_data, short=short)
                formatted = f"{start} - {end}"
        else:
            formatted = strfdur(start_data, short=short)
    elif rank_type is RankType.MESSAGE:
        suffix = "msgs" if short else "messages"
        if end_data is not None:
            formatted = f"{start_data} - {end_data} {suffix}"
        else:
            formatted = f"{start_data} {suffix}"
    elif rank_type is RankType.XP:
        suffix = "XP"
        if end_data is not None:
            formatted = f"{start_data} - {end_data} {suffix}"
        else:
            formatted = f"{start_data} {suffix}"

    return formatted


def stat_value_to_data(rank_type: RankType, value: float) -> int:
    if rank_type is RankType.VOICE:
        data = int(round(value * 100) * 36)
    else:
        data = value
    return data

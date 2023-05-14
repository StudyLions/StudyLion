from settings import ModelData
from settings.groups import SettingGroup
from settings.setting_types import BoolSetting, ChannelSetting, EnumSetting

from core.data import RankType, CoreData
from babel.translator import ctx_translator

from . import babel

_p = babel._p


class RankSettings(SettingGroup):
    """
    Rank Type
    """

    class RankStatType(ModelData, EnumSetting):
        """
        The type of statistic used to determine ranks in a Guild.
        One of VOICE, XP, or MESSAGE
        """
        _enum = RankType
        _default = RankType.VOICE
        _outputs = {
            RankType.VOICE: '`Voice`',
            RankType.XP: '`Exp`',
            RankType.MESSAGE: '`Messages`'
        }
        _inputs = {
            'voice': RankType.VOICE,
            'study': RankType.VOICE,
            'text': RankType.MESSAGE,
            'message': RankType.MESSAGE,
            'messages': RankType.MESSAGE,
            'xp': RankType.XP,
            'exp': RankType.XP
        }

        setting_id = 'rank_type'
        _event = 'guildset_rank_type'

        _display_name = _p('guildset:rank_type', "rank_type")
        _desc = _p(
            'guildset:rank_type|desc',
            "The type of statistic (messages | xp | voice hours) used to determine activity ranks."
        )
        _long_desc = _p(
            'guildset:rank_type|long_desc',
            "Which statistic is used to reward activity ranks.\n"
            "`Voice` is the number of hours active in tracked voice channels, "
            "`Exp` is a measure of message activity, and "
            "`Message` is a simple count of messages sent."
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.rank_type.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.value is RankType.VOICE:
                resp = t(_p(
                    'guildset:rank_type|set_response|type:voice',
                    "Members will be awarded activity ranks based on `Voice Activity`."
                ))
            elif self.value is RankType.MESSAGE:
                resp = t(_p(
                    'guildset:rank_type|set_response|type:messages',
                    "Members will be awarded activity ranks based on `Messages Sent`."
                ))
            elif self.value is RankType.XP:
                resp = t(_p(
                    'guildset:rank_type|set_response|type:xp',
                    "Members will be awarded activity ranks based on `Message XP Earned`."
                ))
            return resp

    class RankChannel(ModelData, ChannelSetting):
        """
        Channel to send Rank notifications.

        If DMRanks is set, this will only be used when the target user has disabled DM notifications.
        """
        setting_id = 'rank_channel'

        _display_name = _p('guildset:rank_channel', "rank_channel")
        _desc = _p(
            'guildset:rank_channel|desc',
            "The channel in which to send rank update notifications."
        )
        _long_desc = _p(
            'guildset:rank_channel|long_desc',
            "Whenever a user advances a rank, a congratulatory message will be sent in this channel, if set. "
            "If `dm_ranks` is enabled, this channel will only be used when the user has opted not to receive "
            "DM notifications, or is otherwise unreachable."
        )
        _model = CoreData.Guild
        _column = CoreData.Guild.rank_channel.name

    class DMRanks(ModelData, BoolSetting):
        """
        Whether to DM rank notifications.
        """
        setting_id = 'dm_ranks'

        _display_name = _p('guildset:dm_ranks', "dm_ranks")
        _desc = _p(
            'guildset:dm_ranks|desc',
            "Whether to send rank advancement notifications through direct messages."
        )
        _long_desc = _p(
            'guildset:dm_ranks|long_desc',
            "If enabled, congratulatory messages for rank advancement will be direct messaged to the user, "
            "instead of being sent to the configured `rank_channel`."
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.dm_ranks.name

from settings import ModelData
from settings.groups import SettingGroup
from settings.setting_types import BoolSetting, ChannelSetting, EnumSetting

from core.data import RankType, CoreData
from babel.translator import ctx_translator
from wards import high_management_iward

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
            RankType.VOICE: _p('guildset:rank_type|output:voice', '`Voice`'),
            RankType.XP: _p('guildset:rank_type|output:xp', '`Exp`'),
            RankType.MESSAGE: _p('guildset:rank_type|output:message', '`Messages`'),
        }
        _input_formatted = {
            RankType.VOICE: _p('guildset:rank_type|input_format:voice', 'Voice'),
            RankType.XP: _p('guildset:rank_type|input_format:xp', 'Exp'),
            RankType.MESSAGE: _p('guildset:rank_type|input_format:message', 'Messages'),
        }
        _input_patterns = {
            RankType.VOICE: _p('guildset:rank_type|input_pattern:voice', 'voice|study'),
            RankType.MESSAGE: _p('guildset:rank_type|input_pattern:voice', 'text|message|messages'),
            RankType.XP: _p('guildset:rank_type|input_pattern:xp', 'xp|exp|experience'),
        }

        setting_id = 'rank_type'
        _event = 'guildset_rank_type'
        _set_cmd = 'admin config ranks'
        _write_ward = high_management_iward

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
        _accepts = _p(
            'guildset:rank_type|accepts',
            "Voice/Exp/Messages"
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

        @property
        def set_str(self) -> str:
            cmdstr = super().set_str
            t = ctx_translator.get().t
            return t(_p(
                'guildset:rank_channel|set_using',
                "{cmd} or option menu below."
            )).format(cmd=cmdstr)

    class RankChannel(ModelData, ChannelSetting):
        """
        Channel to send Rank notifications.

        If DMRanks is set, this will only be used when the target user has disabled DM notifications.
        """
        setting_id = 'rank_channel'
        _set_cmd = 'admin config ranks'
        _write_ward = high_management_iward

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
        _accepts = _p(
            'guildset:rank_channel|accepts',
            "Rank notification channel name or id."
        )
        _model = CoreData.Guild
        _column = CoreData.Guild.rank_channel.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is not None:
                resp = t(_p(
                    'guildset:rank_channel|set_response|set',
                    "Rank update messages will be sent to {channel}."
                )).format(channel=value.mention)
            else:
                resp = t(_p(
                    'guildset:rank_channel|set_response|unset',
                    "Rank update messages will be ignored or sent via DM (if `dm_ranks` is enabled)."
                ))
            return resp

        @property
        def set_str(self) -> str:
            cmdstr = super().set_str
            t = ctx_translator.get().t
            return t(_p(
                'guildset:rank_channel|set_using',
                "{cmd} or channel selector below."
            )).format(cmd=cmdstr)

    class DMRanks(ModelData, BoolSetting):
        """
        Whether to DM rank notifications.
        """
        setting_id = 'dm_ranks'
        _set_cmd = 'admin config ranks'
        _write_ward = high_management_iward

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
        _default = True

        _model = CoreData.Guild
        _column = CoreData.Guild.dm_ranks.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data:
                return t(_p(
                    'guildset:dm_ranks|response:true',
                    "I will direct message members upon rank advancement."
                ))
            else:
                return t(_p(
                    'guildset:dm_ranks|response:false',
                    "I will never direct message members upon rank advancement."
                ))

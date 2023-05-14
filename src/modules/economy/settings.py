"""
Settings for the Economy Cog.
"""

from typing import Optional
import asyncio
from collections import defaultdict

from settings.groups import SettingGroup
from settings.data import ModelData, ListData
from settings.setting_types import ChannelListSetting, IntegerSetting, BoolSetting

from meta.config import conf
from meta.sharding import THIS_SHARD
from meta.logger import log_wrap
from core.data import CoreData
from babel.translator import ctx_translator

from . import babel, logger
from .data import EconomyData

_p = babel._p


class EconomySettings(SettingGroup):
    """
    Economy Settings:
        coins_per_100xp
        allow_transfers
    """
    class CoinsPerXP(ModelData, IntegerSetting):
        setting_id = 'coins_per_xp'

        _display_name = _p('guildset:coins_per_xp', "coins_per_100xp")
        _desc = _p(
            'guildset:coins_per_xp|desc',
            "How many LionCoins to reward members per 100 XP they earn."
        )
        _long_desc = _p(
            'guildset:coins_per_xp|long_desc',
            "Members will be rewarded with this many LionCoins for every 100 XP they earn."
        )
        # This default needs to dynamically depend on the guild mode!
        _default = 50

        _model = CoreData.Guild
        _column = CoreData.Guild.coins_per_centixp.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:coins_per_xp|set_response',
                "For every **100** XP they earn, members will now be given {coin}**{amount}**."
            )).format(amount=self.value, coin=conf.emojis.coin)

    class AllowTransfers(ModelData, BoolSetting):
        setting_id = 'allow_transfers'

        _display_name = _p('guildset:allow_transfers', "allow_transfers")
        _desc = _p(
            'guildset:allow_transfers|desc',
            "Whether to allow members to transfer LionCoins to each other."
        )
        _long_desc = _p(
            'guildset:allow_transfers|long_desc',
            "If disabled, members will not be able to use `/sendcoins` to transfer LionCoinds."
        )
        _default = True

        _model = CoreData.Guild
        _column = CoreData.Guild.allow_transfers.name

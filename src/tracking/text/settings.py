from typing import Optional
import asyncio
from collections import defaultdict

from settings.groups import SettingGroup
from settings.data import ModelData, ListData
from settings.setting_types import ChannelListSetting, IntegerSetting

from meta.config import conf
from meta.sharding import THIS_SHARD
from meta.logger import log_wrap
from core.data import CoreData
from babel.translator import ctx_translator
from wards import low_management_iward

from . import babel, logger
from .data import TextTrackerData

_p = babel._p


class TextTrackerSettings(SettingGroup):
    """
    Guild settings:
        xp per period (guild_config.period_xp)
        additional xp per hundred words (guild_config.word_xp)
        coins per hundred xp (guild_config.xp_coins)
        untracked channels (untracked_text_channels(channelid PK, guildid FK))
    """
    class XPPerPeriod(ModelData, IntegerSetting):
        setting_id = 'xp_per_period'
        _set_cmd = 'config message_exp'
        _write_ward = low_management_iward

        _display_name = _p('guildset:xp_per_period', "xp_per_5min")
        _desc = _p(
            'guildset:xp_per_period|desc',
            "How much XP members will be given every 5 minute period they are active."
        )
        _long_desc = _p(
            'guildset:xp_per_period|long_desc',
            "Amount of message XP to give members for each 5 minute period in which they are active (send a message). "
            "Note that this XP is only given *once* per period."
        )
        _accepts = _p(
            'guildset:xp_per_period|accepts',
            "Number of message XP to reward per 5 minute active period."
        )
        _default = 101  # TODO: Make a dynamic default based on the global setting?

        _model = CoreData.Guild
        _column = CoreData.Guild.xp_per_period.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:xp_per_period|set_response',
                "For every **5** minutes they are active (i.e. in which they send a message), "
                "members will now be given **{amount}** XP."
            )).format(amount=self.value)

    class WordXP(ModelData, IntegerSetting):
        setting_id = 'word_xp'
        _set_cmd = 'config message_exp'
        _write_ward = low_management_iward

        _display_name = _p('guildset:word_xp', "xp_per_100words")
        _desc = _p(
            'guildset:word_xp|desc',
            "How much XP members will be given per hundred words they write."
        )
        _long_desc = _p(
            'guildset:word_xp|long_desc',
            "Amount of message XP to be given (additionally to the XP per period) for each hundred words. "
            "Useful for rewarding communication."
        )
        _accepts = _p(
            'guildset:word_xp|accepts',
            "Number of XP to reward per hundred words sent."
        )
        _default = 50

        _model = CoreData.Guild
        _column = CoreData.Guild.xp_per_centiword.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:word_xp|set_response',
                "For every **100** words they send, members will now be rewarded an additional **{amount}** XP."
            )).format(amount=self.value)

    class UntrackedTextChannels(ListData, ChannelListSetting):
        setting_id = 'untracked_text_channels'
        _write_ward = low_management_iward

        _display_name = _p('guildset:untracked_text_channels', "untracked_text_channels")
        _desc = _p(
            'guildset:untracked_text_channels|desc',
            "Channels in which Message XP will not be given."
        )
        _long_desc = _p(
            'guildset:untracked_text_channels|long_desc',
            "Messages sent in these channels will not count towards a member's message XP. "
            "If a category is selected, then all channels under the category will also be untracked."
        )
        _accepts = _p(
            'guildset:untracked_text_channels|accepts',
            "Comma separated list of untracked text channel names or ids."
        )
        _notset_str = _p(
            'guildset:untracked_text_channels|notset',
            "Not Set (all text channels will be tracked.)"
        )

        _default = None
        _table_interface = TextTrackerData.untracked_channels
        _id_column = 'guildid'
        _data_column = 'channelid'
        _order_column = 'channelid'

        _cache = {}

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data:
                resp = t(_p(
                    'guildset:untracked_text_channels|set_response|set',
                    "Messages in or under the following channels will be ignored: {channels}"
                )).format(channels=self.formatted)
            else:
                resp = t(_p(
                    'guildset:untracked_text_channels|set_response|notset',
                    "Message XP will now be tracked in every channel."
                ))
            return resp

        @property
        def set_str(self) -> str:
            t = ctx_translator.get().t
            return t(_p(
                'guildset:untracked_text_channels|set_using',
                "Channel selector below"
            ))

        @classmethod
        @log_wrap(action='Cache Untracked Text Channels')
        async def setup(cls, bot):
            """
            Pre-load untracked text channels for every guild on the current shard.
            """
            data: TextTrackerData = bot.db.registries['TextTrackerData']
            # TODO: Filter by joining on guild_config with last_left = NULL
            # Otherwise we are also caching all the guilds we left
            rows = await data.untracked_channels.select_where(THIS_SHARD)
            new_cache = defaultdict(list)
            count = 0
            for row in rows:
                new_cache[row['guildid']].append(row['channelid'])
                count += 1
            cls._cache.clear()
            cls._cache.update(new_cache)
            logger.info(f"Loaded {count} untracked text channels on this shard.")


class TextTrackerGlobalSettings(SettingGroup):
    """
    Configure global XP rates for the text tracker.
    """
    class XPPerPeriod(ModelData, IntegerSetting):
        setting_id = 'xp_per_period'
        _set_cmd = 'leo configure experience_rates'

        _display_name = _p('botset:xp_per_period', "xp_per_5min")
        _desc = _p(
            'botset:xp_per_period|desc',
            "How much global XP members will be given every 5 minute period they are active."
        )
        _long_desc = _p(
            'botset:xp_per_period|long_desc',
            "Amount of global message XP to give members "
            "for each 5 minute period in which they are active (send a message). "
            "Note that this XP is only given *once* per period."
        )
        _accepts = _p(
            'botset:xp_per_period|accepts',
            "Number of message XP to reward per 5 minute active period."
        )
        _default = 101

        _model = TextTrackerData.BotConfigText
        _column = TextTrackerData.BotConfigText.xp_per_period.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'leoset:xp_per_period|set_response',
                "For every **5** minutes they are active (i.e. in which they send a message), "
                "all users will now be given **{amount}** global XP."
            )).format(amount=self.value)

    class WordXP(ModelData, IntegerSetting):
        setting_id = 'word_xp'
        _set_cmd = 'leo configure experience_rates'

        _display_name = _p('botset:word_xp', "xp_per_100words")
        _desc = _p(
            'botset:word_xp|desc',
            "How much global XP members will be given per hundred words they write."
        )
        _long_desc = _p(
            'botset:word_xp|long_desc',
            "Amount of global message XP to be given (additionally to the XP per period) for each hundred words. "
            "Useful for rewarding communication."
        )
        _accepts = _p(
            'botset:word_xp|accepts',
            "Number of XP to reward per hundred words sent."
        )
        _default = 50

        _model = TextTrackerData.BotConfigText
        _column = TextTrackerData.BotConfigText.xp_per_centiword.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'leoset:word_xp|set_response',
                "For every **100** words they send, users will now be rewarded an additional **{amount}** global XP."
            )).format(amount=self.value)

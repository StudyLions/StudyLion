from typing import Optional
import asyncio
from collections import defaultdict
import discord
from discord.ui.select import select, Select, ChannelSelect
from discord.ui.button import button, Button, ButtonStyle

from settings.groups import SettingGroup
from settings.data import ModelData, ListData
from settings.setting_types import ChannelListSetting, IntegerSetting, DurationSetting

from meta import conf, LionBot
from meta.sharding import THIS_SHARD
from meta.logger import log_wrap
from utils.lib import MessageArgs
from utils.ui import LeoUI, ConfigUI, DashboardSection
from wards import low_management_iward

from core.data import CoreData
from core.lion_guild import VoiceMode
from babel.translator import ctx_translator

from . import babel, logger
from .data import VoiceTrackerData

_p = babel._p


# untracked channels
# hourly_reward
# hourly_live_bonus
# daily_voice_cap


class VoiceTrackerSettings(SettingGroup):
    class UntrackedChannels(ListData, ChannelListSetting):
        setting_id = 'untracked_channels'
        _event = 'guildset_untracked_channels'
        _set_cmd = 'config voice_rewards'
        _write_ward = low_management_iward

        _display_name = _p('guildset:untracked_channels', "untracked_channels")
        _desc = _p(
            'guildset:untracked_channels|desc',
            "Channels which will be ignored for statistics tracking."
        )
        _long_desc = _p(
            'guildset:untracked_channels|long_desc',
            "Activity in these channels will not count towards a member's statistics. "
            "If a category is selected, all channels under the category will be untracked."
        )
        _accepts = _p(
            'guildset:untracked_channels|accepts',
            "Comma separated list of untracked channel name/ids."
        )
        _notset_str = _p(
            'guildset:untracked_channels|notset',
            "Not Set (all voice channels will be tracked.)"
        )

        _default = None

        _table_interface = VoiceTrackerData.untracked_channels
        _id_column = 'guildid'
        _data_column = 'channelid'
        _order_column = 'channelid'

        _cache = {}

        @property
        def set_str(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:untracked_channels|set',
                "Channel selector below."
            ))

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data:
                resp = t(_p(
                    'guildset:untracked_channels|set_response|set',
                    "Activity in the following channels will now be ignored: {channels}"
                )).format(
                    channels=self.formatted
                )
            else:
                resp = t(_p(
                    'guildset:untracked_channels|set_response|unset',
                    "All voice channels will now be tracked."
                ))
            return resp

        @classmethod
        @log_wrap(action='Cache Untracked Channels')
        async def setup(cls, bot):
            """
            Pre-load untracked channels for every guild on the current shard.
            """
            data: VoiceTrackerData = bot.db.registries['VoiceTrackerData']
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
            logger.info(f"Loaded {count} untracked channels on this shard.")

    class HourlyReward(ModelData, IntegerSetting):
        setting_id = 'hourly_reward'
        _event = 'on_guildset_hourly_reward'
        _set_cmd = 'config voice_rewards'
        _write_ward = low_management_iward

        _display_name = _p('guildset:hourly_reward', "hourly_reward")
        _desc = _p(
            'guildset:hourly_reward|mode:voice|desc',
            "LionCoins given per hour in a voice channel."
        )
        _long_desc = _p(
            'guildset:hourly_reward|mode:voice|long_desc',
            "Number of LionCoins to each member per hour that they stay in a tracked voice channel."
        )
        _accepts = _p(
            'guildset:hourly_reward|accepts',
            "Number of coins to reward per hour in voice."
        )

        _default = 50
        _min = 0
        _max = 2**15

        _model = CoreData.Guild
        _column = CoreData.Guild.study_hourly_reward.name

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return t(_p(
                    'guildset:hourly_reward|formatted',
                    "{coin}**{amount}** per hour."
                )).format(
                    coin=conf.emojis.coin,
                    amount=data
                )

    class HourlyReward_Voice(HourlyReward):
        """
        Voice-mode specialised version of HourlyReward
        """
        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:hourly_reward|mode:voice|response',
                "Members will be given {coin}**{amount}** per hour in a voice channel!"
            )).format(
                coin=conf.emojis.coin,
                amount=self.data
            )

    class HourlyReward_Study(HourlyReward):
        """
        Study-mode specialised version of HourlyReward.
        """
        _desc = _p(
            'guildset:hourly_reward|mode:study|desc',
            "LionCoins given per hour of study."
        )
        _long_desc = _p(
            'guildset:hourly_reward|mode:study|long_desc',
            "Number of LionCoins given per hour of study, up to the daily hour cap."
        )

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:hourly_reward|mode:study|response',
                "Members will be given {coin}**{amount}** per hour that they study!"
            )).format(
                coin=conf.emojis.coin,
                amount=self.data
            )

    class HourlyLiveBonus(ModelData, IntegerSetting):
        """
        Guild setting describing the per-hour LionCoin bonus given to "live" members during tracking.
        """
        setting_id = 'hourly_live_bonus'
        _event = 'on_guildset_hourly_live_bonus'
        _set_cmd = 'config voice_rewards'
        _write_ward = low_management_iward

        _display_name = _p('guildset:hourly_live_bonus', "hourly_live_bonus")
        _desc = _p(
            'guildset:hourly_live_bonus|desc',
            "Bonus Lioncoins given per hour when a member streams or video-chats."
        )

        _long_desc = _p(
            'guildset:hourly_live_bonus|long_desc',
            "When a member streams or video-chats in a channel they will be given this bonus *additionally* "
            "to the `hourly_reward`."
        )
        _accepts = _p(
            'guildset:hourly_live_bonus|accepts',
            "Number of bonus coins to reward per hour when live."
        )

        _default = 150
        _min = 0
        _max = 2**15

        _model = CoreData.Guild
        _column = CoreData.Guild.study_hourly_live_bonus.name

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            t = ctx_translator.get().t
            if data is not None:
                return t(_p(
                    'guildset:hourly_live_bonus|formatted',
                    "{coin}**{amount}** bonus per hour when live."
                )).format(
                    coin=conf.emojis.coin,
                    amount=data
                )

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:hourly_live_bonus|response',
                "Live members will now *additionally* be given {coin}**{amount}** per hour."
            )).format(
                coin=conf.emojis.coin,
                amount=self.data
            )

    class DailyVoiceCap(ModelData, DurationSetting):
        setting_id = 'daily_voice_cap'
        _event = 'on_guildset_daily_voice_cap'
        _set_cmd = 'config voice_rewards'
        _write_ward = low_management_iward

        _display_name = _p('guildset:daily_voice_cap', "daily_voice_cap")
        _desc = _p(
            'guildset:daily_voice_cap|desc',
            "Maximum number of hours per day to count for each member."
        )
        _long_desc = _p(
            'guildset:daily_voice_cap|long_desc',
            "Time spend in voice channels over this amount will not be tracked towards the member's statistics. "
            "Tracking will resume at the start of the next day. "
            "The start of the day is determined by the configured guild timezone."
        )
        _accepts = _p(
            'guildset:daily_voice_cap|accepts',
            "The maximum number of voice hours to track per day."
        )

        _default = 16 * 60 * 60
        _default_multiplier = 60 * 60

        _max = 60 * 60 * 25

        _model = CoreData.Guild
        _column = CoreData.Guild.daily_study_cap.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:daily_voice_cap|response',
                "Members will be tracked for at most {duration} per day. "
                "(**NOTE:** This will not affect members currently in voice channels.)"
            )).format(
                duration=self.formatted
            )


class VoiceTrackerConfigUIALT(LeoUI):
    # TODO: Bulk edit
    # TODO: Cohesive exit
    # TODO: Back to main configuration panel

    _listening = {}

    def __init__(self, bot: LionBot, settings: VoiceTrackerSettings, guildid: int, channelid: int, **kwargs):
        super().__init__(**kwargs)
        self.bot = bot
        self.settings = settings
        self.guildid = guildid
        self.channelid = channelid

        self._original: Optional[discord.Interaction] = None
        self._message: Optional[discord.Message] = None

        self.hourly_reward: Optional[VoiceTrackerSettings.HourlyReward] = None
        self.hourly_live_bonus: Optional[VoiceTrackerSettings.HourlyLiveBonus] = None
        self.daily_voice_cap: Optional[VoiceTrackerSettings.DailyVoiceCap] = None
        self.untracked_channels: Optional[VoiceTrackerSettings.UntrackedChannels] = None

        self.embed: Optional[discord.Embed] = None

    @property
    def instances(self):
        return (self.hourly_reward, self.hourly_live_bonus, self.daily_voice_cap, self.untracked_channels)

    async def cleanup(self):
        # TODO: Swap cleanup and close..
        self._listening.pop(self.channelid, None)
        for instance in self.instances:
            instance.deregister_callback(self.id)
        try:
            if self._original is not None:
                await self._original.delete_original_response()
                self._original = None
            if self._message is not None:
                await self._message.delete()
                self._message = None
        except discord.HTTPException:
            # Interaction is likely expired or invalid, or some form of comms issue
            pass

    @button(label='CLOSE')
    async def close_button(self, interaction: discord.Interaction, pressed):
        await interaction.response.defer()
        await self.close()

    async def refresh_close_button(self):
        t = self.bot.translator.t
        self.close_button.label = t(_p('ui:voice_tracker_config|button:close|label', "Close"))

    @button(label='RESET')
    async def reset_button(self, interaction: discord.Interaction, pressed):
        await interaction.response.defer()

        for instance in self.instances:
            instance.data = None
            await instance.write()

        await self.reload()

    async def refresh_reset_button(self):
        t = self.bot.translator.t
        self.reset_button.label = t(_p('ui:voice_tracker_config|button:reset|label', "Reset"))

    @select(cls=ChannelSelect, placeholder='UNTRACKED_CHANNEL_MENU', min_values=0, max_values=25)
    async def untracked_channels_menu(self, interaction: discord.Interaction, selected):
        await interaction.response.defer()
        self.untracked_channels.value = selected.values
        await self.untracked_channels.write()
        await self.reload()

    async def refresh_untracked_channels_menu(self):
        t = self.bot.translator.t
        self.untracked_channels_menu.placeholder = t(_p(
            'ui:voice_tracker_config|menu:untracked_channels|placeholder',
            "Set Untracked Channels"
        ))

    async def run(self, interaction: discord.Interaction):
        if old := self._listening.get(self.channelid, None):
            await old.close()

        await self.refresh()

        if interaction.response.is_done():
            # Use followup to respond
            self._message = await interaction.followup.send(embed=self.embed, view=self)
        else:
            # Use interaction response to respond
            self._original = interaction
            await interaction.response.send_message(embed=self.embed, view=self)

        for instance in self.instances:
            instance.register_callback(self.id)(self.reload)

        self._listening[self.channelid] = self

    async def refresh(self):
        # TODO: Check if listening works for subclasses
        await self.refresh_close_button()
        await self.refresh_reset_button()
        await self.refresh_untracked_channels_menu()

        lguild = await self.bot.core.lions.fetch_guild(self.guildid)

        if lguild.guild_mode.voice is VoiceMode.VOICE:
            self.hourly_reward = await self.settings.HourlyReward_Voice.get(self.guildid)
        else:
            self.hourly_reward = await self.settings.HourlyReward_Study.get(self.guildid)

        self.hourly_live_bonus = lguild.config.get('hourly_live_bonus')
        self.daily_voice_cap = lguild.config.get('daily_voice_cap')
        self.untracked_channels = await self.settings.UntrackedChannels.get(self.guildid)

        self._layout = [
            (self.untracked_channels_menu,),
            (self.reset_button, self.close_button)
        ]

        self.embed = await self.make_embed()

    async def redraw(self):
        try:
            if self._message:
                await self._message.edit(embed=self.embed, view=self)
            elif self._original:
                await self._original.edit_original_response(embed=self.embed, view=self)
        except discord.HTTPException:
            await self.close()

    async def reload(self, *args, **kwargs):
        await self.refresh()
        await self.redraw()

    async def make_embed(self):
        t = self.bot.translator.t
        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        mode = lguild.guild_mode
        if mode.voice is VoiceMode.VOICE:
            title = t(_p(
                'ui:voice_tracker_config|mode:voice|embed|title',
                "Voice Tracker Configuration Panel"
            ))
        else:
            title = t(_p(
                'ui:voice_tracker_config|mode:study|embed|title',
                "Study Tracker Configuration Panel"
            ))
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title
        )
        for setting in self.instances:
            embed.add_field(**setting.embed_field, inline=False)
        return embed


class VoiceTrackerConfigUI(ConfigUI):
    setting_classes = (
        VoiceTrackerSettings.HourlyReward,
        VoiceTrackerSettings.HourlyLiveBonus,
        VoiceTrackerSettings.DailyVoiceCap,
        VoiceTrackerSettings.UntrackedChannels,
    )

    def __init__(self, bot: LionBot,
                 guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('VoiceTrackerCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    @select(
        cls=ChannelSelect,
        placeholder="UNTRACKED_CHANNELS_PLACEHOLDER",
        channel_types=[
            discord.enums.ChannelType.voice, discord.enums.ChannelType.stage_voice, discord.enums.ChannelType.category
        ],
        min_values=0, max_values=25
    )
    async def untracked_channels_menu(self, selection: discord.Interaction, selected):
        await selection.response.defer()
        setting = self.instances[3]
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values
        await setting.write()

    async def untracked_channels_menu_refresh(self):
        t = self.bot.translator.t
        self.untracked_channels_menu.placeholder = t(_p(
            'ui:voice_tracker_config|menu:untracked_channels|placeholder',
            "Select Untracked Channels"
        ))

    async def make_message(self):
        t = self.bot.translator.t
        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        mode = lguild.guild_mode
        if mode.voice is VoiceMode.VOICE:
            title = t(_p(
                'ui:voice_tracker_config|mode:voice|embed|title',
                "Voice Tracker Configuration Panel"
            ))
        else:
            title = t(_p(
                'ui:voice_tracker_config|mode:study|embed|title',
                "Study Tracker Configuration Panel"
            ))
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title
        )
        for setting in self.instances:
            embed.add_field(**setting.embed_field, inline=False)

        args = MessageArgs(embed=embed)
        return args

    async def reload(self):
        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        if lguild.guild_mode.voice is VoiceMode.VOICE:
            hourly_reward = await self.settings.HourlyReward_Voice.get(self.guildid)
        else:
            hourly_reward = await self.settings.HourlyReward_Study.get(self.guildid)
        hourly_live_bonus = lguild.config.get('hourly_live_bonus')
        daily_voice_cap = lguild.config.get('daily_voice_cap')
        untracked_channels = await self.settings.UntrackedChannels.get(self.guildid)
        self.instances = (
            hourly_reward, hourly_live_bonus, daily_voice_cap, untracked_channels
        )

    async def refresh_components(self):
        await asyncio.gather(
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
            self.untracked_channels_menu_refresh(),
        )
        self._layout = [
            (self.untracked_channels_menu,),
            (self.edit_button, self.reset_button, self.close_button)
        ]


class VoiceTrackerDashboard(DashboardSection):
    section_name = _p(
        'dash:voice_tracker|title',
        "Voice Tracker Configuration ({commands[config voice_rewards]})"
    )
    _option_name = _p(
        "dash:voice_tracking|dropdown|placeholder",
        "Voice Activity Panel"
    )
    configui = VoiceTrackerConfigUI
    setting_classes = configui.setting_classes

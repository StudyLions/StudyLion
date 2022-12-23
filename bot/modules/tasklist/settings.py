from typing import Optional
import discord
from discord.ui.select import select, Select, SelectOption, ChannelSelect
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.text_input import TextInput, TextStyle

from settings import ListData, ModelData
from settings.setting_types import StringSetting, BoolSetting, ChannelListSetting, IntegerSetting
from settings.groups import SettingGroup

from meta import conf, LionBot
from utils.lib import tabulate
from utils.ui import LeoUI, FastModal, error_handler_for, ModalRetryUI
from core.data import CoreData
from babel.translator import ctx_translator

from . import babel
from .data import TasklistData

_p = babel._p


class TasklistSettings(SettingGroup):
    class task_reward(ModelData, IntegerSetting):
        """
        Guild configuration for the task completion economy award.

        Exposed via `/configure tasklist`, and the standard configuration interface.
        """
        setting_id = 'task_reward'

        _display_name = _p('guildset:task_reward', "task_reward")
        _desc = _p(
            'guildset:task_reward|desc',
            "Number of LionCoins given for each completed task."
        )
        _long_desc = _p(
            'guildset:task_reward|long_desc',
            "The number of coins members will be rewarded each time they complete a task on their tasklist."
        )
        _default = 50

        _model = CoreData.Guild
        _column = CoreData.Guild.task_reward.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:task_reward|response',
                "Members will now be rewarded {coin}**{amount}** for each completed task."
            )).format(coin=conf.emojis.coin, amount=self.data)

        @property
        def set_str(self):
            return '</configure tasklist:1038560947666694144>'

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            if data is not None:
                return "{coin}**{amount}** per task.".format(
                    coin=conf.emojis.coin,
                    amount=data
                )

    class task_reward_limit(ModelData, IntegerSetting):
        setting_id = 'task_reward_limit'

        _display_name = _p('guildset:task_reward_limit', "task_reward_limit")
        _desc = _p(
            'guildset:task_reward_limit|desc',
            "Maximum number of task rewards given per 24h."
        )
        _long_desc = _p(
            'guildset:task_reward_limit|long_desc',
            "Maximum number of times in each 24h period that members will be rewarded "
            "for completing a task."
        )
        _default = 10

        _model = CoreData.Guild
        _column = CoreData.Guild.task_reward_limit.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:task_reward_limit|response',
                "Members will now be rewarded for task completion at most **{amount}** times per 24h."
            )).format(amount=self.data)

        @property
        def set_str(self):
            return '</configure tasklist:1038560947666694144>'

        @classmethod
        def _format_data(cls, parent_id, data, **kwargs):
            if data is not None:
                return "`{number}` per 24 hours.".format(
                    number=data
                )

    class tasklist_channels(ListData, ChannelListSetting):
        setting_id = 'tasklist_channels'

        _display_name = _p('guildset:tasklist_channels', "tasklist_channels")
        _desc = _p(
            'guildset:tasklist_channels|desc',
            "Channels in which to allow the tasklist."
        )
        _long_desc = _p(
            'guildset:tasklist_channels|long_desc',
            "If set, members will only be able to open their tasklist in these channels.\n"
            "If a category is selected, this will allow all channels under that category."
        )
        _default = None

        _table_interface = TasklistData.channels
        _id_column = 'guildid'
        _data_column = 'channelid'
        _order_column = 'channelid'

        _cache = {}

        @property
        def set_str(self):
            return "Channel selector below."


class TasklistConfigUI(LeoUI):
    # TODO: Back option to globall guild config
    # TODO: Cohesive edit
    _listening = {}

    def __init__(self, bot: LionBot, settings: TasklistSettings, guildid: int, channelid: int,**kwargs):
        super().__init__(**kwargs)
        self.bot = bot
        self.settings = settings
        self.guildid = guildid
        self.channelid = channelid

        # Original interaction, used when the UI runs as an initial interaction response
        self._original: Optional[discord.Interaction] = None
        # UI message, used when UI run as a followup message
        self._message: Optional[discord.Message] = None

        self.task_reward = None
        self.task_reward_limit = None
        self.tasklist_channels = None

        self.embed: Optional[discord.Embed] = None

        self.set_labels()

    @property
    def instances(self):
        return (self.task_reward, self.task_reward_limit, self.tasklist_channels)

    @button(label='CLOSE_PLACEHOLDER')
    async def close_pressed(self, interaction: discord.Interaction, pressed):
        """
        Close the configuration UI.
        """
        try:
            if self._message:
                await self._message.delete()
                self._message = None
            elif self._original:
                await self._original.delete_original_response()
                self._original = None
        except discord.HTTPException:
            pass
        await self.close()

    @button(label='RESET_PLACEHOLDER')
    async def reset_pressed(self, interaction: discord.Interaction, pressed):
        """
        Reset the tasklist configuration.
        """
        await interaction.response.defer()

        self.task_reward.data = None
        await self.task_reward.write()
        self.task_reward_limit.data = None
        await self.task_reward_limit.write()
        self.tasklist_channels.data = None
        await self.tasklist_channels.write()

        await self.refresh()
        await self.redraw()

    @select(cls=ChannelSelect, placeholder="CHANNEL_SELECTOR_PLACEHOLDER", min_values=0, max_values=25)
    async def channels_selected(self, interaction: discord.Interaction, selected: Select):
        """
        Multi-channel selector to select the tasklist channels in the Guild.
        Allows any channel type.
        Selected category channels will apply to their children.
        """
        await interaction.response.defer()
        self.tasklist_channels.value = selected.values
        await self.tasklist_channels.write()
        await self.refresh()
        await self.redraw()

    async def cleanup(self):
        self._listening.pop(self.channelid, None)
        self.task_reward.deregister_callback(self.id)
        self.task_reward_limit.deregister_callback(self.id)
        try:
            if self._original is not None:
                await self._original.delete_original_response()
                self._original = None
            if self._message is not None:
                await self._message.delete()
                self._message = None
        except discord.HTTPException:
            pass

    async def run(self, interaction: discord.Interaction):
        if old := self._listening.get(self.channelid, None):
            await old.close()

        await self.refresh()

        if interaction.response.is_done():
            # Use followup
            self._message = await interaction.followup.send(embed=self.embed, view=self)
        else:
            # Use interaction response
            self._original = interaction
            await interaction.response.send_message(embed=self.embed, view=self)

        self.task_reward.register_callback(self.id)(self.reload)
        self.task_reward_limit.register_callback(self.id)(self.reload)
        self._listening[self.channelid] = self

    async def reload(self, *args, **kwargs):
        await self.refresh()
        await self.redraw()

    async def refresh(self):
        self.task_reward = await self.settings.task_reward.get(self.guildid)
        self.task_reward_limit = await self.settings.task_reward_limit.get(self.guildid)
        self.tasklist_channels = await self.settings.tasklist_channels.get(self.guildid)
        self._layout = [
            (self.channels_selected,),
            (self.reset_pressed, self.close_pressed)
        ]
        self.embed = await self.make_embed()

    def set_labels(self):
        t = self.bot.translator.t
        self.close_pressed.label = t(_p('ui:tasklist_config|button:close|label', "Close"))
        self.reset_pressed.label = t(_p('ui:tasklist_config|button:reset|label', "Reset"))
        self.channels_selected.placeholder = t(_p(
            'ui:tasklist_config|menu:channels|placeholder',
            "Set Tasklist Channels"
        ))

    async def redraw(self):
        try:
            if self._message:
                await self._message.edit(embed=self.embed, view=self)
            elif self._original:
                await self._original.edit_original_response(embed=self.embed, view=self)
        except discord.HTTPException:
            pass

    async def make_embed(self):
        t = self.bot.translator.t
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=t(_p(
                'ui:tasklist_config|embed|title',
                "Tasklist Configuration Panel"
            ))
        )
        for setting in self.instances:
            embed.add_field(**setting.embed_field, inline=False)
        return embed

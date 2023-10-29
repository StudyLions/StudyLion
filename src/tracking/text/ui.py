import asyncio

import discord
from discord.ui.select import select, Select, ChannelSelect
from discord.ui.button import button, Button, ButtonStyle

from meta import LionBot

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from .settings import TextTrackerSettings, TextTrackerGlobalSettings
from . import babel

_p = babel._p


class TextTrackerConfigUI(ConfigUI):
    setting_classes = (
        TextTrackerSettings.XPPerPeriod,
        TextTrackerSettings.WordXP,
        TextTrackerSettings.UntrackedTextChannels,
    )

    def __init__(self, bot: LionBot,
                 guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('TextTrackerCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    @select(
        cls=ChannelSelect,
        placeholder='UNTRACKED_CHANNELS_PLACEHOLDER',
        min_values=0, max_values=25
    )
    async def untracked_channels_menu(self, selection: discord.Interaction, selected):
        await selection.response.defer()
        setting = self.instances[2]
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values
        await setting.write()

    async def untracked_channels_menu_refresh(self):
        t = self.bot.translator.t
        self.untracked_channels_menu.placeholder = t(_p(
            'ui:text_tracker_config|menu:untracked_channels|placeholder',
            "Select Untracked Channels"
        ))

    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:text_tracker_config|embed|title',
            "Message Tracking Configuration Panel"
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
        xp_per_period = lguild.config.get(self.settings.XPPerPeriod.setting_id)
        wordxp = lguild.config.get(self.settings.WordXP.setting_id)
        untracked = await self.settings.UntrackedTextChannels.get(self.guildid)
        self.instances = (
            xp_per_period, wordxp, untracked
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


class TextTrackerDashboard(DashboardSection):
    section_name = _p(
        'dash:text_tracking|title',
        "Message XP configuration ({commands[config message_exp]})",
    )
    _option_name = _p(
        "dash:text_tracking|dropdown|placeholder",
        "Message XP Panel"
    )
    configui = TextTrackerConfigUI
    setting_classes = configui.setting_classes

import asyncio

import discord
from discord.ui.select import select, ChannelSelect

from meta import LionBot

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from .settings import TimerSettings
from . import babel

_p = babel._p


class TimerConfigUI(ConfigUI):
    setting_classes = (
        TimerSettings.PomodoroChannel,
    )

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('TimerCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    # ----- UI Components -----
    @select(cls=ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.voice],
            placeholder="CHANNEL_SELECT_PLACEHOLDER",
            min_values=0, max_values=1)
    async def channel_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        await selection.response.defer()
        setting = self.instances[0]
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()

    async def refresh_channel_menu(self):
        self.channel_menu.placeholder = self.bot.translator.t(_p(
            'ui:timer_config|menu:channels|placeholder',
            "Select Pomodoro Notification Channel"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:timer_config|embed|title',
            "Timer Configuration Panel"
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
        self.instances = (
            lguild.config.get(TimerSettings.PomodoroChannel.setting_id),
        )

    async def refresh_components(self):
        await asyncio.gather(
            self.refresh_channel_menu(),
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
        )
        self.set_layout(
            (self.channel_menu,),
            (self.edit_button, self.reset_button, self.close_button)
        )


class TimerDashboard(DashboardSection):
    section_name = _p(
        'dash:pomodoro|title',
        "Pomodoro Configuration ({commands[config pomodoro]})"
    )
    _option_name = _p(
        "dash:stats|dropdown|placeholder",
        "Pomodoro Timer Panel"
    )
    configui = TimerConfigUI
    setting_classes = TimerConfigUI.setting_classes

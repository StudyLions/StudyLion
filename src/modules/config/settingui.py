import asyncio

import discord
from discord.ui.select import select, ChannelSelect

from meta import LionBot

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from . import babel
from .settings import GeneralSettings


_p = babel._p


class GeneralSettingUI(ConfigUI):
    setting_classes = (
        GeneralSettings.Timezone,
        GeneralSettings.Eventlog,
    )

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('GeneralSettingsCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    # ----- UI Components -----
    # Event log
    @select(
        cls=ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.voice],
        placeholder='EVENT_LOG_PLACEHOLDER',
        min_values=0, max_values=1,
    )
    async def eventlog_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        """
        Single channel selector for the event log.
        """
        await selection.response.defer(thinking=True, ephemeral=True)

        setting = self.get_instance(GeneralSettings.Eventlog)

        value = selected.values[0] if selected.values else None
        if issue := (await setting.check_value(value)):
            raise UserInputError(issue)

        setting.value = value
        await setting.write()
        await selection.delete_original_response()

    async def eventlog_menu_refresh(self):
        menu = self.eventlog_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:general_config|menu:event_log|placeholder',
            "Select Event Log"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:general_config|embed:title',
            "General Configuration"
        ))
        embed = discord.Embed(
            title=title,
            colour=discord.Colour.orange()
        )
        for setting in self.instances:
            embed.add_field(**setting.embed_field, inline=False)

        return MessageArgs(embed=embed)

    async def reload(self):
        self.instances = [
            await setting.get(self.guildid)
            for setting in self.setting_classes
        ]
    
    async def refresh_components(self):
        to_refresh = (
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
            self.eventlog_menu_refresh(),
        )
        await asyncio.gather(*to_refresh)

        self.set_layout(
            (self.eventlog_menu,),
            (self.edit_button, self.reset_button, self.close_button,),
        )


class GeneralDashboard(DashboardSection):
    section_name = _p(
        "dash:general|title",
        "General Dashboard Settings ({commands[configure general]})"
    )
    _option_name = _p(
        "dash:general|option|name",
        "General Configuration Panel"
    )
    configui = GeneralSettingsUI
    setting_classes = configui.setting_classes

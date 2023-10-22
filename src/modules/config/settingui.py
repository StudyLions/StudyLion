import asyncio

import discord
from discord.ui.select import select, ChannelSelect

from meta import LionBot
from meta.errors import UserInputError

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from . import babel
from .settings import GeneralSettings


_p = babel._p


class GeneralSettingUI(ConfigUI):
    setting_classes = (
        GeneralSettings.Timezone,
        GeneralSettings.EventLog,
    )

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('GuildConfigCog').settings
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

        setting = self.get_instance(GeneralSettings.EventLog)
        await setting.interaction_check(setting.parent_id, selection)

        value = selected.values[0].resolve() if selected.values else None
        setting = await setting.from_value(self.guildid, value)
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
        "General Configuration ({commands[config general]})"
    )
    _option_name = _p(
        "dash:general|option|name",
        "General Configuration Panel"
    )
    configui = GeneralSettingUI
    setting_classes = configui.setting_classes

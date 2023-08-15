import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, ChannelSelect, RoleSelect

from meta import LionBot

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from . import babel
from .settings import ModerationSettings


_p = babel._p


class ModerationSettingUI(ConfigUI):
    setting_classes = (
        ModerationSettings.TicketLog,
        ModerationSettings.AlertChannel,
        ModerationSettings.ModRole,
    )

    def __init__(self, bot: LionBot, guildid: int, channelid, **kwargs):
        self.settings = bot.get_cog('ModerationCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    # ----- UI Components -----
    # Ticket Log selector
    @select(
        cls=ChannelSelect,
        placeholder="TICKET_LOG_MENU_PLACEHOLDER",
        min_values=0, max_values=1
    )
    async def ticket_log_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        """
        Single channel selector for the `ticket_log` setting.
        """
        await selection.response.defer(thinking=True, ephemeral=True)

        setting = self.get_instance(ModerationSettings.TicketLog)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()
        await selection.delete_original_response()
    
    async def ticket_log_menu_refresh(self):
        menu = self.ticket_log_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:moderation_config|menu:ticket_log|placeholder',
            "Select Ticket Log"
        ))

    # Alert Channel selector
    @select(
        cls=ChannelSelect,
        placeholder="ALERT_CHANNEL_MENU_PLACEHOLDER",
        min_values=0, max_values=1
    )
    async def alert_channel_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        """
        Single channel selector for the `alert_channel` setting.
        """
        await selection.response.defer(thinking=True, ephemeral=True)
        
        setting = self.get_instance(ModerationSettings.AlertChannel)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()
        await selection.delete_original_response()
    
    async def alert_channel_menu_refresh(self):
        menu = self.alert_channel_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:moderation_config|menu:alert_channel|placeholder',
            "Select Alert Channel"
        ))

    # Moderation Role Selector
    @select(
        cls=RoleSelect,
        placeholder="MODROLE_MENU_PLACEHOLDER",
        min_values=0, max_values=1
    )
    async def modrole_menu(self, selection: discord.Interaction, selected: RoleSelect):
        """
        Single role selector for the `moderation_role` setting.
        """
        await selection.response.defer(thinking=True, ephemeral=True)
        
        setting = self.get_instance(ModerationSettings.ModRole)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()
        await selection.delete_original_response()
    
    async def modrole_menu_refresh(self):
        menu = self.modrole_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:moderation_config|menu:modrole|placeholder',
            "Select Moderator Role"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:moderation_config|embed|title',
            "Moderation Configuration Panel"
        ))
        embed = discord.Embed(
            title=title,
            colour=discord.Colour.orange(),
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
        component_refresh = (
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
            self.ticket_log_menu_refresh(),
            self.alert_channel_menu_refresh(),
            self.modrole_menu_refresh(),
        )
        await asyncio.gather(*component_refresh)

        self.set_layout(
            (self.ticket_log_menu,),
            (self.alert_channel_menu,),
            (self.modrole_menu,),
            (self.edit_button, self.reset_button, self.close_button,)
        )


class ModerationDashboard(DashboardSection):
    section_name = _p(
        "dash:moderation|title",
        "Moderation Settings ({commands[configure moderation]})"
    )
    _option_name = _p(
        "dash:moderation|dropdown|placeholder",
        "Moderation Panel"
    )
    configui = ModerationSettingUI
    setting_classes = ModerationSettingUI.setting_classes

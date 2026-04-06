# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Configuration UI and dashboard section for screen
#          share enforcement (mirrors video_channels/settingui.py)
# ============================================================
import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, ChannelSelect, RoleSelect

from meta import LionBot
from wards import equippable_role

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from . import babel
from .settings import ScreenSettings


_p = babel._p


class ScreenSettingUI(ConfigUI):
    setting_classes = (
        ScreenSettings.ScreenChannels,
        ScreenSettings.ScreenExempt,
        ScreenSettings.ScreenGracePeriod,
        ScreenSettings.ScreenBlacklist,
        ScreenSettings.ScreenBlacklistDurations,
    )

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('ScreenCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    # ----- UI Components -----
    @select(
        cls=ChannelSelect,
        channel_types=[discord.ChannelType.voice, discord.ChannelType.category],
        placeholder="CHANNELS_MENU_PLACEHOLDER",
        min_values=0, max_values=25
    )
    async def channels_menu(self, selection: discord.Interaction, selected: RoleSelect):
        await selection.response.defer(thinking=True, ephemeral=True)

        setting = self.get_instance(ScreenSettings.ScreenChannels)
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values
        await setting.write()
        await selection.delete_original_response()

    async def channels_menu_refresh(self):
        menu = self.channels_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:screen_config|menu:channels|placeholder',
            "Select Screen Share Channels"
        ))

    @select(
        cls=RoleSelect,
        placeholder="EXEMPT_MENU_PLACEHOLDER",
        min_values=0, max_values=25
    )
    async def exempt_menu(self, selection: discord.Interaction, selected: RoleSelect):
        await selection.response.defer(thinking=True, ephemeral=True)

        setting = self.get_instance(ScreenSettings.ScreenExempt)
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values
        await setting.write()
        await selection.delete_original_response()

    async def exempt_menu_refresh(self):
        menu = self.exempt_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:screen_config|menu:exempt|placeholder',
            "Select Exempt Roles"
        ))

    @select(
        cls=RoleSelect,
        placeholder="SCREEN_BLACKLIST_MENU_PLACEHOLDER",
        min_values=0, max_values=1
    )
    async def screen_blacklist_menu(self, selection: discord.Interaction, selected: RoleSelect):
        await selection.response.defer(thinking=True, ephemeral=True)

        setting = self.get_instance(ScreenSettings.ScreenBlacklist)
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values[0] if selected.values else None
        if setting.value:
            await equippable_role(self.bot, setting.value, selection.user)
        await setting.write()
        await selection.delete_original_response()

    async def screen_blacklist_menu_refresh(self):
        menu = self.screen_blacklist_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:screen_config|menu:screen_blacklist|placeholder',
            "Select Blacklist Role"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
          'ui:screen_config|embed|title',
          "Screen Share Channel Configuration Panel"
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
        component_refresh = (
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
            self.channels_menu_refresh(),
            self.exempt_menu_refresh(),
            self.screen_blacklist_menu_refresh(),
        )
        await asyncio.gather(*component_refresh)

        self.set_layout(
            (self.channels_menu,),
            (self.exempt_menu,),
            (self.screen_blacklist_menu,),
            (self.edit_button, self.reset_button, self.close_button,),
        )


class ScreenDashboard(DashboardSection):
    section_name = _p(
        "dash:screen|title",
        "Screen Share Channel Settings ({commands[admin config screen_channels]})"
    )
    _option_name = _p(
        "dash:screen|option|name",
        "Screen Share Channel Panel"
    )
    configui = ScreenSettingUI
    setting_classes = ScreenSettingUI.setting_classes

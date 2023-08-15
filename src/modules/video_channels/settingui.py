import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, ChannelSelect, RoleSelect

from meta import LionBot
from wards import equippable_role

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from . import babel
from .settings import VideoSettings


_p = babel._p


class VideoSettingUI(ConfigUI):
    setting_classes = (
        VideoSettings.VideoChannels,
        VideoSettings.VideoExempt,
        VideoSettings.VideoGracePeriod,
        VideoSettings.VideoBlacklist,
        VideoSettings.VideoBlacklistDurations,
    )

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('VideoCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    # ----- UI Components -----
    # Video Channels channel selector
    @select(
        cls=ChannelSelect,
        channel_types=[discord.ChannelType.voice, discord.ChannelType.category],
        placeholder="CHANNELS_MENU_PLACEHOLDER",
        min_values=0, max_values=25
    )
    async def channels_menu(self, selection: discord.Interaction, selected: RoleSelect):
        """
        Multi-channel selector for the `video_channels` setting.
        """
        await selection.response.defer(thinking=True, ephemeral=True)

        setting = self.get_instance(VideoSettings.VideoChannels)
        setting.value = selected.values
        await setting.write()
        await selection.delete_original_response()
    
    async def channels_menu_refresh(self):
        menu = self.channels_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:video_config|menu:channels|placeholder',
            "Select Video Channels"
        ))

    # Video exempt role selector
    @select(
        cls=RoleSelect,
        placeholder="EXEMPT_MENU_PLACEHOLDER",
        min_values=0, max_values=25
    )
    async def exempt_menu(self, selection: discord.Interaction, selected: RoleSelect):
        """
        Multi-role selector for the `video_exempt` setting.
        """
        await selection.response.defer(thinking=True, ephemeral=True)

        setting = self.get_instance(VideoSettings.VideoExempt)
        setting.value = selected.values
        await setting.write()
        await selection.delete_original_response()
    
    async def exempt_menu_refresh(self):
        menu = self.exempt_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:video_config|menu:exempt|placeholder',
            "Select Exempt Roles"
        ))

    # Video blacklist role selector
    @select(
        cls=RoleSelect,
        placeholder="VIDEO_BLACKLIST_MENU_PLACEHOLDER",
        min_values=0, max_values=1
    )
    async def video_blacklist_menu(self, selection: discord.Interaction, selected: RoleSelect):
        """
        Single role selector for the `video_blacklist` setting.
        """
        await selection.response.defer(thinking=True, ephemeral=True)

        setting = self.get_instance(VideoSettings.VideoBlacklist)
        setting.value = selected.values[0] if selected.values else None
        if setting.value:
            await equippable_role(self.bot, setting.value, selection.user)
        await setting.write()
        await selection.delete_original_response()
    
    async def video_blacklist_menu_refresh(self):
        menu = self.video_blacklist_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:video_config|menu:video_blacklist|placeholder',
            "Select Blacklist Role"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
          'ui:video_config|embed|title',
          "Video Channel Configuration Panel"
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
            self.video_blacklist_menu_refresh(),
        )
        await asyncio.gather(*component_refresh)

        self.set_layout(
            (self.channels_menu,),
            (self.exempt_menu,),
            (self.video_blacklist_menu,),
            (self.edit_button, self.reset_button, self.close_button,),
        )


class VideoDashboard(DashboardSection):
    section_name = _p(
        "dash:video|title",
        "Video Channel Settings ({commands[configure video_channels]})"
    )
    _option_name = _p(
        "dash:video|option|name",
        "Video Channel Panel"
    )
    configui = VideoSettingUI
    setting_classes = VideoSettingUI.setting_classes

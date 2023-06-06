import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, ChannelSelect

from meta import LionBot

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from .settings import RoomSettings
from . import babel

_p = babel._p


class RoomSettingUI(ConfigUI):
    setting_classes = RoomSettings.model_settings

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('RoomCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    # ----- UI Components -----
    @select(cls=ChannelSelect, channel_types=[discord.ChannelType.category],
            min_values=0, max_values=1,
            placeholder='CATEGORY_PLACEHOLDER')
    async def category_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        await selection.response.defer()
        setting = self.instances[0]
        setting.value = selected.values[0] if selected.values else None
        await setting.write()

    async def category_menu_refresh(self):
        self.category_menu.placeholder = self.bot.translator.t(_p(
            'ui:room_config|menu:category|placeholder',
            "Select Private Room Category"
        ))

    @button(label="VISIBLE_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def visible_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        setting = next(inst for inst in self.instances if inst.setting_id == RoomSettings.Visible.setting_id)
        setting.value = not setting.value
        await setting.write()

    async def visible_button_refresh(self):
        button = self.visible_button
        button.label = self.bot.translator.t(_p(
            'ui:room_config|button:visible|label',
            "Toggle Room Visibility"
        ))
        setting = next(inst for inst in self.instances if inst.setting_id == RoomSettings.Visible.setting_id)
        button.style = ButtonStyle.green if setting.value else ButtonStyle.grey

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:rooms_config|embed|title',
            "Private Room System Configuration Panel"
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
        self.instances = tuple(
            lguild.config.get(setting.setting_id)
            for setting in self.settings.model_settings
        )

    async def refresh_components(self):
        await asyncio.gather(
            self.category_menu_refresh(),
            self.visible_button_refresh(),
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
        )
        self.set_layout(
            (self.category_menu,),
            (self.visible_button, self.edit_button, self.reset_button, self.close_button)
        )


class RoomDashboard(DashboardSection):
    section_name = _p(
        'dash:rooms|title',
        "Private Room Configuration ({commands[configure rooms]})"
    )
    configui = RoomSettingUI
    setting_classes = RoomSettingUI.setting_classes

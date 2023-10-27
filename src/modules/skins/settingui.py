import asyncio

import discord
from discord.ui.select import select, Select

from utils.ui import ConfigUI
from utils.lib import MessageArgs
from meta import LionBot

from . import babel, logger
from .settings import GlobalSkinSettings as Settings
from .skinlib import appskin_as_option

_p = babel._p


class GlobalSkinSettingUI(ConfigUI):
    setting_classes = (
        Settings.DefaultSkin,
    )

    def __init__(self, bot: LionBot, appname: str, channelid: int, **kwargs):
        self.cog = bot.get_cog('CustomSkinCog')
        super().__init__(bot, appname, channelid, **kwargs)

    # ----- UI Components -----
    @select(
        cls=Select,
        placeholder="DEFAULT_APP_MENU_PLACEHOLDER",
        min_values=0, max_values=1
    )
    async def default_app_menu(self, selection: discord.Interaction, selected: Select):
        await selection.response.defer(thinking=False)
        setting = self.instances[0]

        if selected.values:
            setting.data = selected.values[0]
            await setting.write()
        else:
            setting.data = None
            await setting.write()
    
    async def default_app_menu_refresh(self):
        menu = self.default_app_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:appskins|menu:default_app|placeholder',
            "Select Default Skin"
        ))
        options = []
        for skinid in self.cog.appskin_names:
            appskin = self.cog.get_base(skinid)
            option = appskin_as_option(appskin)
            option.default = (
                self.instances[0].value == appskin.skin_id
            )
            options.append(option)
        if options:
            menu.options = options
        else:
            menu.disabled = True
            menu.options = [
                discord.SelectOption(label='DUMMY')
            ]

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:appskins|embed|title',
            "Leo Global Skin Settings"
        ))
        embed = discord.Embed(
            title=title,
            colour=discord.Colour.orange()
        )
        for setting in self.instances:
            embed.add_field(**setting.embed_field, inline=False)

        return MessageArgs(embed=embed)

    async def refresh_components(self):
        to_refresh = (
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
            self.default_app_menu_refresh(),
        )
        await asyncio.gather(*to_refresh)

        self.set_layout(
            (self.edit_button, self.reset_button, self.close_button,),
            (self.default_app_menu,),
        )

    async def reload(self):
        self.instances = [
            await setting.get(self.bot.appname)
            for setting in self.setting_classes
        ]

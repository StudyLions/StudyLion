import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle

from meta import LionBot

from utils.ui import ConfigUI, MessageUI, DashboardSection
from utils.lib import MessageArgs

from .settings import LocaleSettings
from . import babel

_p = babel._p


class LocaleSettingUI(ConfigUI):
    setting_classes = [
        LocaleSettings.GuildLocale,
        LocaleSettings.ForceLocale,
    ]

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('BabelCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    # ----- UI Components -----
    @button(label="FORCE_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def force_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        setting = next(inst for inst in self.instances if inst.setting_id == LocaleSettings.ForceLocale.setting_id)
        await setting.interaction_check(self.guildid, press)
        setting.value = not setting.value
        await setting.write()

    async def force_button_refresh(self):
        button = self.force_button
        setting = next(inst for inst in self.instances if inst.setting_id == LocaleSettings.ForceLocale.setting_id)
        button.label = self.bot.translator.t(_p(
            'ui:locale_config|button:force|label',
            "Toggle Force"
        ))
        button.style = ButtonStyle.green if setting.value else ButtonStyle.grey

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:locale_config|embed|title',
            "Language Configuration Panel"
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
            for setting in self.setting_classes
        )

    async def refresh_components(self):
        await asyncio.gather(
            self.force_button_refresh(),
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
        )
        self.set_layout(
            (self.force_button, self.edit_button, self.reset_button, self.close_button)
        )


class LocaleDashboard(DashboardSection):
    section_name = _p(
        'dash:locale|title',
        "Server Language Configuration ({commands[config language]})"
    )
    _option_name = _p(
        "dash:locale|dropdown|placeholder",
        "Server Language Panel"
    )
    configui = LocaleSettingUI
    setting_classes = LocaleSettingUI.setting_classes

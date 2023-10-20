import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle

from meta import LionBot

from utils.ui import ConfigUI
from utils.lib import MessageArgs
from utils.ui.msgeditor import MsgEditor

from .settings import SponsorSettings as Settings
from . import babel, logger

_p = babel._p


class SponsorUI(ConfigUI):
    setting_classes = (
        Settings.SponsorPrompt,
        Settings.SponsorMessage,
        Settings.Whitelist,
    )

    def __init__(self, bot: LionBot, appname: str, channelid: int, **kwargs):
        self.settings = bot.get_cog('SponsorCog').settings
        super().__init__(bot, appname, channelid, **kwargs)

    # ----- UI Components -----
    @button(
        label="SPONSOR_PROMPT_BUTTON_PLACEHOLDER",
        style=ButtonStyle.blurple
    )
    async def sponsor_prompt_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        setting = self.get_instance(Settings.SponsorPrompt)

        value = setting.value
        if value is None:
            value = {'content': "Empty"}

        editor = MsgEditor(
            self.bot,
            value,
            callback=setting.editor_callback,
            callerid=press.user.id,
        )
        self._slaves.append(editor)
        await editor.run(press)
    
    async def sponsor_prompt_button_refresh(self):
        button = self.sponsor_prompt_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:sponsors|button:sponsor_prompt|label',
            "Sponsor Prompt"
        ))

    @button(
        label="SPONSOR_MESSAGE_BUTTON_PLACEHOLDER",
        style=ButtonStyle.blurple
    )
    async def sponsor_message_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        setting = self.get_instance(Settings.SponsorMessage)

        value = setting.value
        if value is None:
            value = {'content': "Empty"}

        editor = MsgEditor(
            self.bot,
            value,
            callback=setting.editor_callback,
            callerid=press.user.id,
        )
        self._slaves.append(editor)
        await editor.run(press)
    
    async def sponsor_message_button_refresh(self):
        button = self.sponsor_message_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:sponsors|button:sponsor_message|label',
            "Sponsor Message"
        ))
    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:sponsors|embed|title',
            "Leo Sponsor Panel"
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
            await setting.get(self.bot.appname)
            for setting in self.setting_classes
        ]

    async def refresh_components(self):
        to_refresh = (
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
            self.sponsor_message_button_refresh(),
            self.sponsor_prompt_button_refresh(),
        )
        await asyncio.gather(*to_refresh)

        self.set_layout(
            (self.sponsor_prompt_button, self.sponsor_message_button,
             self.edit_button, self.reset_button, self.close_button)
        )

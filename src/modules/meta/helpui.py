from typing import Optional
import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle

from meta import LionBot, conf
from utils.ui import MessageUI
from utils.lib import MessageArgs

from .help_sections import make_admin_page, make_member_page
from . import babel

_p = babel._p


class HelpUI(MessageUI):
    def __init__(self,
                 bot: LionBot,
                 caller: discord.User | discord.Member, guild: Optional[discord.Guild],
                 show_admin: bool = False,
                 **kwargs):
        self.bot = bot
        self.caller = caller
        self.guild = guild
        self.show_admin = show_admin

        kwargs.setdefault('callerid', caller.id)
        super().__init__(**kwargs)

        self.member_page = None
        self.admin_page = None

        # 0: Member page, 1: Admin page, 2: Super Admin page
        self.page = 0

    # ----- UI Components -----
    @button(label='MEMBER_PAGE_PLACEHOLDER', style=ButtonStyle.blurple)
    async def member_page_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        self.page = 0
        await self.redraw()

    async def member_page_button_refresh(self):
        self.member_page_button.label = self.bot.translator.t(_p(
            'ui:help|button:member_page|label',
            "Member Page"
        ))

    @button(label='ADMIN_PAGE_PLACEHOLDER', style=ButtonStyle.blurple)
    async def admin_page_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        self.page = 1
        await self.redraw()

    async def admin_page_button_refresh(self):
        self.admin_page_button.label = self.bot.translator.t(_p(
            'ui:help|button:admin_page|label',
            "Admin Page"
        ))

    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def close_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        await self.quit()

    async def close_button_refresh(self):
        pass

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        if self.page == 0:
            message = MessageArgs(embed=self.member_page)
        elif self.page == 1:
            message = MessageArgs(embed=self.admin_page)
        else:
            message = MessageArgs(embed=self.member_page)
        return message

    async def refresh_layout(self):
        if self.show_admin:
            await asyncio.gather(
                self.close_button_refresh(),
                self.member_page_button_refresh(),
                self.admin_page_button_refresh(),
            )
            switcher = self.member_page_button if self.page else self.admin_page_button
            self.set_layout(
                (switcher, self.close_button)
            )
        else:
            self.set_layout()

    async def reload(self):
        self.member_page = await make_member_page(self.bot, self.caller, self.guild)
        if self.show_admin:
            self.admin_page = await make_admin_page(self.bot, self.caller, self.guild)
        else:
            self.admin_page = None

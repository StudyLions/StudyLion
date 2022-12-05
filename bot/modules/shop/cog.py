import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from meta import LionBot, LionCog, LionContext

from utils import ui

from . import babel

from .shops.colours import ColourShop

logger = logging.getLogger(__name__)

_p = babel._p


class Shopping(LionCog):
    Shops = [ColourShop]

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = None
        self.shops = []

    async def cog_load(self):
        for Shop in self.Shops:
            shop = Shop(self.bot, self.data)
            await shop.load_into(self)
            self.shops.append(shop)

    async def cog_unload(self):
        for shop in self.shops:
            await shop.unload()

    @cmds.hybrid_group(name='editshop')
    async def editshop_group(self, ctx: LionContext):
        return

    @cmds.hybrid_group(name='shop')
    async def shop_group(self, ctx: LionContext):
        return

    @shop_group.command(name='open')
    async def shop_open_cmd(self, ctx: LionContext):
        """
        Opens the shop UI for the current guild.
        """
        ...


class StoreManager(ui.LeoUI):
    def __init__(self, bot, data, shops):
        self.bot = bot
        self.data = data
        self.shops = shops

        self.page_num = 0

        self._original: Optional[discord.Interaction] = None

        self._store_row = self.make_buttons()
        self._widgets = self.prepare_widgets()

    async def redraw(self):
        """
        Ask the current shop widget to redraw.
        """
        ...

    def make_buttons(self):
        """
        Make a tuple of shop buttons.

        If there is only one shop, return an empty tuple.
        """
        if len(self.shops) <= 1:
            return ()
        buttons = []
        for i, shop in enumerate(self.shops):
            @ui.AButton(label=shop.name)
            async def pressed_switch_shop(press: discord.Interaction, pressed):
                await press.response.defer()
                await self.change_page(i)
            buttons.append(pressed_switch_shop)
        return tuple(buttons)

    def prepare_widgets(self):
        widgets = []
        for shop in self.shops:
            widget = shop.make_widget()
            # TODO: Update this when we have a UILayout class
            # widget.layout.set_row('shops', self._store_row, affinity=1)
            widget.shop_row = self._store_row
            widgets.append(widget)
        return widgets

    async def change_page(self, i):
        """
        Change to the given page number.
        """
        ...

    async def run(self, interaction):
        ...

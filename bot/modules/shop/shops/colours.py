from typing import TYPE_CHECKING

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.ui.select import select, Select
from discord.ui.button import button, Button

from meta import LionCog, LionContext, LionBot
from utils import ui

from .data import ShopData

if TYPE_CHECKING:
    from ..cog import Shopping


class ColourShopping(LionCog):
    """
    Cog in charge of colour shopping.

    Registers colour shop related commands and methods.
    """

    def __init__(self, bot: LionBot, data):
        self.bot = bot
        self.data = data

    async def load_into(self, cog: 'Shopping'):
        self.crossload_group(self.editshop_group, cog.editshop_group)
        await cog.bot.add_cog(self)

    async def unload(self):
        pass

    @LionCog.placeholder_group
    @cmds.hybrid_group('editshopp', with_app_command=False)
    async def editshop_group(self, ctx: LionContext):
        pass

    @editshop_group.group('colours')
    async def editshop_colour_group(self, ctx: LionContext):
        ...

    @editshop_colour_group.command('edit')
    async def editshop_colours_edit_cmd(self, ctx: LionContext):
        await ctx.reply(f"I am a {self.__class__.__name__} version 2")
        ...

    def make_widget(self):
        """
        Instantiate and return a new UI for this shop.
        """
        return ColourStore(self.bot, self.data)

    def make_shop_for(self, member: discord.Member):
        return ColourShop(member, self.data)


class ColourShop:
    """
    A Shop representing a colour shop for a particular member.

    Parameters
    ----------
    bot: LionBot
        The current LionBot.

    member: discord.Member
        The member this particular shop is for.

    data: ShopData
        An initialised ShopData registry.
    """
    def __init__(self, bot, member, data):
        self.bot = bot
        self.user = member
        self.guild = member.guild
        self.data = data

        # List of items in this shop. Initialised in refresh()
        self.items = []

        # Current inventory for this member
        self.inventory = None

    def make_store(self):
        """
        Initialise and return a new Store UI for this shop.
        """
        return ColourStore(self)


class ColourStore:
    """
    Ephemeral UI providing access to the colour store.
    """

    def __init__(self, shop: ColourShop):
        self.bot = shop.bot
        self.data = shop.data
        self.shop = shop

        self.shop_row = ()

    async def refresh(self):
        """
        Refresh the data.
        """
        # Refresh current item list
        # Refresh user's current item
        ...

    async def redraw(self):
        ...

    @select(placeholder="Select to Buy")
    async def select_colour(self, interaction: discord.Interaction, selection: Select):
        # User selected a colour from the list
        # Run purchase pathway for that item
        ...

    async def select_colour_refresh(self):
        """
        Refresh the select colour menu.

        For an item to be purchasable,
        it needs to be affordable and not currently owned by the member.
        """
        ...

    def make_embed(self):
        """
        Embed for this shop.
        """
        lines = []
        for i, item in enumerate(self.shop.items):
            line = f"[{i+1}] | `{item.price} LC` | <@&{item.data.roleid}>"
            if item.itemid in self.shop.member_inventory.itemids:
                line += " (You own this!)"
        embed = discord.Embed(
            title="Colour Role Shop",
            description=""
        )
        ...



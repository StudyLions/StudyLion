"""
The initial Shopping Cog acts as the entry point to the shopping system.
It provides the commands:
    /shop open [type:<acmpl str>]
    /shop buy <item:<acmpl str>>
It also provides the "/editshop" group,
which each shop type should hook into (via placeholder groups)
to provide a shop creation and edit interface.

A "Shop" represents a colour shop, role shop, boost shop, etc.
Each Shop has a different editing interface (the ShopCog),
and a different user interface page (the Store).

When a user runs /shop open, the "StoreManager" opens.
This PagedUI serves as a top-level manager for each shop store,
even though it has no UI elements itself.

The user sees the first Store page, and can freely use the store UI
to interact with that Shop.
They may also use the "shop row" buttons to switch between shops.

Now, onto the individual shop systems.

When the user first opens a shop, a Customer is created.
The Customer represents the member themselves (i.e. the lion),
along with their inventory (a list of raw items that they own).
For fast access (for e.g. autocomplete), the Customer may be
cached, as long as it has a unique registry map.

Each initialised Shop has a collection of ShopItems.
The ShopItems represent individual objects of that shop,
and usually contain state particular to that shop.
The ShopItems shouldn't need to remember their origin shop,
or the Customer.

The Shop itself handles purchases, checking whether a customer can purchase
a given item, and running the purchase logic for an item.

Note: Timing out Acmpl state to handle caching shared states between acmpl?

Note: shop_item_info table which joins the others? Include guild_item_id,
and cache the items.

/shop open:
    - Create the Customer
    - Initialise the Shops, with the current Guild and the Customer
    - Pass the shop stores to the StoreManager, along with the command interaction
    - Run display on the StoreManager, which displays the first Store UI
        - The StoreManager gets a store button from each store, then passes those back to the individuals
        - This would be best done with a UILayout modification, but we don't have that yet
    - The Store displays its UI, which is Customer-dependent, relying on the Shop for most computations.
    - (The Store might not even need to keep the Customer, just using Shop methods to access them.)
    - The Customer may make a purchase/refund/etc, which gets mapped back to the Shop.
    - After the Customer has made an action, the Store refreshes its UI, from the Shop data.
/shop buy <item>:
    - Instantiates the Customer and Shops (via acmpl state?), which should _not_ require any data lookups.
    - Acmpl shows an intelligent list of matching items, nicely formatted
    - (Shopitem itself can be responsible for formatting?)
    - (Shop can be responsible for showing which items the user can purchase?)
    - Command gets the shopitemid (possibly partitioned by guild), gets that item, gets the item Shop.
    - Command then gets the Shop to purchase that item.
"""

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from meta import LionBot, LionCog, LionContext
from utils import ui
from utils.lib import error_embed

from . import babel

from .shops.base import Customer, ShopCog
from .data import ShopData

logger = logging.getLogger(__name__)

_p = babel._p


class Shopping(LionCog):
    # List of active Shop cogs
    ShopCogs = ShopCog.active

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(ShopData())
        self.active_cogs = []

    async def cog_load(self):
        await self.data.init()
        for SCog in self.ShopCogs:
            shop_cog = SCog(self.bot, self.data)
            await shop_cog.load_into(self)
            self.active_cogs.append(shop_cog)

    async def cog_unload(self):
        for shop in self.shops:
            await shop.unload()

    @cmds.hybrid_group(
        name=_p('group:editshop', 'editshop')
    )
    async def editshop_group(self, ctx: LionContext):
        return

    @cmds.hybrid_group(
        name=_p('group:shop', 'shop')
    )
    async def shop_group(self, ctx: LionContext):
        return

    @shop_group.command(
        name=_p('cmd:shop_open', 'open'),
        description=_p('cmd:shop_open|desc', "Open the server shop.")
    )
    async def shop_open_cmd(self, ctx: LionContext):
        """
        Opens the shop UI for the current guild.
        """
        t = self.bot.translator.t

        # Typechecker guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(ephemeral=True, thinking=True)

        # Create the Customer
        customer = await Customer.fetch(self.bot, self.data, ctx.guild.id, ctx.author.id)

        # Create the Shops
        shops = [await cog.make_shop_for(customer) for cog in self.active_cogs]

        # TODO: Filter by shops which actually have items
        if not shops:
            await ctx.reply(
                embed=error_embed(
                    t(_p('cmd:shop_open|error:no_shops', "There is nothing to buy!"))
                ),
                ephemeral=True
            )
            return

        # Extract the Stores
        stores = [shop.make_store(ctx.interaction) for shop in shops]

        # Build the StoreManager from the Stores
        manager = StoreManager(self.bot, self.data, stores)

        # Display the StoreManager
        await manager.run(ctx.interaction)

        await manager.wait()

    # TODO: shortcut shop buy command


class StoreManager(ui.LeoUI):
    def __init__(self, bot, data, stores, **kwargs):
        super().__init__(**kwargs)

        self.bot = bot
        self.data = data
        self.stores = stores

        self.page_num = 0

        # Original interaction that opened this shop
        self._original: Optional[discord.Interaction] = None

        # tuple of Buttons to each active store
        self._store_row = self.make_buttons()

    async def redraw(self):
        """
        Ask the current shop widget to redraw.
        """
        self.page_num %= len(self.stores)
        await self.stores[self.page_num].refresh()
        await self.stores[self.page_num].redraw()

    def make_buttons(self):
        """
        Make a tuple of shop buttons.

        If there is only one shop, returns an empty tuple.
        """
        t = self.bot.translator.t

        buttons = []
        if len(self.stores) > 1:
            for i, store in enumerate(self.stores):
                @ui.AButton(label=store.shop.name)
                async def pressed_switch_shop(press: discord.Interaction, pressed):
                    await press.response.defer()
                    await self.change_page(i)
                buttons.append(pressed_switch_shop)

        @ui.AButton(
            label=t(_p('ui:stores|button:close|label', "Close")),
            emoji=self.bot.config.emojis.getemoji('cancel')
        )
        async def pressed_close(press: discord.Interaction, pressed):
            await press.response.defer()
            if not self._original.is_expired():
                embed = discord.Embed(
                    title=t(_p('ui:stores|button:close|response|title', "Shop Closed")),
                    colour=discord.Colour.orange()
                )
                await self._original.edit_original_response(embed=embed, view=None)
            await self.close()
        buttons.append(pressed_close)
        for button in buttons:
            self.add_item(button)
        return tuple(buttons)

    async def change_page(self, i):
        """
        Change to the given page number.
        """
        self.page_num = i
        self.page_num %= len(self.stores)
        await self.redraw()

    async def run(self, interaction):
        self._original = interaction
        for store in self.stores:
            self.children.append(store)
            store.set_store_row(self._store_row)
        await self.redraw()

    async def monitor(self):
        """
        When one of the stores closes, we want all the stores to close,
        along with this parent UI.
        """
        # TODO
        ...

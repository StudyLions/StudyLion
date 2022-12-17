from typing import Type, TYPE_CHECKING
from weakref import WeakValueDictionary

import discord
from discord.ui.button import Button

from meta import LionBot, LionCog
from utils import ui
from babel.translator import LazyStr

from ..data import ShopData

if TYPE_CHECKING:
  from core.lion import Lion


class ShopCog(LionCog):
    """
    Minimal base class for a ShopCog.
    """
    _shop_cls_: Type['Shop']

    active: list[Type['ShopCog']] = []

    def __init__(self, bot: LionBot, data: ShopData):
        self.bot = bot
        self.data = data

    async def load_into(self, cog: LionCog):
        """
        Load this ShopCog into the parent Shopping Cog.

        Usually just attaches the editshop placeholder group, if applicable.
        May also load the cog itself into the client,
        if the ShopCog needs to provide global features
        or commands.
        """
        raise NotImplementedError

    async def make_shop_for(self, customer: 'Customer'):
        """
        Make a Shop instance for the provided Customer.
        """
        shop = self._shop_cls_(self.bot, self.data, customer)
        await shop.refresh()
        return shop

    @classmethod
    def register(self, shop):
        """
        Helper decorator to register a given ShopCog as active.
        """
        self.active.append(shop)
        return shop


class Customer:
    """
    An interface to the member's inventory.
    """

    _cache_ = WeakValueDictionary()

    def __init__(self, bot: LionBot, shop_data: ShopData, lion, inventory: ShopData.MemberInventory):
        self.bot = bot
        self.data = shop_data

        self.lion: 'Lion' = lion

        # A list of InventoryItems held by this customer
        self.inventory = inventory

    @property
    def guildid(self):
        return self.lion.guildid

    @property
    def userid(self):
        return self.lion.userid

    @property
    def balance(self):
      return self.lion.data['coins']

    @classmethod
    async def fetch(cls, bot: LionBot, shop_data: ShopData, guildid: int, userid: int):
        lion = await bot.core.lions.fetch(guildid, userid)
        inventory = await shop_data.MemberInventoryInfo.fetch_inventory_info(guildid, userid)
        return cls(bot, shop_data, lion, inventory)

    async def refresh(self):
        """
        Refresh the data for this member.
        """
        self.lion = await self.bot.core.lions.fetch(self.guildid, self.userid)
        await self.lion.data.refresh()
        self.inventory = await self.data.MemberInventoryInfo.fetch_inventory_info(self.guildid, self.userid)
        return self


class ShopItem:
    """
    Base class representing a purchasable guild shop item.

    In its most basic form, this is just a direct interface to the data,
    with some formatting methods.
    """
    def __init__(self, bot: LionBot, data: ShopData.ShopItemInfo):
        self.bot = bot
        self.data = data


class Shop:
    """
    Base class representing a Shop for a particular Customer.
    """
    # The name of this shop class, as a lazystring
    _name_: LazyStr

    # Store class describing the shop UI.
    _store_cls_: Type['Store']

    def __init__(self, bot: LionBot, shop_data: ShopData, customer: Customer):
        self.bot = bot
        self.data = shop_data
        self.customer = customer

        # A map itemid: ShopItem of items viewable by the customer
        self.items = {}

    def purchasable(self):
        """
        Retrieve a list of items purchasable by the customer.
        """
        raise NotImplementedError

    async def refresh(self):
        """
        Refresh the shop and customer data.
        """
        raise NotImplementedError

    @property
    def name(self):
        """
        The localised name of this shop.

        Usually just a context-aware translated version of cls._name_
        """
        t = self.bot.translator.t
        return t(self._name_)

    async def purchase(self, itemid):
        """
        Have the shop customer purchase the given (global) itemid.
        Checks that the item is actually purchasable by the customer.
        This method must be overridden in base classes.
        """
        raise NotImplementedError

    def make_store(self):
        """
        Initialise and return a new Store UI for this shop.
        """
        return self._store_cls_(self)


class Store(ui.LeoUI):
    """
    ABC for the UI used to interact with a given shop.

    This must always be an ephemeral UI,
    so extra permission checks are not required.
    (Note that each Shop instance is specific to a single customer.)
    """
    def __init__(self, shop: Shop, interaction: discord.Interaction, **kwargs):
      super().__init__(**kwargs)

      # The shop this Store is an interface for
      # Client, shop, and customer data is taken from here
      # The Shop also manages most Customer object interaction, including purchases.
      self.shop = shop

      # The row of Buttons used to access different shops, if any
      # Transient, will be deprecated by direct access to UILayout.
      self.store_row = ()

      # Current embed page
      self.embed: Optional[discord.Embed] = None

      # Current interaction to use
      self.interaction: discord.Interaction = interaction

    def set_store_row(self, row):
      self.store_row = row
      for item in row:
        self.add_item(item)

    async def refresh(self):
        """
        Refresh all UI elements.
        """
        raise NotImplementedError

    async def redraw(self):
        """
        Redraw the store UI.
        """
        if self.interaction.is_expired():
          # This is actually possible,
          # If the user keeps using the UI,
          # but never closes it until the origin interaction expires
          raise ValueError("This interaction has expired!")
          return

        if self.embed is None:
          await self.refresh()

        await self.interaction.edit_original_response(embed=self.embed, view=self)

    async def make_embed(self):
        """
        Embed page for this shop.
        """
        raise NotImplementedError

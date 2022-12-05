import discord
from discord.ui.button import Button

from meta import LionBot

from utils import ui

from ..data import ShopData


class MemberInventory:
    """
    An interface to the member's inventory.
    """
    def __init__(self, bot, shop_data, lion, inventory):
        self.bot = bot
        self.lion = lion
        self.guildid = lion.guildid
        self.userid = lion.userid

        # A list of InventoryItems held by this user
        self.inventory = inventory

    @classmethod
    async def fetch(cls, bot: LionBot, shop_data: ShopData, guildid: int, userid: int):
        lion = await bot.core.lions.fetch(guildid, userid)
        inventory = await shop_data.fetch_where(guildid=guildid, userid=userid)
        return cls(bot, shop_data, lion, inventory)

    async def refresh(self):
        """
        Refresh the data for this member.
        """
        self.lion = self.bot.core.lions.fetch(self.guild.id, self.user.id)

        data = self.bot.get_cog('Shopping').data
        self.inventory_items = await data.InventoryItem.fetch_where(userid=self.userid, guildid=self.guildid)


class ShopItem:
    """
    ABC representing a purchasable guild shop item.
    """
    def __init__(self, data):
        self.data = data

    async def purchase(self, userid):
        """
        Called when a member purchases this item.
        """
        ...


class Shop:
    """
    Base class representing a Shop for a particular member.
    """
    def __init__(self, bot: LionBot, shop_data: ShopData, member: discord.Member):
        self.bot = bot
        self.data = shop_data
        self.member = member
        self.guild = member.guild

        # A list of ShopItems that are currently visible to the member
        self.items = []

        # Current inventory for the member
        self.inventory = None

    async def refresh(self):
        ...


class Store(ui.LeoUI):
    """
    Base UI for the different shops.
    """
    def __init__(self, bot: LionBot, data, shops):
        self.bot = bot
        self.data = data
        self.shops = shops

import discord
import datetime
from typing import List

from meta import client
from utils.lib import FieldEnum
from data import Row
from settings import GuildSettings

from .data import shop_items, shop_item_info


class ShopItemType(FieldEnum):
    COLOUR_ROLE = 'COLOUR_ROLE', 'Colour'


class ShopItem:
    """
    Abstract base class representing an item in a guild shop.
    """
    __slots__ = ('itemid', '_guild')

    # Mapping of item types to class handlers
    _item_classes = {}  # ShopItemType -> ShopItem subclass

    # Item type handled by the current subclass
    item_type = None  # type: ShopItemType

    # Format string to use for each item of this type in the shop embed
    shop_fmt = "`[{num:<{num_len}}]` | `{item.price:<{price_len}}` {item.display_name}"

    # Shop input modifiers
    allow_multi_select = True
    buy_hint = None

    def __init__(self, itemid, *args, **kwargs):
        self.itemid = itemid  # itemid in shop_items representing this info
        self._guild = None  # cached Guild

    # Meta
    @classmethod
    def register_item_class(cls, itemcls):
        """
        Decorator to register a class as a handler for a given item type.
        The item type must be set as the `item_type` class attribute.
        """
        cls._item_classes[itemcls.item_type] = itemcls
        return itemcls

    @classmethod
    async def create(cls, guildid, price, *args, **kwargs):
        """
        Create a new ShopItem of this type.
        Must be implemented by each item class.
        """
        raise NotImplementedError

    @classmethod
    def fetch_where(cls, **kwargs):
        """
        Fetch ShopItems matching the given conditions.
        Automatically filters by `item_type` if set in class, and not provided.
        """
        if cls.item_type is not None and 'item_type' not in kwargs:
            kwargs['item_type'] = cls.item_type
        rows = shop_item_info.fetch_rows_where(**kwargs)
        return [
            cls._item_classes[ShopItemType(row.item_type)](row.itemid)
            for row in rows
        ]

    @classmethod
    def fetch(cls, itemid):
        """
        Fetch a single ShopItem by itemid.
        """
        row = shop_item_info.fetch(itemid)
        if row:
            return cls._item_classes[ShopItemType(row.item_type)](row.itemid)
        else:
            return None

    # Data and transparent data properties
    @property
    def data(self) -> Row:
        """
        Return the cached data row for this item.
        This is not guaranteed to be up to date.
        This is also not guaranteed to keep existing during a session.
        """
        return shop_item_info.fetch(self.itemid)

    @property
    def guildid(self) -> int:
        return self.data.guildid

    @property
    def price(self) -> int:
        return self.data.price

    @property
    def purchasable(self) -> bool:
        return self.data.purchasable

    # Computed properties
    @property
    def guild(self) -> discord.Guild:
        if not self._guild:
            self._guild = client.get_guild(self.guildid)
        return self._guild

    @property
    def guild_settings(self) -> GuildSettings:
        return GuildSettings(self.guildid)

    # Display properties
    @property
    def display_name(self) -> str:
        """
        Short name to display after purchasing the item, and by default in the shop.
        """
        raise NotImplementedError

    # Data manipulation methods
    def refresh(self) -> Row:
        """
        Refresh the stored data row.
        """
        shop_item_info.row_cache.pop(self.itemid, None)
        return self.data

    def _update(self, **kwargs):
        """
        Updates the data with the provided kwargs.
        Subclasses are expected to override this is they provide their own updatable data.

        This method does *not* refresh the data row. This is expect to be handled by `update`.
        """
        handled = ('price', 'purchasable')

        update = {key: kwargs[key] for key in handled}
        if update:
            shop_items.update_where(
                update,
                itemid=self.itemid
            )

    async def update(self, **kwargs):
        """
        Update the shop item with the given kwargs.
        """
        self._update()
        self.refresh()

    # Formatting
    @classmethod
    def _cat_embed_items(cls, items: List['ShopItem'], blocksize: int = 20,
                         fmt: str = shop_fmt, **kwargs) -> List[discord.Embed]:
        """
        Build a list of embeds for the current item type from a list of items.
        These embeds may be used anywhere multiple items may be shown,
        including confirmations and shop pages.
        Subclasses may extend or override.
        """
        embeds = []
        if items:
            # Cut into blocks
            item_blocks = [items[i:i+blocksize] for i in range(0, len(items), blocksize)]
            for i, item_block in enumerate(item_blocks):
                # Compute lengths
                num_len = len(str((i * blocksize + len(item_block) - 1)))
                max_price = max(item.price for item in item_block)
                price_len = len(str(max_price))

                # Format items
                string_block = '\n'.join(
                    fmt.format(
                        item=item,
                        num=i * blocksize + j,
                        num_len=num_len,
                        price_len=price_len
                    ) for j, item in enumerate(item_block)
                )

                # Build embed
                embed = discord.Embed(
                    description=string_block,
                    timestamp=datetime.datetime.utcnow()
                )
                if len(item_blocks) > 1:
                    embed.set_footer(text="Page {}/{}".format(i+1, len(item_blocks)))

                embeds.append(embed)
        else:
            # Empty shop case, should generally be avoided
            embed = discord.Embed(
                description="Nothing to show!"
            )
            embeds.append(embed)

        return embeds

    # Shop interface
    @classmethod
    def _cat_shop_embed_items(cls, items: List['ShopItem'], **kwargs) -> List[discord.Embed]:
        """
        Embed a list of items specifically for displaying in the shop.
        Subclasses will usually extend or override this, if only to add metadata.
        """
        if items:
            # TODO: prefix = items[0].guild_settings.prefix.value
            prefix = client.prefix

            embeds = cls._cat_embed_items(items, **kwargs)
            for embed in embeds:
                embed.title = "{} shop!".format(cls.item_type.desc)
                embed.description = "{}\n\n{}".format(
                    embed.description,
                    "Buy items with `{prefix}buy <numbers>`, e.g. `{prefix}buy 1, 2, 3`.".format(
                        prefix=prefix
                    )
                )
        else:
            embed = discord.Embed(
                title="{} shop!".format(cls.item_type.desc),
                description="This shop is empty! Please come back later."
            )
            embeds = [embed]
        return embeds

    @classmethod
    def cat_shop_embeds(cls, guildid: int, itemids: List[int] = None, **kwargs) -> List[discord.Embed]:
        """
        Format the items of this type (i.e. this category) as one or more embeds.
        Subclasses may extend or override.
        """
        if itemids is None:
            # Get itemids if not provided
            # TODO: Not using the row cache here, make sure we don't need an extended caching form
            rows = shop_item_info.fetch_rows_where(
                guildid=guildid,
                item_type=cls.item_type,
                purchasable=True,
                deleted=False
            )
            itemids = [row.itemid for row in rows]
        elif not all(itemid in shop_item_info.row_cache for itemid in itemids):
            # Ensure cache is populated
            shop_item_info.fetch_rows_where(itemid=itemids)

        return cls._cat_shop_embed_items([cls(itemid) for itemid in itemids])

    async def buy(self, ctx):
        """
        Action to trigger when a member buys this item.
        """
        raise NotImplementedError

    # Shop admin interface
    @classmethod
    async def parse_new(self, ctx):
        """
        Parse new shop items.
        """
        raise NotImplementedError

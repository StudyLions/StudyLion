from enums import Enum
from cachetools import TTLCache


from data import Registry, RowModel, RegisterEnum, WeakCache
from data.columns import Integer, String, Bool, Timestamp, Column


class ShopItemType(Enum):
    """
    Schema
    ------
    CREATE TYPE ShopItemType AS ENUM (
        'COLOUR_ROLE'
    );
    """
    COLOUR = 'COLOUR_ROLE',


class ShopData(Registry, name='shop'):
    _ShopItemType = RegisterEnum(ShopItemType)

    class ShopItem(RowModel):
        """
        Schema
        ------
        CREATE TABLE shop_items(
            itemid SERIAL PRIMARY KEY,
            guildid BIGINT NOT NULL,
            item_type ShopItemType NOT NULL,
            price INTEGER NOT NULL,
            purchasable BOOLEAN DEFAULT TRUE,
            deleted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT (now() at time zone 'utc')
        );
        CREATE INDEX guild_shop_items ON shop_items (guildid);
        """
        _tablename_ = 'shop_items'

        itemid = Integer(primary=True)
        guildid = Integer()
        item_type: Column[ShopItemType] = Column()
        price = Integer()
        purchasable = Bool()
        deleted = Bool()
        created_at = Timestamp()

    class ColourRole(RowModel):
        """
        Schema
        ------
        CREATE TABLE shop_items_colour_roles(
            itemid INTEGER PRIMARY KEY REFERENCES shop_items(itemid) ON DELETE CASCADE,
            roleid BIGINT NOT NULL
        );
        """
        _tablename_ = 'shop_items_colour_roles'

        itemid = Integer(primary=True)
        roleid = Integer()

    class MemberInventory(RowModel):
        """
        Schema
        ------
        CREATE TABLE member_inventory(
            inventoryid SERIAL PRIMARY KEY,
            guildid BIGINT NOT NULL,
            userid BIGINT NOT NULL,
            transactionid INTEGER REFERENCES coin_transactions(transactionid) ON DELETE SET NULL,
            itemid INTEGER NOT NULL REFERENCES shop_items(itemid) ON DELETE CASCADE
        );
        CREATE INDEX member_inventory_members ON member_inventory(guildid, userid);
        """
        _tablename_ = 'member_inventory'

        inventoryid = Integer(primary=True)
        guildid = Integer()
        userid = Integer()
        transactionid = Integer()
        itemid = Integer()

        async def fetch_inventory(self, guildid, userid) -> list['ShopData.MemberInventory']:
            """
            Fetch the given member's inventory.
            """
            return await self.fetch_where(guildid=guildid, userid=userid)

from enum import Enum
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

    class ShopItemInfo(RowModel):
        """
        A view joining the shop item sub-type information,
        and including the guild id.

        Schema
        ------
        CREATE VIEW shop_item_info AS
          SELECT
            *,
            row_number() OVER (PARTITION BY guildid ORDER BY itemid) AS guild_itemid
          FROM
            shop_items
          LEFT JOIN shop_items_colour_roles USING (itemid)
          ORDER BY itemid ASC;
        """
        _tablename_ = 'shop_item_info'
        _readonly_ = True

        itemid = Integer(primary=True)
        guild_itemid = Integer()
        guildid = Integer()
        item_type: Column[ShopItemType] = Column()
        price = Integer()
        purchasable = Bool()
        deleted = Bool()
        created_at = Timestamp()
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

    class MemberInventoryInfo(RowModel):
        """
        Composite view joining the member inventory with shop item information.

        Schema
        ------
        CREATE VIEW member_inventory_info AS
          SELECT
            inv.inventoryid AS inventoryid,
            inv.guildid AS guildid,
            inv.userid AS userid,
            inv.transactionid AS transactionid,
            items.itemid AS itemid,
            items.item_type AS item_type,
            items.price AS price,
            items.purchasable AS purchasable,
            items.deleted AS deleted
          FROM
            member_inventory inv
          LEFT JOIN shop_item_info items USING (itemid)
          ORDER BY itemid ASC;
        """
        _tablename_ = 'member_inventory_info'
        _readonly_ = True

        inventoryid = Integer(primary=True)
        guildid = Integer()
        userid = Integer()
        transactionid = Integer()
        itemid = Integer()
        guild_itemid = Integer()
        item_type: Column[ShopItemType] = Column()
        price = Integer()
        purchasable = Bool()
        deleted = Bool()
        roleid = Integer()

        @classmethod
        async def fetch_inventory_info(cls, guildid, userid) -> list['ShopData.MemberInventoryInfo']:
            """
            Fetch the information rows for the given members inventory.
            """
            return await cls.fetch_where(guildid=guildid, userid=userid)

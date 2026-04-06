# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-15
# Purpose: LionGotchi database models and registry
# ============================================================
from enum import Enum

from data import Registry, RowModel, RegisterEnum, Table
from data.columns import Integer, String, Bool, Timestamp, Column


class LGGoldTransactionType(Enum):
    """
    Schema
    ------
    CREATE TYPE LGGoldTransactionType AS ENUM (
      'VOICE_ACTIVITY', 'TEXT_ACTIVITY', 'LEVEL_UP',
      'SHOP_PURCHASE', 'FARM_HARVEST', 'ITEM_DROP', 'TRADE', 'ADMIN',
      'FARM_PLANT', 'FARM_UPROOT', 'MARKETPLACE_SALE', 'MARKETPLACE_PURCHASE',
      'GIFT'
    );
    """
    VOICE_ACTIVITY = 'VOICE_ACTIVITY'
    TEXT_ACTIVITY = 'TEXT_ACTIVITY'
    LEVEL_UP = 'LEVEL_UP'
    SHOP_PURCHASE = 'SHOP_PURCHASE'
    FARM_HARVEST = 'FARM_HARVEST'
    ITEM_DROP = 'ITEM_DROP'
    TRADE = 'TRADE'
    ADMIN = 'ADMIN'
    # --- AI-MODIFIED (2026-03-21) ---
    # Purpose: Add missing farm and marketplace transaction types to match DB enum
    FARM_PLANT = 'FARM_PLANT'
    FARM_UPROOT = 'FARM_UPROOT'
    MARKETPLACE_SALE = 'MARKETPLACE_SALE'
    MARKETPLACE_PURCHASE = 'MARKETPLACE_PURCHASE'
    # --- END AI-MODIFIED ---
    # --- AI-MODIFIED (2026-04-03) ---
    # Purpose: Add GIFT type used by website friend gifting (lg_gold_transactions)
    GIFT = 'GIFT'
    # --- END AI-MODIFIED ---


class LGEquipmentSlot(Enum):
    """
    Schema
    ------
    CREATE TYPE LGEquipmentSlot AS ENUM ('HEAD','FACE','BODY','BACK','FEET');
    """
    HEAD = 'HEAD'
    FACE = 'FACE'
    BODY = 'BODY'
    BACK = 'BACK'
    FEET = 'FEET'


class LGRarity(Enum):
    """
    Schema
    ------
    CREATE TYPE LGRarity AS ENUM (
      'COMMON','UNCOMMON','RARE','EPIC','LEGENDARY','MYTHICAL'
    );
    """
    COMMON = 'COMMON'
    UNCOMMON = 'UNCOMMON'
    RARE = 'RARE'
    EPIC = 'EPIC'
    LEGENDARY = 'LEGENDARY'
    MYTHICAL = 'MYTHICAL'


class LGItemCategory(Enum):
    """
    Schema
    ------
    CREATE TYPE LGItemCategory AS ENUM (
      'HAT','GLASSES','COSTUME','SHIRT','WINGS','BOOTS',
      'FURNITURE','ROOM','GAMEBOY_SKIN','FARM_SEED','CONSUMABLE',
      'MATERIAL','SCROLL'
    );
    """
    HAT = 'HAT'
    GLASSES = 'GLASSES'
    COSTUME = 'COSTUME'
    SHIRT = 'SHIRT'
    WINGS = 'WINGS'
    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: BOOTS split from COSTUME for FEET-slot items; MATERIAL/SCROLL for crafting
    BOOTS = 'BOOTS'
    FURNITURE = 'FURNITURE'
    ROOM = 'ROOM'
    GAMEBOY_SKIN = 'GAMEBOY_SKIN'
    FARM_SEED = 'FARM_SEED'
    CONSUMABLE = 'CONSUMABLE'
    MATERIAL = 'MATERIAL'
    SCROLL = 'SCROLL'
    # --- END AI-MODIFIED ---


class LGItemSource(Enum):
    """
    Schema
    ------
    CREATE TYPE LGItemSource AS ENUM (
      'SHOP','DROP','LEVEL_REWARD','FARM_HARVEST','TRADE','ADMIN','TUTORIAL','CRAFT'
    );
    """
    SHOP = 'SHOP'
    DROP = 'DROP'
    LEVEL_REWARD = 'LEVEL_REWARD'
    FARM_HARVEST = 'FARM_HARVEST'
    TRADE = 'TRADE'
    ADMIN = 'ADMIN'
    TUTORIAL = 'TUTORIAL'
    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: New source for crafted items
    CRAFT = 'CRAFT'
    # --- END AI-MODIFIED ---


class LGFurnitureSlot(Enum):
    """
    Schema
    ------
    CREATE TYPE LGFurnitureSlot AS ENUM (
      'WALL','FLOOR','CARPET','BED','CHAIR','DESK','LAMP'
    );
    """
    WALL = 'WALL'
    FLOOR = 'FLOOR'
    CARPET = 'CARPET'
    BED = 'BED'
    CHAIR = 'CHAIR'
    DESK = 'DESK'
    LAMP = 'LAMP'


class LGExpression(Enum):
    """
    Schema
    ------
    CREATE TYPE LGExpression AS ENUM (
      'DEFAULT','HAPPY','SAD','EATING','SICK','SLEEPING'
    );
    """
    DEFAULT = 'DEFAULT'
    HAPPY = 'HAPPY'
    SAD = 'SAD'
    EATING = 'EATING'
    SICK = 'SICK'
    SLEEPING = 'SLEEPING'


class LionGotchiData(Registry, name='liongotchi'):
    _LGGoldTransactionType = RegisterEnum(LGGoldTransactionType, 'LGGoldTransactionType')
    _LGEquipmentSlot = RegisterEnum(LGEquipmentSlot, 'LGEquipmentSlot')
    _LGRarity = RegisterEnum(LGRarity, 'LGRarity')
    _LGItemCategory = RegisterEnum(LGItemCategory, 'LGItemCategory')
    _LGItemSource = RegisterEnum(LGItemSource, 'LGItemSource')
    _LGFurnitureSlot = RegisterEnum(LGFurnitureSlot, 'LGFurnitureSlot')
    _LGExpression = RegisterEnum(LGExpression, 'LGExpression')

    class Pet(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_pets (
          userid BIGINT PRIMARY KEY REFERENCES user_config (userid),
          pet_name TEXT NOT NULL DEFAULT 'Leo',
          expression LGExpression NOT NULL DEFAULT 'DEFAULT',
          level INTEGER NOT NULL DEFAULT 1,
          xp BIGINT NOT NULL DEFAULT 0,
          food INTEGER NOT NULL DEFAULT 8,
          bath INTEGER NOT NULL DEFAULT 8,
          sleep INTEGER NOT NULL DEFAULT 8,
          life INTEGER NOT NULL DEFAULT 8,
          last_decay_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          active_room_id INTEGER,
          active_gameboy_skin_id INTEGER,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          drop_notif TEXT NOT NULL DEFAULT 'ALL',
          last_pet_warning TIMESTAMPTZ
        );
        """
        _tablename_ = 'lg_pets'
        _cache_ = {}

        userid = Integer(primary=True)
        pet_name = String()
        expression: Column[LGExpression] = Column()
        level = Integer()
        xp = Integer()
        food = Integer()
        bath = Integer()
        sleep = Integer()
        life = Integer()
        last_decay_at = Timestamp()
        active_room_id = Integer()
        active_gameboy_skin_id = Integer()
        created_at = Timestamp()
        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: User notification preference for material drops (ALL / DM_ONLY / MUTED)
        drop_notif = String()
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Persist pet warning cooldown in DB so it survives restarts and works across shards
        last_pet_warning = Timestamp()
        # --- END AI-MODIFIED ---

    class GoldTransaction(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_gold_transactions (
          transactionid SERIAL PRIMARY KEY,
          transaction_type LGGoldTransactionType NOT NULL,
          actorid BIGINT NOT NULL,
          from_account BIGINT,
          to_account BIGINT,
          amount INTEGER NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          reference TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        _tablename_ = 'lg_gold_transactions'

        transactionid = Integer(primary=True)
        transaction_type: Column[LGGoldTransactionType] = Column()
        actorid = Integer()
        from_account = Integer()
        to_account = Integer()
        amount = Integer()
        description = String()
        reference = String()
        created_at = Timestamp()

    class Item(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_items (
          itemid SERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          category LGItemCategory NOT NULL,
          slot LGEquipmentSlot,
          rarity LGRarity NOT NULL DEFAULT 'COMMON',
          asset_path TEXT NOT NULL,
          gold_price INTEGER,
          gem_price INTEGER,
          tradeable BOOLEAN NOT NULL DEFAULT TRUE,
          description TEXT NOT NULL DEFAULT '',
          copyright_flag BOOLEAN NOT NULL DEFAULT FALSE
        );
        """
        _tablename_ = 'lg_items'

        itemid = Integer(primary=True)
        name = String()
        category: Column[LGItemCategory] = Column()
        slot: Column[LGEquipmentSlot] = Column()
        rarity: Column[LGRarity] = Column()
        asset_path = String()
        gold_price = Integer()
        gem_price = Integer()
        tradeable = Bool()
        description = String()
        copyright_flag = Bool()
        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Per-item drop weight for weighted random drops (lower = rarer within tier)
        drop_weight = Column()
        # --- END AI-MODIFIED ---

    class UserInventory(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_user_inventory (
          inventoryid SERIAL PRIMARY KEY,
          userid BIGINT NOT NULL REFERENCES user_config (userid),
          itemid INTEGER NOT NULL REFERENCES lg_items (itemid),
          acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          source LGItemSource NOT NULL DEFAULT 'SHOP',
          quantity INTEGER NOT NULL DEFAULT 1,
          enhancement_level INTEGER NOT NULL DEFAULT 0
        );
        """
        _tablename_ = 'lg_user_inventory'

        inventoryid = Integer(primary=True)
        userid = Integer()
        itemid = Integer()
        acquired_at = Timestamp()
        source: Column[LGItemSource] = Column()
        # --- AI-MODIFIED (2026-03-15) ---
        # Purpose: Quantity for stackable materials/scrolls, enhancement level for equipment
        quantity = Integer()
        enhancement_level = Integer()
        # --- END AI-MODIFIED ---

    class PetEquipment(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_pet_equipment (
          userid BIGINT NOT NULL REFERENCES lg_pets (userid),
          slot LGEquipmentSlot NOT NULL,
          itemid INTEGER NOT NULL REFERENCES lg_items (itemid),
          PRIMARY KEY (userid, slot)
        );
        """
        _tablename_ = 'lg_pet_equipment'

        userid = Integer(primary=True)
        slot: Column[LGEquipmentSlot] = Column(primary=True)
        itemid = Integer()

    class Room(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_rooms (
          room_id SERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          asset_prefix TEXT NOT NULL,
          has_furniture BOOLEAN NOT NULL DEFAULT FALSE,
          gold_price INTEGER,
          gem_price INTEGER
        );
        """
        _tablename_ = 'lg_rooms'

        room_id = Integer(primary=True)
        name = String()
        asset_prefix = String()
        has_furniture = Bool()
        gold_price = Integer()
        gem_price = Integer()

    class UserRoom(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_user_rooms (
          userid BIGINT NOT NULL REFERENCES lg_pets (userid),
          room_id INTEGER NOT NULL REFERENCES lg_rooms (room_id),
          unlocked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (userid, room_id)
        );
        """
        _tablename_ = 'lg_user_rooms'

        userid = Integer(primary=True)
        room_id = Integer(primary=True)
        unlocked_at = Timestamp()

    class UserFurniture(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_user_furniture (
          userid BIGINT NOT NULL,
          room_id INTEGER NOT NULL,
          slot LGFurnitureSlot NOT NULL,
          furniture_itemid INTEGER NOT NULL REFERENCES lg_items (itemid),
          PRIMARY KEY (userid, room_id, slot)
        );
        """
        _tablename_ = 'lg_user_furniture'

        userid = Integer(primary=True)
        room_id = Integer(primary=True)
        slot: Column[LGFurnitureSlot] = Column(primary=True)
        furniture_itemid = Integer()

    class GameboySkin(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_gameboy_skins (
          skin_id SERIAL PRIMARY KEY,
          theme TEXT NOT NULL,
          color TEXT NOT NULL,
          asset_path TEXT NOT NULL,
          unlock_type LGUnlockType NOT NULL DEFAULT 'GOLD',
          unlock_level INTEGER,
          gold_price INTEGER,
          gem_price INTEGER
        );
        """
        _tablename_ = 'lg_gameboy_skins'

        skin_id = Integer(primary=True)
        theme = String()
        color = String()
        asset_path = String()
        unlock_type = String()
        unlock_level = Integer()
        gold_price = Integer()
        gem_price = Integer()

    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Added plant_cost and growth_points_needed for activity-driven farm
    class FarmSeed(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_farm_seeds (
          seed_id SERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          plant_type TEXT NOT NULL,
          grow_time_hours INTEGER NOT NULL DEFAULT 24,
          water_interval_hours INTEGER NOT NULL DEFAULT 6,
          harvest_gold INTEGER NOT NULL DEFAULT 10,
          asset_prefix TEXT NOT NULL,
          plant_cost INTEGER NOT NULL DEFAULT 10,
          growth_points_needed INTEGER NOT NULL DEFAULT 100
        );
        """
        _tablename_ = 'lg_farm_seeds'

        seed_id = Integer(primary=True)
        name = String()
        plant_type = String()
        grow_time_hours = Integer()
        water_interval_hours = Integer()
        harvest_gold = Integer()
        asset_prefix = String()
        plant_cost = Integer()
        growth_points_needed = Integer()
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Added growth_points, gold_invested, activity tracking for activity-driven farm
    class UserFarm(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_user_farm (
          userid BIGINT NOT NULL REFERENCES lg_pets (userid),
          plot_id INTEGER NOT NULL,
          seed_id INTEGER REFERENCES lg_farm_seeds (seed_id),
          planted_at TIMESTAMPTZ,
          last_watered TIMESTAMPTZ,
          growth_stage INTEGER NOT NULL DEFAULT 0,
          dead BOOLEAN NOT NULL DEFAULT FALSE,
          growth_points REAL NOT NULL DEFAULT 0,
          gold_invested INTEGER NOT NULL DEFAULT 0,
          voice_minutes_earned REAL NOT NULL DEFAULT 0,
          messages_earned INTEGER NOT NULL DEFAULT 0,
          rarity TEXT NOT NULL DEFAULT 'COMMON',
          PRIMARY KEY (userid, plot_id)
        );
        """
        _tablename_ = 'lg_user_farm'

        userid = Integer(primary=True)
        plot_id = Integer(primary=True)
        seed_id = Integer()
        planted_at = Timestamp()
        last_watered = Timestamp()
        growth_stage = Integer()
        dead = Bool()
        growth_points = Integer()
        gold_invested = Integer()
        voice_minutes_earned = Integer()
        messages_earned = Integer()
        rarity = String()
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: New RowModels for crafting and enhancement system

    class CraftingRecipe(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_crafting_recipes (
          recipeid SERIAL PRIMARY KEY,
          result_itemid INTEGER NOT NULL REFERENCES lg_items (itemid),
          result_quantity INTEGER NOT NULL DEFAULT 1,
          gold_cost INTEGER NOT NULL DEFAULT 0,
          description TEXT NOT NULL DEFAULT ''
        );
        """
        _tablename_ = 'lg_crafting_recipes'

        recipeid = Integer(primary=True)
        result_itemid = Integer()
        result_quantity = Integer()
        gold_cost = Integer()
        description = String()

    class RecipeIngredient(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_recipe_ingredients (
          recipeid INTEGER NOT NULL REFERENCES lg_crafting_recipes (recipeid) ON DELETE CASCADE,
          itemid INTEGER NOT NULL REFERENCES lg_items (itemid),
          quantity INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY (recipeid, itemid)
        );
        """
        _tablename_ = 'lg_recipe_ingredients'

        recipeid = Integer(primary=True)
        itemid = Integer(primary=True)
        quantity = Integer()

    class ScrollProperties(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_scroll_properties (
          itemid INTEGER PRIMARY KEY REFERENCES lg_items (itemid),
          target_slot TEXT,
          success_rate REAL NOT NULL DEFAULT 0.7,
          destroy_rate REAL NOT NULL DEFAULT 0.1,
          bonus_value REAL NOT NULL DEFAULT 1.0
        );
        """
        _tablename_ = 'lg_scroll_properties'

        itemid = Integer(primary=True)
        target_slot = String()
        success_rate = Column()
        destroy_rate = Column()
        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Scroll bonus multiplier -- higher risk scrolls give more stats per level
        bonus_value = Column()
        # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Enhancement slot history -- tracks which scroll was used at each level
    class EnhancementSlot(RowModel):
        """
        Schema
        ------
        CREATE TABLE lg_enhancement_slots (
          slotid SERIAL PRIMARY KEY,
          inventoryid INTEGER NOT NULL REFERENCES lg_user_inventory (inventoryid) ON DELETE CASCADE,
          slot_number INTEGER NOT NULL,
          scroll_itemid INTEGER NOT NULL REFERENCES lg_items (itemid),
          scroll_name VARCHAR(64) NOT NULL,
          bonus_value REAL NOT NULL DEFAULT 1.0,
          enhanced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          UNIQUE(inventoryid, slot_number)
        );
        """
        _tablename_ = 'lg_enhancement_slots'

        slotid = Integer(primary=True)
        inventoryid = Integer()
        slot_number = Integer()
        scroll_itemid = Integer()
        scroll_name = String()
        bonus_value = Column()
        enhanced_at = Timestamp()
    # --- END AI-MODIFIED ---

    # --- END AI-MODIFIED ---

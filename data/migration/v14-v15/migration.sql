-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: LionGotchi virtual pet system - database schema migration
-- ============================================================

BEGIN;

-- Gold transaction types
CREATE TYPE LGGoldTransactionType AS ENUM (
  'VOICE_ACTIVITY',
  'TEXT_ACTIVITY',
  'LEVEL_UP',
  'SHOP_PURCHASE',
  'FARM_HARVEST',
  'ITEM_DROP',
  'TRADE',
  'ADMIN'
);

-- Equipment slot types
CREATE TYPE LGEquipmentSlot AS ENUM (
  'HEAD',
  'FACE',
  'BODY',
  'BACK',
  'FEET'
);

-- Item rarity tiers
CREATE TYPE LGRarity AS ENUM (
  'COMMON',
  'UNCOMMON',
  'RARE',
  'EPIC',
  'LEGENDARY',
  'MYTHICAL'
);

-- Item categories
CREATE TYPE LGItemCategory AS ENUM (
  'HAT',
  'GLASSES',
  'COSTUME',
  'SHIRT',
  'WINGS',
  'FURNITURE',
  'ROOM',
  'GAMEBOY_SKIN',
  'FARM_SEED',
  'CONSUMABLE'
);

-- Item acquisition source
CREATE TYPE LGItemSource AS ENUM (
  'SHOP',
  'DROP',
  'LEVEL_REWARD',
  'FARM_HARVEST',
  'TRADE',
  'ADMIN',
  'TUTORIAL'
);

-- Room furniture slot types
CREATE TYPE LGFurnitureSlot AS ENUM (
  'WALL',
  'FLOOR',
  'CARPET',
  'BED',
  'CHAIR',
  'DESK',
  'LAMP'
);

-- Gameboy skin unlock method
CREATE TYPE LGUnlockType AS ENUM (
  'FREE',
  'LEVEL',
  'GOLD',
  'GEMS',
  'EVENT'
);

-- Pet expression / mood
CREATE TYPE LGExpression AS ENUM (
  'DEFAULT',
  'HAPPY',
  'SAD',
  'EATING',
  'SICK',
  'SLEEPING'
);

-- ========== Add gold column to existing user_config ==========

ALTER TABLE user_config ADD COLUMN IF NOT EXISTS gold BIGINT NOT NULL DEFAULT 0;

-- ========== Core pet table ==========

CREATE TABLE lg_pets (
  userid BIGINT PRIMARY KEY REFERENCES user_config (userid),
  pet_name TEXT NOT NULL DEFAULT 'Leo',
  expression LGExpression NOT NULL DEFAULT 'DEFAULT',
  level INTEGER NOT NULL DEFAULT 1,
  xp BIGINT NOT NULL DEFAULT 0,
  food INTEGER NOT NULL DEFAULT 8 CHECK (food >= 0 AND food <= 8),
  bath INTEGER NOT NULL DEFAULT 8 CHECK (bath >= 0 AND bath <= 8),
  sleep INTEGER NOT NULL DEFAULT 8 CHECK (sleep >= 0 AND sleep <= 8),
  life INTEGER NOT NULL DEFAULT 8 CHECK (life >= 0 AND life <= 8),
  last_decay_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  active_room_id INTEGER,
  active_gameboy_skin_id INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ========== Gold transactions ==========

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
CREATE INDEX lg_gold_transactions_to ON lg_gold_transactions (to_account);
CREATE INDEX lg_gold_transactions_from ON lg_gold_transactions (from_account);

-- ========== Item registry ==========

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
CREATE INDEX lg_items_category ON lg_items (category);

-- ========== User inventory ==========

CREATE TABLE lg_user_inventory (
  inventoryid SERIAL PRIMARY KEY,
  userid BIGINT NOT NULL REFERENCES user_config (userid),
  itemid INTEGER NOT NULL REFERENCES lg_items (itemid),
  acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source LGItemSource NOT NULL DEFAULT 'SHOP'
);
CREATE INDEX lg_user_inventory_user ON lg_user_inventory (userid);

-- ========== Pet equipment (equipped items) ==========

CREATE TABLE lg_pet_equipment (
  userid BIGINT NOT NULL REFERENCES lg_pets (userid),
  slot LGEquipmentSlot NOT NULL,
  itemid INTEGER NOT NULL REFERENCES lg_items (itemid),
  PRIMARY KEY (userid, slot)
);

-- ========== Room registry ==========

CREATE TABLE lg_rooms (
  room_id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  asset_prefix TEXT NOT NULL,
  has_furniture BOOLEAN NOT NULL DEFAULT FALSE,
  gold_price INTEGER,
  gem_price INTEGER
);

-- ========== User owned rooms ==========

CREATE TABLE lg_user_rooms (
  userid BIGINT NOT NULL REFERENCES lg_pets (userid),
  room_id INTEGER NOT NULL REFERENCES lg_rooms (room_id),
  unlocked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (userid, room_id)
);

-- ========== User room furniture ==========

CREATE TABLE lg_user_furniture (
  userid BIGINT NOT NULL,
  room_id INTEGER NOT NULL,
  slot LGFurnitureSlot NOT NULL,
  furniture_itemid INTEGER NOT NULL REFERENCES lg_items (itemid),
  PRIMARY KEY (userid, room_id, slot),
  FOREIGN KEY (userid, room_id) REFERENCES lg_user_rooms (userid, room_id)
);

-- ========== Gameboy skins ==========

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

-- ========== Farm seed registry ==========

CREATE TABLE lg_farm_seeds (
  seed_id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  plant_type TEXT NOT NULL,
  grow_time_hours INTEGER NOT NULL DEFAULT 24,
  water_interval_hours INTEGER NOT NULL DEFAULT 6,
  harvest_gold INTEGER NOT NULL DEFAULT 10,
  asset_prefix TEXT NOT NULL
);

-- ========== User farm plots ==========

CREATE TABLE lg_user_farm (
  userid BIGINT NOT NULL REFERENCES lg_pets (userid),
  plot_id INTEGER NOT NULL,
  seed_id INTEGER REFERENCES lg_farm_seeds (seed_id),
  planted_at TIMESTAMPTZ,
  last_watered TIMESTAMPTZ,
  growth_stage INTEGER NOT NULL DEFAULT 0,
  dead BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (userid, plot_id)
);

-- ========== Seed initial data: rooms ==========

INSERT INTO lg_rooms (name, asset_prefix, has_furniture, gold_price) VALUES
  ('Castle', 'rooms/castle', TRUE, NULL),
  ('Cave', 'rooms/cave', TRUE, 500),
  ('Futuristic', 'rooms/futuristic', TRUE, 1000),
  ('Library', 'rooms/library', TRUE, 750),
  ('Moon', 'rooms/moon', TRUE, 1500);

-- ========== Seed initial data: gameboy skins ==========

INSERT INTO lg_gameboy_skins (theme, color, asset_path, unlock_type, unlock_level, gold_price, gem_price) VALUES
  ('flat', 'blue', 'gameboy/frames/flat/blue.png', 'FREE', NULL, NULL, NULL),
  ('flat', 'green', 'gameboy/frames/flat/green.png', 'GOLD', NULL, 200, NULL),
  ('flat', 'orange', 'gameboy/frames/flat/orange.png', 'GOLD', NULL, 200, NULL),
  ('flat', 'purple', 'gameboy/frames/flat/purple.png', 'GOLD', NULL, 200, NULL),
  ('flat', 'red', 'gameboy/frames/flat/red.png', 'GOLD', NULL, 200, NULL),
  ('fire', 'blue', 'gameboy/frames/fire/blue.png', 'LEVEL', 10, NULL, NULL),
  ('fire', 'green', 'gameboy/frames/fire/green.png', 'LEVEL', 15, NULL, NULL),
  ('fire', 'red', 'gameboy/frames/fire/red.png', 'LEVEL', 20, NULL, NULL),
  ('fish_n_flower', '1', 'gameboy/frames/fish_n_flower/fish_n_flower_1.png', 'GOLD', NULL, 500, NULL),
  ('fish_n_flower', '2', 'gameboy/frames/fish_n_flower/fish_n_flower_2.png', 'GOLD', NULL, 500, NULL),
  ('fish_n_flower', '3', 'gameboy/frames/fish_n_flower/fish_n_flower_3.png', 'GOLD', NULL, 500, NULL),
  ('fish_n_flower', '4', 'gameboy/frames/fish_n_flower/fish_n_flower_4.png', 'GOLD', NULL, 500, NULL),
  ('fish_n_flower', '5', 'gameboy/frames/fish_n_flower/fish_n_flower_5.png', 'GOLD', NULL, 500, NULL),
  ('flower', '1', 'gameboy/frames/flower/flower_1.png', 'GOLD', NULL, 500, NULL),
  ('flower', '2', 'gameboy/frames/flower/flower_2.png', 'GOLD', NULL, 500, NULL),
  ('flower', '3', 'gameboy/frames/flower/flower_3.png', 'GOLD', NULL, 500, NULL),
  ('flower', '4', 'gameboy/frames/flower/flower_4.png', 'GOLD', NULL, 500, NULL),
  ('flower', '5', 'gameboy/frames/flower/flower_5.png', 'GOLD', NULL, 500, NULL),
  ('japan_pattern', '1', 'gameboy/frames/japan_pattern/japan_pattern_1.png', 'GEMS', NULL, NULL, 50),
  ('japan_pattern', '2', 'gameboy/frames/japan_pattern/japan_pattern_2.png', 'GEMS', NULL, NULL, 50),
  ('japan_pattern', '3', 'gameboy/frames/japan_pattern/japan_pattern_3.png', 'GEMS', NULL, NULL, 50),
  ('japan_pattern', '4', 'gameboy/frames/japan_pattern/japan_pattern_4.png', 'GEMS', NULL, NULL, 50),
  ('japan_pattern', '5', 'gameboy/frames/japan_pattern/japan_pattern_5.png', 'GEMS', NULL, NULL, 50),
  ('japan_pattern', '6', 'gameboy/frames/japan_pattern/japan_pattern_6.png', 'GEMS', NULL, NULL, 50),
  ('love', 'cyan', 'gameboy/frames/love/cyan.png', 'GEMS', NULL, NULL, 75),
  ('love', 'peach', 'gameboy/frames/love/peach.png', 'GEMS', NULL, NULL, 75),
  ('love', 'purple', 'gameboy/frames/love/purple.png', 'GEMS', NULL, NULL, 75),
  ('wave', 'blue', 'gameboy/frames/wave/blue.png', 'LEVEL', 25, NULL, NULL),
  ('wave', 'cyan', 'gameboy/frames/wave/cyan.png', 'LEVEL', 30, NULL, NULL),
  ('wave', 'purple', 'gameboy/frames/wave/purple.png', 'LEVEL', 50, NULL, NULL);

INSERT INTO VersionHistory (version, author) VALUES (15, 'v14-v15 LionGotchi virtual pet system');

COMMIT;

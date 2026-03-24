-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Crafting & Enhancement system schema changes
-- ============================================================

-- New enum values for item categories and sources
ALTER TYPE lgitemcategory ADD VALUE IF NOT EXISTS 'MATERIAL';
ALTER TYPE lgitemcategory ADD VALUE IF NOT EXISTS 'SCROLL';
ALTER TYPE lgitemsource ADD VALUE IF NOT EXISTS 'CRAFT';

-- Add quantity and enhancement_level columns to inventory
ALTER TABLE lg_user_inventory
  ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS enhancement_level INTEGER NOT NULL DEFAULT 0;

-- Partial unique index for stackable items (materials/scrolls)
-- Only stacks rows where enhancement_level = 0
CREATE UNIQUE INDEX IF NOT EXISTS lg_inventory_stack_idx
  ON lg_user_inventory (userid, itemid)
  WHERE enhancement_level = 0;

-- Crafting recipes
CREATE TABLE IF NOT EXISTS lg_crafting_recipes (
    recipeid SERIAL PRIMARY KEY,
    result_itemid INTEGER NOT NULL REFERENCES lg_items(itemid),
    result_quantity INTEGER NOT NULL DEFAULT 1,
    gold_cost INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT ''
);

-- Recipe ingredients (what materials are needed)
CREATE TABLE IF NOT EXISTS lg_recipe_ingredients (
    recipeid INTEGER NOT NULL REFERENCES lg_crafting_recipes(recipeid) ON DELETE CASCADE,
    itemid INTEGER NOT NULL REFERENCES lg_items(itemid),
    quantity INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (recipeid, itemid)
);

-- Scroll enhancement properties
CREATE TABLE IF NOT EXISTS lg_scroll_properties (
    itemid INTEGER PRIMARY KEY REFERENCES lg_items(itemid),
    target_slot TEXT,
    success_rate REAL NOT NULL DEFAULT 0.7,
    destroy_rate REAL NOT NULL DEFAULT 0.1
);

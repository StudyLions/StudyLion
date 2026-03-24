-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-17
-- Purpose: MapleStory-style scroll system v2 -- 11 unique scrolls
--          with varying bonus_value, plus enhancement_slots tracking
-- ============================================================

-- ==============================
-- SCHEMA CHANGES
-- ==============================

ALTER TABLE lg_scroll_properties
  ADD COLUMN IF NOT EXISTS bonus_value REAL NOT NULL DEFAULT 1.0;

CREATE TABLE IF NOT EXISTS lg_enhancement_slots (
    slotid        SERIAL PRIMARY KEY,
    inventoryid   INT NOT NULL REFERENCES lg_user_inventory(inventoryid) ON DELETE CASCADE,
    slot_number   INT NOT NULL,
    scroll_itemid INT NOT NULL REFERENCES lg_items(itemid) ON DELETE NO ACTION,
    scroll_name   VARCHAR(64) NOT NULL,
    bonus_value   REAL NOT NULL DEFAULT 1.0,
    enhanced_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(inventoryid, slot_number)
);

CREATE INDEX IF NOT EXISTS idx_enhancement_slots_inv ON lg_enhancement_slots(inventoryid);

-- ==============================
-- CLEAN OLD SCROLL DATA
-- ==============================

DELETE FROM lg_recipe_ingredients WHERE recipeid IN (
    SELECT r.recipeid FROM lg_crafting_recipes r
    JOIN lg_items i ON r.result_itemid = i.itemid
    WHERE i.category = 'SCROLL'
);
DELETE FROM lg_crafting_recipes WHERE result_itemid IN (
    SELECT itemid FROM lg_items WHERE category = 'SCROLL'
);
DELETE FROM lg_scroll_properties;
DELETE FROM lg_user_inventory WHERE itemid IN (
    SELECT itemid FROM lg_items WHERE category = 'SCROLL'
);
DELETE FROM lg_items WHERE category = 'SCROLL';

-- ==============================
-- INSERT 11 NEW SCROLLS
-- ==============================

-- COMMON
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Dusty Scroll', 'SCROLL', 'COMMON', 'scrolls/dusty_scroll.png', true,
 'A worn but reliable scroll. The bread and butter of enhancement.'),
('Forest Scroll', 'SCROLL', 'COMMON', 'scrolls/forest_scroll.png', true,
 'Infused with forest magic. Slightly riskier but more potent than a Dusty Scroll.');

-- UNCOMMON
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Lucky Scroll', 'SCROLL', 'UNCOMMON', 'scrolls/lucky_scroll.png', true,
 'Blessed with good fortune. Will never destroy your equipment, but offers modest power.'),
('Gilded Scroll', 'SCROLL', 'UNCOMMON', 'scrolls/gilded_scroll.png', true,
 'Lined with gold leaf. Your first real gamble -- decent bonus if you dare.');

-- RARE
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Festive Scroll', 'SCROLL', 'RARE', 'scrolls/festive_scroll.png', true,
 'A rare seasonal find adorned with bells. Good odds with a respectable bonus.'),
('Arcane Scroll', 'SCROLL', 'RARE', 'scrolls/arcane_scroll.png', true,
 'Pulsing with arcane energy. A coin-flip that pays off handsomely.');

-- EPIC
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Cryptic Scroll', 'SCROLL', 'EPIC', 'scrolls/cryptic_scroll.png', true,
 'Covered in indecipherable runes. Equal chance of glory and ruin.'),
('Cursed Scroll', 'SCROLL', 'EPIC', 'scrolls/cursed_scroll.png', true,
 'Radiates dark energy. Immense power, but most items don''t survive.');

-- LEGENDARY
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Divine Scroll', 'SCROLL', 'LEGENDARY', 'scrolls/divine_scroll.png', true,
 'Blessed by the gods. Guaranteed success with zero risk -- but modest power.'),
('Celestial Scroll', 'SCROLL', 'LEGENDARY', 'scrolls/celestial_scroll.png', true,
 'Shimmers with every color of the rainbow. Massive bonus for those brave enough.');

-- MYTHICAL
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Doom Scroll', 'SCROLL', 'MYTHICAL', 'scrolls/doom_scroll.png', true,
 'The ultimate gamble. Near-impossible odds, but a single success is legendary.');

-- ==============================
-- SCROLL PROPERTIES
-- ==============================
-- (itemid, target_slot, success_rate, destroy_rate, bonus_value)

-- COMMON: Dusty -- safe workhorse
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.90, 0.05, 1.0
FROM lg_items WHERE name = 'Dusty Scroll' AND category = 'SCROLL';

-- COMMON: Forest -- slightly riskier, slightly better
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.85, 0.08, 1.2
FROM lg_items WHERE name = 'Forest Scroll' AND category = 'SCROLL';

-- UNCOMMON: Lucky -- 0% destroy, same bonus as Dusty
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.75, 0.00, 1.0
FROM lg_items WHERE name = 'Lucky Scroll' AND category = 'SCROLL';

-- UNCOMMON: Gilded -- first real gamble
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.60, 0.15, 1.8
FROM lg_items WHERE name = 'Gilded Scroll' AND category = 'SCROLL';

-- RARE: Festive -- seasonal, decent odds
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.55, 0.10, 2.0
FROM lg_items WHERE name = 'Festive Scroll' AND category = 'SCROLL';

-- RARE: Arcane -- coin-flip territory
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.45, 0.20, 2.5
FROM lg_items WHERE name = 'Arcane Scroll' AND category = 'SCROLL';

-- EPIC: Cryptic -- true gambler's scroll
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.30, 0.30, 3.5
FROM lg_items WHERE name = 'Cryptic Scroll' AND category = 'SCROLL';

-- EPIC: Cursed -- desperate play
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.20, 0.45, 4.5
FROM lg_items WHERE name = 'Cursed Scroll' AND category = 'SCROLL';

-- LEGENDARY: Divine -- guaranteed, safe, modest
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 1.00, 0.00, 1.0
FROM lg_items WHERE name = 'Divine Scroll' AND category = 'SCROLL';

-- LEGENDARY: Celestial -- the whale's dream
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.35, 0.30, 5.0
FROM lg_items WHERE name = 'Celestial Scroll' AND category = 'SCROLL';

-- MYTHICAL: Doom -- the ultimate gamble
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate, bonus_value)
SELECT itemid, NULL, 0.15, 0.60, 7.0
FROM lg_items WHERE name = 'Doom Scroll' AND category = 'SCROLL';

-- ==============================
-- BACKFILL: Create enhancement slot history for already-enhanced items
-- ==============================
-- Existing enhanced items are treated as if Dusty Scrolls (1.0 bonus) were used.
-- This preserves backward compatibility.

INSERT INTO lg_enhancement_slots (inventoryid, slot_number, scroll_itemid, scroll_name, bonus_value)
SELECT
    ui.inventoryid,
    gs.n,
    (SELECT itemid FROM lg_items WHERE name = 'Dusty Scroll' AND category = 'SCROLL' LIMIT 1),
    'Dusty Scroll',
    1.0
FROM lg_user_inventory ui
CROSS JOIN generate_series(1, 20) AS gs(n)
WHERE ui.enhancement_level > 0
  AND gs.n <= ui.enhancement_level
ON CONFLICT (inventoryid, slot_number) DO NOTHING;

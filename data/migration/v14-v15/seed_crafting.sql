-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Seed scroll items, scroll properties, and crafting recipes
-- ============================================================

-- Clean up existing crafting data
DELETE FROM lg_recipe_ingredients;
DELETE FROM lg_crafting_recipes;
DELETE FROM lg_scroll_properties;
DELETE FROM lg_user_inventory WHERE itemid IN (SELECT itemid FROM lg_items WHERE category = 'SCROLL');
DELETE FROM lg_items WHERE category = 'SCROLL';

-- ==============================
-- SCROLL ITEMS
-- ==============================
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Basic Enhancement Scroll', 'SCROLL', 'COMMON', 'scrolls/basic_scroll.png', true,
 'A simple scroll. High success rate but can destroy items at higher levels.'),
('Intermediate Enhancement Scroll', 'SCROLL', 'UNCOMMON', 'scrolls/intermediate_scroll.png', true,
 'A refined scroll with decent success and moderate risk.'),
('Advanced Enhancement Scroll', 'SCROLL', 'RARE', 'scrolls/advanced_scroll.png', true,
 'A powerful scroll. Lower success but pushes items to high levels.'),
('Master Enhancement Scroll', 'SCROLL', 'EPIC', 'scrolls/master_scroll.png', true,
 'A masterwork scroll. Risky, but the only way to reach elite levels.'),
('Protection Scroll', 'SCROLL', 'LEGENDARY', 'scrolls/protection_scroll.png', true,
 'Guarantees success with zero destroy chance. Extremely valuable.');

-- ==============================
-- SCROLL PROPERTIES
-- ==============================
-- target_slot NULL = works on any equipment slot
INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate)
SELECT itemid, NULL, 0.90, 0.05 FROM lg_items WHERE name = 'Basic Enhancement Scroll' AND category = 'SCROLL';

INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate)
SELECT itemid, NULL, 0.70, 0.10 FROM lg_items WHERE name = 'Intermediate Enhancement Scroll' AND category = 'SCROLL';

INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate)
SELECT itemid, NULL, 0.50, 0.15 FROM lg_items WHERE name = 'Advanced Enhancement Scroll' AND category = 'SCROLL';

INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate)
SELECT itemid, NULL, 0.30, 0.25 FROM lg_items WHERE name = 'Master Enhancement Scroll' AND category = 'SCROLL';

INSERT INTO lg_scroll_properties (itemid, target_slot, success_rate, destroy_rate)
SELECT itemid, NULL, 1.00, 0.00 FROM lg_items WHERE name = 'Protection Scroll' AND category = 'SCROLL';

-- ==============================
-- CRAFTING RECIPES
-- ==============================

-- Recipe 1: Basic Enhancement Scroll
-- 8x Dandelion Wish + 5x Ink Drop + 3x Paper Scrap
INSERT INTO lg_crafting_recipes (result_itemid, result_quantity, gold_cost, description)
SELECT itemid, 1, 10, 'A simple enhancement scroll crafted from wishes and ink.'
FROM lg_items WHERE name = 'Basic Enhancement Scroll' AND category = 'SCROLL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 8
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Basic Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Dandelion Wish' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 5
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Basic Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Ink Drop' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 3
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Basic Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Paper Scrap' AND i.category = 'MATERIAL';


-- Recipe 2: Intermediate Enhancement Scroll
-- 4x Moonlight Essence + 3x Silk Thread + 2x Quartz Chip
INSERT INTO lg_crafting_recipes (result_itemid, result_quantity, gold_cost, description)
SELECT itemid, 1, 50, 'A scroll infused with moonlight and gemstone essence.'
FROM lg_items WHERE name = 'Intermediate Enhancement Scroll' AND category = 'SCROLL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 4
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Intermediate Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Moonlight Essence' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 3
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Intermediate Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Silk Thread' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 2
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Intermediate Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Quartz Chip' AND i.category = 'MATERIAL';


-- Recipe 3: Advanced Enhancement Scroll
-- 3x Enchanted Ink + 2x Moonwoven Silk + 1x Frozen Tear
INSERT INTO lg_crafting_recipes (result_itemid, result_quantity, gold_cost, description)
SELECT itemid, 1, 200, 'A scroll written with enchanted ink on moonwoven silk.'
FROM lg_items WHERE name = 'Advanced Enhancement Scroll' AND category = 'SCROLL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 3
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Advanced Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Enchanted Ink' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 2
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Advanced Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Moonwoven Silk' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 1
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Advanced Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Frozen Tear' AND i.category = 'MATERIAL';


-- Recipe 4: Master Enhancement Scroll
-- 2x Liquid Starlight + 2x Dragon Whisker + 1x Diamond Dust
INSERT INTO lg_crafting_recipes (result_itemid, result_quantity, gold_cost, description)
SELECT itemid, 1, 500, 'The ultimate scroll, forged from starlight and dragon essence.'
FROM lg_items WHERE name = 'Master Enhancement Scroll' AND category = 'SCROLL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 2
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Master Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Liquid Starlight' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 2
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Master Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Dragon Whisker' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 1
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Master Enhancement Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Diamond Dust' AND i.category = 'MATERIAL';


-- Recipe 5: Protection Scroll
-- 1x Philosopher's Stone Shard + 3x Celestial Thread + 2x Bottled Aurora
INSERT INTO lg_crafting_recipes (result_itemid, result_quantity, gold_cost, description)
SELECT itemid, 1, 1000, 'A protective scroll that prevents all risk during enhancement.'
FROM lg_items WHERE name = 'Protection Scroll' AND category = 'SCROLL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 1
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Protection Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Philosopher''s Stone Shard' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 3
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Protection Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Celestial Thread' AND i.category = 'MATERIAL';

INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity)
SELECT r.recipeid, i.itemid, 2
FROM lg_crafting_recipes r
JOIN lg_items ri ON r.result_itemid = ri.itemid AND ri.name = 'Protection Scroll'
CROSS JOIN lg_items i WHERE i.name = 'Bottled Aurora' AND i.category = 'MATERIAL';

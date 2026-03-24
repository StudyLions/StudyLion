-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-17
-- Purpose: Economy rebalance -- farm seed values + items drop-only
--          Efficiency (net gold / growth point) scales UP with
--          seed cost: 0.16 (starter) to 0.36 (legendary).
--          Equipment/scroll gold_price set to NULL (drop-only).
-- ============================================================

-- ============================================================
-- PART 1: Farm seed rebalance (all 30 seeds)
-- ============================================================

-- Tier 1 - Starter (harvest ~daily, eff 0.16)
UPDATE lg_farm_seeds SET harvest_gold = 10,  growth_points_needed = 45,  plant_cost = 3  WHERE seed_id = 11; -- Tiny Sprout
UPDATE lg_farm_seeds SET harvest_gold = 10,  growth_points_needed = 45,  plant_cost = 3  WHERE seed_id = 24; -- Sunfire Bloom

-- Tier 2 - Basic (harvest ~2 days, eff 0.19-0.20)
UPDATE lg_farm_seeds SET harvest_gold = 22,  growth_points_needed = 80,  plant_cost = 6  WHERE seed_id = 12; -- Meadow Flower
UPDATE lg_farm_seeds SET harvest_gold = 24,  growth_points_needed = 90,  plant_cost = 7  WHERE seed_id = 16; -- Mint Sprout
UPDATE lg_farm_seeds SET harvest_gold = 25,  growth_points_needed = 90,  plant_cost = 7  WHERE seed_id = 7;  -- Orange Autumn
UPDATE lg_farm_seeds SET harvest_gold = 25,  growth_points_needed = 95,  plant_cost = 7  WHERE seed_id = 25; -- Coral Petal

-- Tier 3 - Standard (harvest ~3-4 days, eff 0.23-0.24)
UPDATE lg_farm_seeds SET harvest_gold = 42,  growth_points_needed = 130, plant_cost = 12 WHERE seed_id = 1;  -- Blue Blossom
UPDATE lg_farm_seeds SET harvest_gold = 42,  growth_points_needed = 130, plant_cost = 12 WHERE seed_id = 4;  -- Pink Cherry
UPDATE lg_farm_seeds SET harvest_gold = 48,  growth_points_needed = 150, plant_cost = 14 WHERE seed_id = 13; -- Desert Cactus
UPDATE lg_farm_seeds SET harvest_gold = 48,  growth_points_needed = 150, plant_cost = 14 WHERE seed_id = 17; -- Wild Fern
UPDATE lg_farm_seeds SET harvest_gold = 52,  growth_points_needed = 160, plant_cost = 15 WHERE seed_id = 2;  -- Red Maple
UPDATE lg_farm_seeds SET harvest_gold = 52,  growth_points_needed = 160, plant_cost = 15 WHERE seed_id = 6;  -- Green Pine
UPDATE lg_farm_seeds SET harvest_gold = 55,  growth_points_needed = 170, plant_cost = 16 WHERE seed_id = 14; -- Moon Bloom
UPDATE lg_farm_seeds SET harvest_gold = 55,  growth_points_needed = 170, plant_cost = 16 WHERE seed_id = 18; -- Autumn Berry

-- Tier 4 - Advanced (harvest ~5-7 days, eff 0.26-0.27)
UPDATE lg_farm_seeds SET harvest_gold = 80,  growth_points_needed = 220, plant_cost = 22 WHERE seed_id = 5;  -- Purple Willow
UPDATE lg_farm_seeds SET harvest_gold = 80,  growth_points_needed = 220, plant_cost = 22 WHERE seed_id = 8;  -- White Birch
UPDATE lg_farm_seeds SET harvest_gold = 88,  growth_points_needed = 240, plant_cost = 24 WHERE seed_id = 19; -- Frost Willow
UPDATE lg_farm_seeds SET harvest_gold = 88,  growth_points_needed = 240, plant_cost = 24 WHERE seed_id = 20; -- Ember Vine
UPDATE lg_farm_seeds SET harvest_gold = 95,  growth_points_needed = 260, plant_cost = 26 WHERE seed_id = 26; -- Violet Mist
UPDATE lg_farm_seeds SET harvest_gold = 100, growth_points_needed = 280, plant_cost = 28 WHERE seed_id = 21; -- Ocean Kelp
UPDATE lg_farm_seeds SET harvest_gold = 100, growth_points_needed = 280, plant_cost = 28 WHERE seed_id = 27; -- Jade Lotus
UPDATE lg_farm_seeds SET harvest_gold = 108, growth_points_needed = 300, plant_cost = 30 WHERE seed_id = 15; -- Star Flower

-- Tier 5 - Premium (harvest ~8-10 days, eff 0.29-0.30)
UPDATE lg_farm_seeds SET harvest_gold = 145, growth_points_needed = 360, plant_cost = 40 WHERE seed_id = 22; -- Shadow Elm
UPDATE lg_farm_seeds SET harvest_gold = 148, growth_points_needed = 370, plant_cost = 40 WHERE seed_id = 23; -- Thunder Root
UPDATE lg_farm_seeds SET harvest_gold = 155, growth_points_needed = 380, plant_cost = 42 WHERE seed_id = 3;  -- Golden Oak
UPDATE lg_farm_seeds SET harvest_gold = 165, growth_points_needed = 400, plant_cost = 45 WHERE seed_id = 9;  -- Crystal Tree
UPDATE lg_farm_seeds SET harvest_gold = 175, growth_points_needed = 420, plant_cost = 48 WHERE seed_id = 28; -- Mystic Rose

-- Tier 6 - Legendary (harvest ~12-14 days, eff 0.35-0.36)
UPDATE lg_farm_seeds SET harvest_gold = 240, growth_points_needed = 500, plant_cost = 65 WHERE seed_id = 10; -- Rainbow Tree
UPDATE lg_farm_seeds SET harvest_gold = 255, growth_points_needed = 520, plant_cost = 70 WHERE seed_id = 29; -- Dragon Fern
UPDATE lg_farm_seeds SET harvest_gold = 270, growth_points_needed = 540, plant_cost = 75 WHERE seed_id = 30; -- Phoenix Bloom

-- ============================================================
-- PART 2: Items = drops only (remove gold_price from equipment & scrolls)
-- ============================================================

UPDATE lg_items SET gold_price = NULL
WHERE category IN ('HAT', 'GLASSES', 'COSTUME', 'SHIRT', 'WINGS', 'BOOTS', 'SCROLL');

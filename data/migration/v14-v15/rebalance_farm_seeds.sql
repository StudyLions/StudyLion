-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-16
-- Purpose: Rebalance farm seeds -- differentiate growth_points_needed
--          and plant_cost per plant so the economy has meaningful
--          choices. Formula: ~25 growth pts per grow_time_hour,
--          cost at ~30-40% of harvest_gold.
-- ============================================================

-- Original 15 seeds (values from the approved plan)
UPDATE lg_farm_seeds SET growth_points_needed = 150, plant_cost = 12  WHERE seed_id = 1;  -- Blue Blossom (6hr, 30G)
UPDATE lg_farm_seeds SET growth_points_needed = 200, plant_cost = 15  WHERE seed_id = 2;  -- Red Maple (8hr, 40G)
UPDATE lg_farm_seeds SET growth_points_needed = 300, plant_cost = 30  WHERE seed_id = 3;  -- Golden Oak (12hr, 60G)
UPDATE lg_farm_seeds SET growth_points_needed = 150, plant_cost = 12  WHERE seed_id = 4;  -- Pink Cherry (6hr, 30G)
UPDATE lg_farm_seeds SET growth_points_needed = 250, plant_cost = 20  WHERE seed_id = 5;  -- Purple Willow (10hr, 50G)
UPDATE lg_farm_seeds SET growth_points_needed = 200, plant_cost = 15  WHERE seed_id = 6;  -- Green Pine (8hr, 40G)
UPDATE lg_farm_seeds SET growth_points_needed = 150, plant_cost = 14  WHERE seed_id = 7;  -- Orange Autumn (6hr, 35G)
UPDATE lg_farm_seeds SET growth_points_needed = 250, plant_cost = 20  WHERE seed_id = 8;  -- White Birch (10hr, 50G)
UPDATE lg_farm_seeds SET growth_points_needed = 500, plant_cost = 50  WHERE seed_id = 9;  -- Crystal Tree (24hr, 120G)
UPDATE lg_farm_seeds SET growth_points_needed = 600, plant_cost = 65  WHERE seed_id = 10; -- Rainbow Tree (24hr, 150G)
UPDATE lg_farm_seeds SET growth_points_needed = 50,  plant_cost = 5   WHERE seed_id = 11; -- Tiny Sprout (2hr, 15G)
UPDATE lg_farm_seeds SET growth_points_needed = 80,  plant_cost = 8   WHERE seed_id = 12; -- Meadow Flower (3hr, 20G)
UPDATE lg_farm_seeds SET growth_points_needed = 100, plant_cost = 10  WHERE seed_id = 13; -- Desert Cactus (4hr, 25G)
UPDATE lg_farm_seeds SET growth_points_needed = 150, plant_cost = 15  WHERE seed_id = 14; -- Moon Bloom (6hr, 40G)
UPDATE lg_farm_seeds SET growth_points_needed = 200, plant_cost = 25  WHERE seed_id = 15; -- Star Flower (8hr, 60G)

-- Seeds 16-30 (extrapolated: grow_time_hours * 25, cost ~35% of harvest_gold)
UPDATE lg_farm_seeds SET growth_points_needed = 150, plant_cost = 7   WHERE seed_id = 16; -- Mint Sprout (6hr, 18G)
UPDATE lg_farm_seeds SET growth_points_needed = 200, plant_cost = 9   WHERE seed_id = 17; -- Wild Fern (8hr, 22G)
UPDATE lg_farm_seeds SET growth_points_needed = 250, plant_cost = 11  WHERE seed_id = 18; -- Autumn Berry (10hr, 28G)
UPDATE lg_farm_seeds SET growth_points_needed = 300, plant_cost = 15  WHERE seed_id = 19; -- Frost Willow (12hr, 38G)
UPDATE lg_farm_seeds SET growth_points_needed = 350, plant_cost = 18  WHERE seed_id = 20; -- Ember Vine (14hr, 45G)
UPDATE lg_farm_seeds SET growth_points_needed = 400, plant_cost = 22  WHERE seed_id = 21; -- Ocean Kelp (16hr, 55G)
UPDATE lg_farm_seeds SET growth_points_needed = 500, plant_cost = 28  WHERE seed_id = 22; -- Shadow Elm (20hr, 70G)
UPDATE lg_farm_seeds SET growth_points_needed = 550, plant_cost = 32  WHERE seed_id = 23; -- Thunder Root (22hr, 80G)
UPDATE lg_farm_seeds SET growth_points_needed = 150, plant_cost = 6   WHERE seed_id = 24; -- Sunfire Bloom (6hr, 16G)
UPDATE lg_farm_seeds SET growth_points_needed = 200, plant_cost = 9   WHERE seed_id = 25; -- Coral Petal (8hr, 22G)
UPDATE lg_farm_seeds SET growth_points_needed = 300, plant_cost = 14  WHERE seed_id = 26; -- Violet Mist (12hr, 35G)
UPDATE lg_farm_seeds SET growth_points_needed = 350, plant_cost = 19  WHERE seed_id = 27; -- Jade Lotus (14hr, 48G)
UPDATE lg_farm_seeds SET growth_points_needed = 600, plant_cost = 40  WHERE seed_id = 28; -- Mystic Rose (24hr, 100G)
UPDATE lg_farm_seeds SET growth_points_needed = 650, plant_cost = 52  WHERE seed_id = 29; -- Dragon Fern (26hr, 130G)
UPDATE lg_farm_seeds SET growth_points_needed = 700, plant_cost = 56  WHERE seed_id = 30; -- Phoenix Bloom (28hr, 140G)

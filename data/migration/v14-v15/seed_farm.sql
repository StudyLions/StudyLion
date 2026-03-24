-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Seed farm plant types and initial user farm plots
-- ============================================================

-- Seed tree types (type_id maps to tree asset groups: type 1 = trees_01-05, etc.)
INSERT INTO lg_farm_seeds (name, plant_type, grow_time_hours, water_interval_hours, harvest_gold, asset_prefix) VALUES
  ('Blue Blossom',     'tree',   6,  4, 30,  'tree:1'),
  ('Red Maple',        'tree',   8,  4, 40,  'tree:2'),
  ('Golden Oak',       'tree',   12, 6, 60,  'tree:3'),
  ('Pink Cherry',      'tree',   6,  4, 30,  'tree:4'),
  ('Purple Willow',    'tree',   10, 5, 50,  'tree:5'),
  ('Green Pine',       'tree',   8,  4, 40,  'tree:6'),
  ('Orange Autumn',    'tree',   6,  3, 35,  'tree:7'),
  ('White Birch',      'tree',   10, 5, 50,  'tree:8'),
  ('Crystal Tree',     'tree',   24, 8, 120, 'tree:9'),
  ('Rainbow Tree',     'tree',   24, 8, 150, 'tree:10'),
  ('Tiny Sprout',      'pollen', 2,  2, 15,  'pollen:1'),
  ('Meadow Flower',    'pollen', 3,  2, 20,  'pollen:2'),
  ('Desert Cactus',    'pollen', 4,  6, 25,  'pollen:3'),
  ('Moon Bloom',       'pollen', 6,  3, 40,  'pollen:4'),
  ('Star Flower',      'pollen', 8,  4, 60,  'pollen:5');

-- Give all existing pets 4 starting farm plots (empty)
INSERT INTO lg_user_farm (userid, plot_id, growth_stage, dead)
SELECT p.userid, s.plot_id, 0, false
FROM lg_pets p
CROSS JOIN (VALUES (0), (1), (2), (3)) AS s(plot_id)
ON CONFLICT DO NOTHING;

-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Seed room furniture parts into lg_items as FURNITURE category
-- ============================================================

-- Walls (15 variants across 3 styles)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Checker Wall Blue', 'FURNITURE', NULL, 'COMMON', 'rooms/default/wall_checker_blue.png', 50, 'Blue checkered wallpaper'),
  ('Checker Wall Green', 'FURNITURE', NULL, 'COMMON', 'rooms/default/wall_checker_green.png', 50, 'Green checkered wallpaper'),
  ('Checker Wall Grey', 'FURNITURE', NULL, 'COMMON', 'rooms/default/wall_checker_grey.png', 50, 'Grey checkered wallpaper'),
  ('Checker Wall Pink', 'FURNITURE', NULL, 'COMMON', 'rooms/default/wall_checker_pink.png', 50, 'Pink checkered wallpaper'),
  ('Checker Wall Yellow', 'FURNITURE', NULL, 'COMMON', 'rooms/default/wall_checker_yellow.png', 50, 'Yellow checkered wallpaper'),
  ('Stripe Wall Green', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/wall_stripe_green.png', 100, 'Green striped wallpaper'),
  ('Stripe Wall Grey', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/wall_stripe_grey.png', 100, 'Grey striped wallpaper'),
  ('Stripe Wall Blue', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/wall_stripe_light_blue.png', 100, 'Light blue striped wallpaper'),
  ('Stripe Wall Pink', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/wall_stripe_pink.png', 100, 'Pink striped wallpaper'),
  ('Stripe Wall Yellow', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/wall_stripe_yellow.png', 100, 'Yellow striped wallpaper'),
  ('Dotted Wall Blue', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/walldots_blue.png', 100, 'Blue polka dot wallpaper'),
  ('Dotted Wall Green', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/walldots_green.png', 100, 'Green polka dot wallpaper'),
  ('Dotted Wall Grey', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/walldots_grey.png', 100, 'Grey polka dot wallpaper'),
  ('Dotted Wall Pink', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/walldots_pink.png', 100, 'Pink polka dot wallpaper'),
  ('Dotted Wall Yellow', 'FURNITURE', NULL, 'UNCOMMON', 'rooms/default/walldots_yellow.png', 100, 'Yellow polka dot wallpaper');

-- Floors (5 colors)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Blue Floor', 'FURNITURE', NULL, 'COMMON', 'rooms/default/floor_blue.png', 40, 'Blue flooring'),
  ('Brown Floor', 'FURNITURE', NULL, 'COMMON', 'rooms/default/floor_brown.png', 40, 'Brown wooden floor'),
  ('Green Floor', 'FURNITURE', NULL, 'COMMON', 'rooms/default/floor_green.png', 40, 'Green flooring'),
  ('Orange Floor', 'FURNITURE', NULL, 'COMMON', 'rooms/default/floor_orange.png', 40, 'Orange flooring'),
  ('Purple Floor', 'FURNITURE', NULL, 'COMMON', 'rooms/default/floor_purple.png', 40, 'Purple flooring');

-- Beds (5 colors)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Blue-Yellow Bed', 'FURNITURE', NULL, 'COMMON', 'rooms/default/bed_blueyellow.png', 80, 'Cozy blue and yellow bed'),
  ('Orange Bed', 'FURNITURE', NULL, 'COMMON', 'rooms/default/bed_orange.png', 80, 'Bright orange bed'),
  ('Pink-Purple Bed', 'FURNITURE', NULL, 'COMMON', 'rooms/default/bed_pinkpurple.png', 80, 'Lovely pink and purple bed'),
  ('Red Bed', 'FURNITURE', NULL, 'COMMON', 'rooms/default/bed_red.png', 80, 'Classic red bed'),
  ('Red-Green Bed', 'FURNITURE', NULL, 'COMMON', 'rooms/default/bed_redgreen.png', 80, 'Festive red and green bed');

-- Chairs (5 colors)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Blue Chair', 'FURNITURE', NULL, 'COMMON', 'rooms/default/chair_blue.png', 60, 'Comfortable blue chair'),
  ('Brown Chair', 'FURNITURE', NULL, 'COMMON', 'rooms/default/chair_brown.png', 60, 'Classic brown chair'),
  ('Green Chair', 'FURNITURE', NULL, 'COMMON', 'rooms/default/chair_green.png', 60, 'Fresh green chair'),
  ('Pink Chair', 'FURNITURE', NULL, 'COMMON', 'rooms/default/chair_pink.png', 60, 'Pretty pink chair'),
  ('White Chair', 'FURNITURE', NULL, 'COMMON', 'rooms/default/chair_white.png', 60, 'Clean white chair');

-- Lamps (5 colors)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Blue Lamp', 'FURNITURE', NULL, 'COMMON', 'rooms/default/lamp_blue.png', 40, 'Blue desk lamp'),
  ('Green Lamp', 'FURNITURE', NULL, 'COMMON', 'rooms/default/lamp_green.png', 40, 'Green desk lamp'),
  ('Purple Lamp', 'FURNITURE', NULL, 'COMMON', 'rooms/default/lamp_purple.png', 40, 'Purple desk lamp'),
  ('Red Lamp', 'FURNITURE', NULL, 'COMMON', 'rooms/default/lamp_red.png', 40, 'Red desk lamp'),
  ('Yellow Lamp', 'FURNITURE', NULL, 'COMMON', 'rooms/default/lamp_yellow.png', 40, 'Yellow desk lamp');

-- Mats (5 colors)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Blue Mat', 'FURNITURE', NULL, 'COMMON', 'rooms/default/mat_blue.png', 30, 'Soft blue mat'),
  ('Green Mat', 'FURNITURE', NULL, 'COMMON', 'rooms/default/mat_green.png', 30, 'Soft green mat'),
  ('Red Mat', 'FURNITURE', NULL, 'COMMON', 'rooms/default/mat_red.png', 30, 'Soft red mat'),
  ('Silver Mat', 'FURNITURE', NULL, 'COMMON', 'rooms/default/mat_silver.png', 30, 'Elegant silver mat'),
  ('Yellow Mat', 'FURNITURE', NULL, 'COMMON', 'rooms/default/mat_yellow.png', 30, 'Cheerful yellow mat');

-- Tables (5 colors)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Blue Table', 'FURNITURE', NULL, 'COMMON', 'rooms/default/table_blue.png', 50, 'Blue side table'),
  ('Brown Table', 'FURNITURE', NULL, 'COMMON', 'rooms/default/table_brown.png', 50, 'Classic wooden table'),
  ('Green Table', 'FURNITURE', NULL, 'COMMON', 'rooms/default/table_green.png', 50, 'Green side table'),
  ('Pink Table', 'FURNITURE', NULL, 'COMMON', 'rooms/default/table_pink.png', 50, 'Pink side table'),
  ('White Table', 'FURNITURE', NULL, 'COMMON', 'rooms/default/table_white.png', 50, 'White side table');

-- Pictures (5 colors)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Blue Picture', 'FURNITURE', NULL, 'COMMON', 'rooms/default/picture_blue.png', 30, 'Blue framed picture'),
  ('Brown Picture', 'FURNITURE', NULL, 'COMMON', 'rooms/default/picture_brown.png', 30, 'Brown framed picture'),
  ('Grey Picture', 'FURNITURE', NULL, 'COMMON', 'rooms/default/picture_grey.png', 30, 'Grey framed picture'),
  ('Orange Picture', 'FURNITURE', NULL, 'COMMON', 'rooms/default/picture_orange.png', 30, 'Orange framed picture'),
  ('Red Picture', 'FURNITURE', NULL, 'COMMON', 'rooms/default/picture_red.png', 30, 'Red framed picture');

-- Windows (5 colors)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Blue Window', 'FURNITURE', NULL, 'COMMON', 'rooms/default/window_blue.png', 40, 'Blue curtained window'),
  ('Green Window', 'FURNITURE', NULL, 'COMMON', 'rooms/default/window_green.png', 40, 'Green curtained window'),
  ('Purple-Pink Window', 'FURNITURE', NULL, 'COMMON', 'rooms/default/window_purple_pink.png', 40, 'Purple and pink window'),
  ('Red-Blue Window', 'FURNITURE', NULL, 'COMMON', 'rooms/default/window_red_blue.png', 40, 'Red and blue window'),
  ('Yellow Window', 'FURNITURE', NULL, 'COMMON', 'rooms/default/window_yellow.png', 40, 'Yellow curtained window');

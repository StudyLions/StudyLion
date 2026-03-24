-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Seed initial LionGotchi items into lg_items
-- ============================================================

-- Hats (HEAD slot)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Crown', 'HAT', 'HEAD', 'RARE', 'hats/crown.png', 500, 'A royal golden crown'),
  ('Angel Halo', 'HAT', 'HEAD', 'UNCOMMON', 'hats/angel_halo.png', 200, 'A heavenly halo'),
  ('Pirate Hat', 'HAT', 'HEAD', 'UNCOMMON', 'hats/pirate.png', 200, 'Yarr matey'),
  ('Santa Hat', 'HAT', 'HEAD', 'RARE', 'hats/santa_hat.png', 300, 'Ho ho ho'),
  ('Witch Hat', 'HAT', 'HEAD', 'UNCOMMON', 'hats/witch.png', 200, 'Magical headwear'),
  ('Farmer Hat', 'HAT', 'HEAD', 'COMMON', 'hats/farmer_hat.png', 100, 'Simple farming hat'),
  ('King Crown', 'HAT', 'HEAD', 'LEGENDARY', 'hats/king_crown.png', 1000, 'Crown of the king'),
  ('Pumpkin Head', 'HAT', 'HEAD', 'RARE', 'hats/pumpkin_head.png', 400, 'Spooky season'),
  ('Beanie', 'HAT', 'HEAD', 'COMMON', 'hats/beanie.png', 80, 'Cozy beanie'),
  ('Beret', 'HAT', 'HEAD', 'COMMON', 'hats/beret_hat.png', 100, 'Fancy French beret');

-- Glasses (FACE slot)  
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Classic Glasses', 'GLASSES', 'FACE', 'COMMON', 'glasses/glasses_1_common.png', 80, 'Simple specs'),
  ('Cool Shades', 'GLASSES', 'FACE', 'UNCOMMON', 'glasses/glasses_2_uncommon.png', 150, 'Looking cool'),
  ('Rare Monocle', 'GLASSES', 'FACE', 'RARE', 'glasses/glasses_3_rare.png', 350, 'Quite distinguished'),
  ('Golden Specs', 'GLASSES', 'FACE', 'LEGENDARY', 'glasses/glasses_4_legendary.png', 800, 'Solid gold frames'),
  ('Mystic Eyes', 'GLASSES', 'FACE', 'MYTHICAL', 'glasses/glasses_5_mythical.png', NULL, 'Only from drops');

-- Costumes (BODY slot)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Business Suit', 'COSTUME', 'BODY', 'UNCOMMON', 'costumes/business_suit_business_suit_uncommon.png', 200, 'Professional attire'),
  ('Doctor Coat', 'COSTUME', 'BODY', 'UNCOMMON', 'costumes/doctor_doctor_uncommon.png', 200, 'Medical professional'),
  ('Firefighter', 'COSTUME', 'BODY', 'RARE', 'costumes/firefighter_firefighter_rare.png', 400, 'Brave firefighter gear'),
  ('Police Uniform', 'COSTUME', 'BODY', 'RARE', 'costumes/police_police_rare.png', 400, 'Serve and protect'),
  ('Lucky Cat', 'COSTUME', 'BODY', 'LEGENDARY', 'costumes/lucky_cat_costume_lucky_cat_costume_legendary.png', 900, 'Brings good fortune');

-- Shirts (BODY slot)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Basic Shirt', 'SHIRT', 'BODY', 'COMMON', 'shirts/shirt_1_common.png', 60, 'Simple everyday shirt'),
  ('Striped Tee', 'SHIRT', 'BODY', 'COMMON', 'shirts/shirt_2_common.png', 60, 'Casual striped tee'),
  ('Fancy Shirt', 'SHIRT', 'BODY', 'UNCOMMON', 'shirts/shirt_3_uncommon.png', 150, 'A nicer shirt'),
  ('Designer Top', 'SHIRT', 'BODY', 'RARE', 'shirts/shirt_5_rare.png', 350, 'High fashion'),
  ('Royal Garment', 'SHIRT', 'BODY', 'LEGENDARY', 'shirts/shirt_7_legendary.png', 800, 'Fit for royalty');

-- Wings (BACK slot)
INSERT INTO lg_items (name, category, slot, rarity, asset_path, gold_price, description) VALUES
  ('Angel Wings White', 'WINGS', 'BACK', 'RARE', 'wings/angel_wings__white_.png', 500, 'Pure white angel wings'),
  ('Bat Wings', 'WINGS', 'BACK', 'UNCOMMON', 'wings/bat_wings.png', 300, 'Dark bat wings'),
  ('Butterfly Wings', 'WINGS', 'BACK', 'RARE', 'wings/butterfly_wings.png', 500, 'Beautiful butterfly wings'),
  ('Dragon Wings', 'WINGS', 'BACK', 'LEGENDARY', 'wings/dragon_wings.png', 1200, 'Fearsome dragon wings'),
  ('Fire Wings', 'WINGS', 'BACK', 'MYTHICAL', 'wings/fire_wings.png', NULL, 'Only from drops');

-- Add default room as room_id 6
INSERT INTO lg_rooms (name, asset_prefix, has_furniture, gold_price) VALUES
  ('Starter Room', 'rooms/default', TRUE, NULL);

-- Update room 1 (Castle) to be free
UPDATE lg_rooms SET gold_price = NULL WHERE room_id = 1;

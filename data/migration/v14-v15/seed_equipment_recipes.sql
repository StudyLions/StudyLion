-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Generate crafting recipes for all equipment items.
--          Each recipe uses 2 materials from rarity-appropriate
--          pools, picked deterministically via MOD(itemid).
--          Existing scroll recipes are preserved.
-- ============================================================

DO $$
DECLARE
  equip RECORD;
  recipe_id INT;
  mats_hi INT[];
  mats_lo INT[];
  mat_a_id INT;
  mat_b_id INT;
  qty_a INT;
  qty_b INT;
  gold INT;
  n_hi INT;
  n_lo INT;
  idx_a INT;
  idx_b INT;
BEGIN
  FOR equip IN
    SELECT itemid, category, rarity FROM lg_items
    WHERE category IN ('HAT','GLASSES','BOOTS','SHIRT','WINGS','COSTUME')
      AND NOT EXISTS (
        SELECT 1 FROM lg_crafting_recipes WHERE result_itemid = lg_items.itemid
      )
    ORDER BY itemid
  LOOP
    CASE equip.rarity
      WHEN 'COMMON' THEN
        mats_hi := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'COMMON' ORDER BY itemid);
        mats_lo := mats_hi;
        qty_a := 5; qty_b := 3; gold := 30;
      WHEN 'UNCOMMON' THEN
        mats_hi := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'UNCOMMON' ORDER BY itemid);
        mats_lo := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'COMMON' ORDER BY itemid);
        qty_a := 3; qty_b := 4; gold := 80;
      WHEN 'RARE' THEN
        mats_hi := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'RARE' ORDER BY itemid);
        mats_lo := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'UNCOMMON' ORDER BY itemid);
        qty_a := 2; qty_b := 3; gold := 200;
      WHEN 'EPIC' THEN
        mats_hi := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'EPIC' ORDER BY itemid);
        mats_lo := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'RARE' ORDER BY itemid);
        qty_a := 2; qty_b := 2; gold := 500;
      WHEN 'LEGENDARY' THEN
        mats_hi := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'LEGENDARY' ORDER BY itemid);
        mats_lo := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'EPIC' ORDER BY itemid);
        qty_a := 2; qty_b := 1; gold := 1200;
      WHEN 'MYTHICAL' THEN
        mats_hi := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'MYTHICAL' ORDER BY itemid);
        mats_lo := ARRAY(SELECT itemid FROM lg_items WHERE category = 'MATERIAL' AND rarity = 'LEGENDARY' ORDER BY itemid);
        qty_a := 1; qty_b := 2; gold := 3000;
    END CASE;

    n_hi := array_length(mats_hi, 1);
    n_lo := array_length(mats_lo, 1);

    idx_a := 1 + (equip.itemid % n_hi);
    idx_b := 1 + ((equip.itemid * 7 + 13) % n_lo);

    mat_a_id := mats_hi[idx_a];
    mat_b_id := mats_lo[idx_b];

    IF mat_a_id = mat_b_id THEN
      idx_b := 1 + ((idx_b) % n_lo);
      mat_b_id := mats_lo[idx_b];
    END IF;

    INSERT INTO lg_crafting_recipes (result_itemid, result_quantity, gold_cost, description)
    VALUES (equip.itemid, 1, gold, '')
    RETURNING recipeid INTO recipe_id;

    INSERT INTO lg_recipe_ingredients (recipeid, itemid, quantity) VALUES
      (recipe_id, mat_a_id, qty_a),
      (recipe_id, mat_b_id, qty_b);
  END LOOP;
END $$;

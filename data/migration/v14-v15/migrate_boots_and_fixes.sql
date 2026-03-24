-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Add BOOTS category, migrate COSTUME/FEET items,
--          fix mis-categorized Superleo X1 and Set 4 items
-- ============================================================

BEGIN;

-- Add BOOTS to the item category enum
ALTER TYPE lgitemcategory ADD VALUE IF NOT EXISTS 'BOOTS';

COMMIT;

-- Enum changes require a separate transaction to take effect
BEGIN;

-- Migrate all COSTUME + FEET items to BOOTS
UPDATE lg_items SET category = 'BOOTS' WHERE category = 'COSTUME' AND slot = 'FEET';

-- Fix Superleo X1 "torso" items mis-categorized as GLASSES/FACE
-- These are body armor, should be SHIRT/BODY
UPDATE lg_items SET category = 'SHIRT', slot = 'BODY'
WHERE name LIKE '%torso superleo x1%' AND category = 'GLASSES';

-- Fix "set 4 hat" base item mis-categorized as SHIRT/BODY
UPDATE lg_items SET category = 'HAT', slot = 'HEAD'
WHERE name LIKE 'set 4 hat%' AND category = 'SHIRT';

COMMIT;

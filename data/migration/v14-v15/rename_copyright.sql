-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Rename copyrighted/branded item names to creative
--          alternatives. Only changes the 'name' column;
--          asset_path stays the same so blob images keep working.
--          Run AFTER seed_all_equipment.sql.
-- ============================================================

BEGIN;

-- Temporary mapping: old duplicated-name prefix -> new clean name
CREATE TEMP TABLE _rename_dup (old_prefix TEXT PRIMARY KEY, new_base TEXT NOT NULL);
INSERT INTO _rename_dup (old_prefix, new_base) VALUES
  -- One Piece
  ('luffy hat luffy hat',                       'Straw Pirate Hat'),
  ('luffy shirt luffy shirt',                   'Straw Pirate Vest'),
  -- Jujutsu Kaisen
  ('gojo blindfold gojo blindfold',             'Mystic Blindfold'),
  -- My Hero Academia
  ('froppy set hat froppy set hat',             'Frog Hero Hat'),
  ('froppy set torso froppy set torso',         'Frog Hero Suit'),
  ('froppy set boots froppy set boots',         'Frog Hero Boots'),
  ('uravity set torso uravity set torso',       'Zero-G Hero Suit'),
  ('uravity set boots uravity set boots',       'Zero-G Hero Boots'),
  -- Demon Slayer
  ('tanjiro kimono',                            'Checkered Flame Kimono'),
  ('zenitsu kimono',                            'Lightning Kimono'),
  ('inosuke mask',                              'Boar Mask'),
  ('rengoku hair wig rengoku hair wig',         'Flame Hair Wig'),
  ('sabito mask',                               'Fox Spirit Mask'),
  -- Attack on Titan
  ('aot shirt aot shirt',                       'Titan Scout Shirt'),
  ('scout uniform scout uniform',               'Scout Corps Uniform'),
  -- Persona
  ('makoto mask',                               'Phantom Thief Mask'),
  -- Bleach
  ('bleach hat 1 bleach hat 1',                 'Reaper Hat'),
  ('bleach mask 1 bleach mask 1',               'Reaper Mask'),
  -- Undertale
  ('sans jacket sans jacket',                   'Skeleton Hoodie'),
  -- Hollow Knight
  ('vessel mask vessel mask',                   'Hollow Vessel Mask');

-- Apply duplicated-name renames (handles base + rarity variants)
UPDATE lg_items i
SET name = TRIM(
  CASE
    WHEN i.name = r.old_prefix THEN r.new_base
    ELSE r.new_base || ' ' || TRIM(SUBSTRING(i.name FROM LENGTH(r.old_prefix) + 1))
  END
)
FROM _rename_dup r
WHERE i.name LIKE r.old_prefix || '%';

DROP TABLE _rename_dup;

-- Standalone items (no duplication pattern, exact matches)
UPDATE lg_items SET name = 'Patriot Shield'         WHERE name = 'captain america shield';
UPDATE lg_items SET name = 'Web-Slinger Mask'       WHERE name = 'spiderman mask';
UPDATE lg_items SET name = 'Iron Knight Helm'       WHERE name = 'iron man mask';
UPDATE lg_items SET name = 'Thunder Hammer'         WHERE name = 'thors hammer';
UPDATE lg_items SET name = 'Scarlet Sorceress Hat'  WHERE name = 'scarlet witch hat';
UPDATE lg_items SET name = 'Ninja Village Headband' WHERE name = 'naruto headband';
UPDATE lg_items SET name = 'Shriek Mask'            WHERE name = 'scream mask';
UPDATE lg_items SET name = 'Faceless Spirit Mask'   WHERE name = 'no face ghibli';
UPDATE lg_items SET name = 'Plumber Hat'            WHERE name = 'more mario hat';
UPDATE lg_items SET name = 'Plumber Costume'        WHERE name = 'more mario costume';
UPDATE lg_items SET name = 'Plumber Shoes'          WHERE name = 'more mario shoes';
UPDATE lg_items SET name = 'Ogre Face'              WHERE name = 'more shrek face';
UPDATE lg_items SET name = 'Ogre Costume'           WHERE name = 'more shrek costume';

COMMIT;

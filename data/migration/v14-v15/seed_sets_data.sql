-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Seed item set data (run after table creation)
-- ============================================================

BEGIN;

UPDATE lg_items SET set_id = NULL;
DELETE FROM lg_item_sets;
ALTER SEQUENCE lg_item_sets_set_id_seq RESTART WITH 1;

-- 3-piece: Frog Hero (hat + suit + boots)
INSERT INTO lg_item_sets (name, description) VALUES ('Frog Hero Set', 'A heroic frog-themed outfit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'Frog Hero Hat%' OR name LIKE 'Frog Hero Suit%' OR name LIKE 'Frog Hero Boots%';

-- 3-piece: Superleo X1 (6 colors)
INSERT INTO lg_item_sets (name, description) VALUES ('Superleo X1 Blue', 'Blue variant of the Superleo X1 superhero suit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'blue mask superleo x1%' OR name LIKE 'blue torso superleo x1%' OR name LIKE 'blue boots superleo x1%';

INSERT INTO lg_item_sets (name, description) VALUES ('Superleo X1 Gold', 'Gold variant of the Superleo X1 superhero suit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'gold mask superleo x1%' OR name LIKE 'gold torso superleo x1%' OR name LIKE 'gold boots superleo x1%';

INSERT INTO lg_item_sets (name, description) VALUES ('Superleo X1 Green', 'Green variant of the Superleo X1 superhero suit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'green mask superleo x1%' OR name LIKE 'green torso superleo x1%' OR name LIKE 'green boots superleo x1%';

INSERT INTO lg_item_sets (name, description) VALUES ('Superleo X1 Purple', 'Purple variant of the Superleo X1 superhero suit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'purple mask superleo x1%' OR name LIKE 'purple torso superleo x1%' OR name LIKE 'purple boots superleo x1%';

INSERT INTO lg_item_sets (name, description) VALUES ('Superleo X1 Red', 'Red variant of the Superleo X1 superhero suit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'red mask superleo x1%' OR name LIKE 'red torso superleo x1%' OR name LIKE 'red boots superleo x1%';

INSERT INTO lg_item_sets (name, description) VALUES ('Superleo X1 White', 'White variant of the Superleo X1 superhero suit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'white mask superleo x1%' OR name LIKE 'white torso superleo x1%' OR name LIKE 'white boots superleo x1%';

-- 3-piece: Plumber (hat + costume + shoes)
INSERT INTO lg_item_sets (name, description) VALUES ('Plumber Set', 'A plucky plumber costume');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('Plumber Hat', 'Plumber Costume', 'Plumber Shoes');

-- 3-piece: Knight (head + torso + shoes)
INSERT INTO lg_item_sets (name, description) VALUES ('Knight Set', 'Full knight armor from head to toe');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('more knight head', 'more knight torso', 'more knight shoes');

-- 3-piece: Astronaut (face + body + shoes)
INSERT INTO lg_item_sets (name, description) VALUES ('Astronaut Set', 'Ready for a space walk');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('more astraunaut face', 'more astrunatout', 'more astraunaut shoes');

-- 3-piece: Pirate (head + face + costume)
INSERT INTO lg_item_sets (name, description) VALUES ('Pirate Set', 'Arrr, a full pirate outfit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('more pirate head', 'more pirate face', 'more pirate costume');

-- 3-piece: Surgeon (head + face + costume)
INSERT INTO lg_item_sets (name, description) VALUES ('Surgeon Set', 'Scrubs, mask, and headgear');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('more surgeon head', 'more surgeon face', 'more surgeon costume');

-- 2-piece: Greenhead Boi
INSERT INTO lg_item_sets (name, description) VALUES ('Greenhead Boi Set', 'The mysterious greenhead boi');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'greenhead boi set mask%' OR name LIKE 'greenhead boi set torso%';

-- 2-piece: Set 4
INSERT INTO lg_item_sets (name, description) VALUES ('Set 4', 'Matching hat and torso');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set 4 hat%' OR name LIKE 'set 4 torso%';

-- 2-piece: Set 5
INSERT INTO lg_item_sets (name, description) VALUES ('Set 5', 'Matching hat and torso');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set 5 hat%' OR name LIKE 'set 5 torso%';

-- 2-piece: Set 6
INSERT INTO lg_item_sets (name, description) VALUES ('Set 6', 'Matching hat and torso');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set 6 hat%' OR name LIKE 'set 6 torso%';

-- 2-piece: Set A1-A5
INSERT INTO lg_item_sets (name, description) VALUES ('Set A1', 'Matching mask and torso');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set a1 mask%' OR name LIKE 'set a1 torso%';

INSERT INTO lg_item_sets (name, description) VALUES ('Set A2', 'Matching mask and torso');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set a2 mask%' OR name LIKE 'set a2 torso%';

INSERT INTO lg_item_sets (name, description) VALUES ('Set A3', 'Matching mask and torso');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set a3 mask%' OR name LIKE 'set a3 torso%';

INSERT INTO lg_item_sets (name, description) VALUES ('Set A4', 'Matching mask and torso');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set a4 mask%' OR name LIKE 'set a4 torso%';

INSERT INTO lg_item_sets (name, description) VALUES ('Set A5', 'Matching mask and torso');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set a5 mask%' OR name LIKE 'set a5 torso%';

-- 2-piece: Straw Pirate (hat + vest)
INSERT INTO lg_item_sets (name, description) VALUES ('Straw Pirate Set', 'A straw-hat pirate look');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'Straw Pirate Hat%' OR name LIKE 'Straw Pirate Vest%';

-- 2-piece: Reaper (hat + mask)
INSERT INTO lg_item_sets (name, description) VALUES ('Reaper Set', 'Soul reaper hat and mask');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'Reaper Hat%' OR name LIKE 'Reaper Mask%';

-- 2-piece: Ogre
INSERT INTO lg_item_sets (name, description) VALUES ('Ogre Set', 'Big green and grumpy');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('Ogre Face', 'Ogre Costume');

-- 2-piece: Ninja
INSERT INTO lg_item_sets (name, description) VALUES ('Ninja Set', 'Stealthy ninja gear');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('more ninja face', 'more ninja costume');

-- 2-piece: Witch
INSERT INTO lg_item_sets (name, description) VALUES ('Witch Set', 'Witchy hat and suit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('more witch hat', 'more witch suit');

-- 2-piece: Wizard
INSERT INTO lg_item_sets (name, description) VALUES ('Wizard Set', 'Wizardly hat and robes');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('more wizard hat', 'more wizard torso');

-- 2-piece: Viking
INSERT INTO lg_item_sets (name, description) VALUES ('Viking Set', 'Norse warrior gear');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('more viking face', 'more viking');

-- 2-piece: Nerd
INSERT INTO lg_item_sets (name, description) VALUES ('Nerd Set', 'Nerdy glasses and outfit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name IN ('more nerd school face', 'more nerd costume');

-- 2-piece: Set 1 (torso + boots)
INSERT INTO lg_item_sets (name, description) VALUES ('Set 1', 'Matching torso and boots');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set 1 torso%' OR name LIKE 'set 1 boots%';

-- 2-piece: Set 3 (torso + feet)
INSERT INTO lg_item_sets (name, description) VALUES ('Set 3', 'Matching torso and footwear');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set 3 torso%' OR name LIKE 'set 3 feet%';

-- 2-piece: Set 7 (torso + sandals)
INSERT INTO lg_item_sets (name, description) VALUES ('Set 7', 'Matching torso and sandals');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'set 7 torso%' OR name LIKE 'set 7 sandals%';

-- 2-piece: Zero-G Hero (suit + boots)
INSERT INTO lg_item_sets (name, description) VALUES ('Zero-G Hero Set', 'Anti-gravity hero outfit');
UPDATE lg_items SET set_id = currval('lg_item_sets_set_id_seq') WHERE name LIKE 'Zero-G Hero Suit%' OR name LIKE 'Zero-G Hero Boots%';

COMMIT;

-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Seed 131 material items for the crafting system
-- ============================================================

-- Clear any existing materials first
DELETE FROM lg_recipe_ingredients WHERE itemid IN (SELECT itemid FROM lg_items WHERE category = 'MATERIAL');
DELETE FROM lg_user_inventory WHERE itemid IN (SELECT itemid FROM lg_items WHERE category = 'MATERIAL');
DELETE FROM lg_items WHERE category = 'MATERIAL';

-- ==============================
-- COMMON (38 items)
-- ==============================

-- Botanicals
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Dandelion', 'MATERIAL', 'COMMON', 'materials/dandelion.png', true, 'A cheerful yellow flower that grows everywhere.'),
('Clover Leaf', 'MATERIAL', 'COMMON', 'materials/clover_leaf.png', true, 'A three-leaf clover. Maybe luck will come next time.'),
('Daisy Petal', 'MATERIAL', 'COMMON', 'materials/daisy_petal.png', true, 'Soft white petals from a common daisy.'),
('Dried Grass', 'MATERIAL', 'COMMON', 'materials/dried_grass.png', true, 'Sun-baked grass blades, surprisingly useful.'),
('Wild Mint', 'MATERIAL', 'COMMON', 'materials/wild_mint.png', true, 'Fresh-smelling mint leaves from the meadow.'),
('Chamomile', 'MATERIAL', 'COMMON', 'materials/chamomile.png', true, 'Calming flower, good for tea and crafting.'),
('Sunflower Seed', 'MATERIAL', 'COMMON', 'materials/sunflower_seed.png', true, 'A small striped seed full of potential.'),
('Lavender Sprig', 'MATERIAL', 'COMMON', 'materials/lavender_sprig.png', true, 'A fragrant purple sprig.');

-- Woods & Natural
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Twig', 'MATERIAL', 'COMMON', 'materials/twig.png', true, 'A small dry branch, snaps easily.'),
('Bark Strip', 'MATERIAL', 'COMMON', 'materials/bark_strip.png', true, 'A curled piece of tree bark.'),
('Pine Cone', 'MATERIAL', 'COMMON', 'materials/pine_cone.png', true, 'A woody pine cone from evergreen trees.'),
('Acorn', 'MATERIAL', 'COMMON', 'materials/acorn.png', true, 'A tiny oak seed in its cap.'),
('Driftwood Piece', 'MATERIAL', 'COMMON', 'materials/driftwood_piece.png', true, 'Smooth wood polished by the sea.'),
('Bamboo Shoot', 'MATERIAL', 'COMMON', 'materials/bamboo_shoot.png', true, 'A fresh green bamboo segment.'),
('Cork Chunk', 'MATERIAL', 'COMMON', 'materials/cork_chunk.png', true, 'Light, spongy cork bark.');

-- Fibers & Textiles
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Cotton Tuft', 'MATERIAL', 'COMMON', 'materials/cotton_tuft.png', true, 'A fluffy ball of raw cotton.'),
('Wool Puff', 'MATERIAL', 'COMMON', 'materials/wool_puff.png', true, 'Soft wool from a friendly sheep.'),
('Linen Thread', 'MATERIAL', 'COMMON', 'materials/linen_thread.png', true, 'A length of sturdy linen thread.'),
('Spider Silk Strand', 'MATERIAL', 'COMMON', 'materials/spider_silk_strand.png', true, 'Surprisingly strong gossamer strand.'),
('Hay Bundle', 'MATERIAL', 'COMMON', 'materials/hay_bundle.png', true, 'A small tied bundle of dried hay.');

-- Shells & Stones
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Pebble', 'MATERIAL', 'COMMON', 'materials/pebble.png', true, 'A smooth, round river pebble.'),
('Sand Dollar', 'MATERIAL', 'COMMON', 'materials/sand_dollar.png', true, 'A flat, star-patterned shell from the beach.'),
('Seashell', 'MATERIAL', 'COMMON', 'materials/seashell.png', true, 'A small spiral shell, pink inside.'),
('River Stone', 'MATERIAL', 'COMMON', 'materials/river_stone.png', true, 'A flat stone, perfect for skipping.'),
('Clay Ball', 'MATERIAL', 'COMMON', 'materials/clay_ball.png', true, 'A lump of soft, moldable clay.'),
('Chalk Piece', 'MATERIAL', 'COMMON', 'materials/chalk_piece.png', true, 'White chalk, leaves marks on everything.');

-- Animal
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Feather', 'MATERIAL', 'COMMON', 'materials/feather.png', true, 'A plain bird feather, slightly bent.'),
('Eggshell Fragment', 'MATERIAL', 'COMMON', 'materials/eggshell_fragment.png', true, 'A thin, curved piece of eggshell.'),
('Snail Shell', 'MATERIAL', 'COMMON', 'materials/snail_shell.png', true, 'An empty spiral snail shell.'),
('Bee Wax', 'MATERIAL', 'COMMON', 'materials/bee_wax.png', true, 'A small chunk of golden beeswax.');

-- Foods
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Honey Drop', 'MATERIAL', 'COMMON', 'materials/honey_drop.png', true, 'A thick, amber drop of honey.'),
('Berry', 'MATERIAL', 'COMMON', 'materials/berry.png', true, 'A small wild berry, deep purple.'),
('Mushroom Cap', 'MATERIAL', 'COMMON', 'materials/mushroom_cap.png', true, 'The cap of a common woodland mushroom.'),
('Wheat Grain', 'MATERIAL', 'COMMON', 'materials/wheat_grain.png', true, 'A single golden wheat kernel.');

-- Essences
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Morning Dew Drop', 'MATERIAL', 'COMMON', 'materials/morning_dew_drop.png', true, 'A glistening droplet from dawn grass.'),
('Rainwater Vial', 'MATERIAL', 'COMMON', 'materials/rainwater_vial.png', true, 'Pure water caught during a gentle rain.'),
('Dandelion Wish', 'MATERIAL', 'COMMON', 'materials/dandelion_wish.png', true, 'A tiny seed carried by the wind.');

-- Study-themed
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Ink Drop', 'MATERIAL', 'COMMON', 'materials/ink_drop.png', true, 'A small blob of black ink.'),
('Paper Scrap', 'MATERIAL', 'COMMON', 'materials/paper_scrap.png', true, 'A torn piece of parchment.');

-- ==============================
-- UNCOMMON (34 items)
-- ==============================

-- Botanicals
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Rose Petal', 'MATERIAL', 'UNCOMMON', 'materials/rose_petal.png', true, 'A velvety red petal, still fragrant.'),
('Bluebell', 'MATERIAL', 'UNCOMMON', 'materials/bluebell.png', true, 'A delicate bell-shaped woodland flower.'),
('Jasmine Bud', 'MATERIAL', 'UNCOMMON', 'materials/jasmine_bud.png', true, 'A sweet-scented white bud.'),
('Sage Bundle', 'MATERIAL', 'UNCOMMON', 'materials/sage_bundle.png', true, 'Dried sage leaves tied with twine.'),
('Thyme Sprig', 'MATERIAL', 'UNCOMMON', 'materials/thyme_sprig.png', true, 'A tiny stem of aromatic thyme.'),
('Ivy Vine', 'MATERIAL', 'UNCOMMON', 'materials/ivy_vine.png', true, 'A curling green vine with heart-shaped leaves.');

-- Woods & Natural
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Birch Bark', 'MATERIAL', 'UNCOMMON', 'materials/birch_bark.png', true, 'Papery white bark that peels in layers.'),
('Maple Sap', 'MATERIAL', 'UNCOMMON', 'materials/maple_sap.png', true, 'Thick, sweet sap from a maple tree.'),
('Willow Branch', 'MATERIAL', 'UNCOMMON', 'materials/willow_branch.png', true, 'A supple, bendable willow withe.'),
('Cedar Shaving', 'MATERIAL', 'UNCOMMON', 'materials/cedar_shaving.png', true, 'A thin curl of aromatic cedar wood.'),
('Mossy Stone', 'MATERIAL', 'UNCOMMON', 'materials/mossy_stone.png', true, 'A stone coated in soft green moss.');

-- Fibers & Textiles
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Silk Thread', 'MATERIAL', 'UNCOMMON', 'materials/silk_thread.png', true, 'Smooth, lustrous thread from silkworms.'),
('Velvet Scrap', 'MATERIAL', 'UNCOMMON', 'materials/velvet_scrap.png', true, 'A small piece of plush velvet fabric.'),
('Felt Patch', 'MATERIAL', 'UNCOMMON', 'materials/felt_patch.png', true, 'A thick, warm square of felted wool.'),
('Satin Ribbon', 'MATERIAL', 'UNCOMMON', 'materials/satin_ribbon.png', true, 'A glossy, smooth ribbon.');

-- Shells & Stones
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Pearl Fragment', 'MATERIAL', 'UNCOMMON', 'materials/pearl_fragment.png', true, 'A small piece of iridescent pearl.'),
('Quartz Chip', 'MATERIAL', 'UNCOMMON', 'materials/quartz_chip.png', true, 'A translucent piece of rose quartz.'),
('Amber Bead', 'MATERIAL', 'UNCOMMON', 'materials/amber_bead.png', true, 'Ancient tree resin, golden and warm.'),
('Coral Piece', 'MATERIAL', 'UNCOMMON', 'materials/coral_piece.png', true, 'A branching fragment of ocean coral.'),
('Sea Glass', 'MATERIAL', 'UNCOMMON', 'materials/sea_glass.png', true, 'Frosted glass tumbled smooth by waves.');

-- Animal
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Owl Feather', 'MATERIAL', 'UNCOMMON', 'materials/owl_feather.png', true, 'A soft, silent feather from an owl.'),
('Fox Fur Tuft', 'MATERIAL', 'UNCOMMON', 'materials/fox_fur_tuft.png', true, 'A tiny tuft of reddish-orange fur.'),
('Firefly Glow', 'MATERIAL', 'UNCOMMON', 'materials/firefly_glow.png', true, 'Bottled bioluminescence from a firefly.'),
('Hummingbird Feather', 'MATERIAL', 'UNCOMMON', 'materials/hummingbird_feather.png', true, 'A tiny iridescent feather.');

-- Foods
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Honeycomb', 'MATERIAL', 'UNCOMMON', 'materials/honeycomb.png', true, 'A perfect hexagonal wax comb.'),
('Truffle Shaving', 'MATERIAL', 'UNCOMMON', 'materials/truffle_shaving.png', true, 'A thin slice of earthy truffle.'),
('Maple Syrup Drop', 'MATERIAL', 'UNCOMMON', 'materials/maple_syrup_drop.png', true, 'Concentrated sweetness from maple.'),
('Cocoa Bean', 'MATERIAL', 'UNCOMMON', 'materials/cocoa_bean.png', true, 'A roasted bean with rich aroma.');

-- Essences
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Moonlight Essence', 'MATERIAL', 'UNCOMMON', 'materials/moonlight_essence.png', true, 'Bottled silver glow from a full moon.'),
('Starlight Dust', 'MATERIAL', 'UNCOMMON', 'materials/starlight_dust.png', true, 'Faintly glowing particles from the night sky.'),
('Rainbow Mist', 'MATERIAL', 'UNCOMMON', 'materials/rainbow_mist.png', true, 'Captured prismatic droplets from a rainbow.');

-- Study-themed
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Quill Nib', 'MATERIAL', 'UNCOMMON', 'materials/quill_nib.png', true, 'A sharp metal nib for a writing quill.'),
('Wax Seal', 'MATERIAL', 'UNCOMMON', 'materials/wax_seal.png', true, 'A stamped disc of red sealing wax.'),
('Old Map Fragment', 'MATERIAL', 'UNCOMMON', 'materials/old_map_fragment.png', true, 'A torn corner of an ancient map.');

-- ==============================
-- RARE (24 items)
-- ==============================

-- Botanicals
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Orchid Bloom', 'MATERIAL', 'RARE', 'materials/orchid_bloom.png', true, 'An exotic flower in vivid purple.'),
('Moonflower', 'MATERIAL', 'RARE', 'materials/moonflower.png', true, 'A pale flower that only blooms at night.'),
('Cherry Blossom', 'MATERIAL', 'RARE', 'materials/cherry_blossom.png', true, 'A delicate pink blossom from spring.'),
('Lotus Petal', 'MATERIAL', 'RARE', 'materials/lotus_petal.png', true, 'A pristine petal from a floating lotus.'),
('Golden Poppy', 'MATERIAL', 'RARE', 'materials/golden_poppy.png', true, 'A brilliant gold wildflower.');

-- Woods & Natural
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Petrified Wood', 'MATERIAL', 'RARE', 'materials/petrified_wood.png', true, 'Ancient wood turned to stone over millennia.'),
('Ancient Bark', 'MATERIAL', 'RARE', 'materials/ancient_bark.png', true, 'Bark from a tree hundreds of years old.'),
('Bonsai Cutting', 'MATERIAL', 'RARE', 'materials/bonsai_cutting.png', true, 'A tiny branch from a carefully tended bonsai.');

-- Fibers & Textiles
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Golden Thread', 'MATERIAL', 'RARE', 'materials/golden_thread.png', true, 'Thread spun from actual gold fibers.'),
('Moonwoven Silk', 'MATERIAL', 'RARE', 'materials/moonwoven_silk.png', true, 'Silk woven under moonlight, faintly luminous.');

-- Shells & Stones
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Moonstone Shard', 'MATERIAL', 'RARE', 'materials/moonstone_shard.png', true, 'A shard with an ethereal blue sheen.'),
('Amethyst Chip', 'MATERIAL', 'RARE', 'materials/amethyst_chip.png', true, 'A small purple crystal fragment.'),
('Jade Fragment', 'MATERIAL', 'RARE', 'materials/jade_fragment.png', true, 'A smooth green piece of jade.'),
('Opal Sliver', 'MATERIAL', 'RARE', 'materials/opal_sliver.png', true, 'A thin slice of fire opal, shifting colors.');

-- Animal
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Peacock Plume', 'MATERIAL', 'RARE', 'materials/peacock_plume.png', true, 'An iridescent feather with an eye pattern.'),
('Dragonfly Wing', 'MATERIAL', 'RARE', 'materials/dragonfly_wing.png', true, 'A translucent, veined wing.'),
('Unicorn Hair', 'MATERIAL', 'RARE', 'materials/unicorn_hair.png', true, 'A single shimmering hair from a unicorn mane.');

-- Foods
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Royal Jelly', 'MATERIAL', 'RARE', 'materials/royal_jelly.png', true, 'Precious substance from the queen bee.'),
('Crystal Honey', 'MATERIAL', 'RARE', 'materials/crystal_honey.png', true, 'Honey that has crystallized into gemlike form.');

-- Essences
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Bottled Sunshine', 'MATERIAL', 'RARE', 'materials/bottled_sunshine.png', true, 'Warm golden light trapped in glass.'),
('Frozen Tear', 'MATERIAL', 'RARE', 'materials/frozen_tear.png', true, 'A crystallized teardrop, cold to the touch.'),
('Lightning in a Bottle', 'MATERIAL', 'RARE', 'materials/lightning_in_a_bottle.png', true, 'A crackling spark of captured lightning.');

-- Study-themed
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Ancient Scroll Fragment', 'MATERIAL', 'RARE', 'materials/ancient_scroll_fragment.png', true, 'Yellowed parchment with faded writing.'),
('Enchanted Ink', 'MATERIAL', 'RARE', 'materials/enchanted_ink.png', true, 'Ink that shimmers and shifts color as it dries.');

-- ==============================
-- EPIC (17 items)
-- ==============================

-- Botanicals
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Night Bloom', 'MATERIAL', 'EPIC', 'materials/night_bloom.png', true, 'A flower that glows faintly in the dark.'),
('Aurora Petal', 'MATERIAL', 'EPIC', 'materials/aurora_petal.png', true, 'A petal that shifts through northern-lights colors.'),
('Starflower', 'MATERIAL', 'EPIC', 'materials/starflower.png', true, 'A tiny flower shaped like a five-pointed star.');

-- Woods & Natural
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Enchanted Driftwood', 'MATERIAL', 'EPIC', 'materials/enchanted_driftwood.png', true, 'Driftwood that hums with faint energy.'),
('Crystal Bark', 'MATERIAL', 'EPIC', 'materials/crystal_bark.png', true, 'Bark that has partially turned to crystal.');

-- Fibers & Textiles
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Starweave Fiber', 'MATERIAL', 'EPIC', 'materials/starweave_fiber.png', true, 'Thread that sparkles like the night sky.'),
('Dreamcloth', 'MATERIAL', 'EPIC', 'materials/dreamcloth.png', true, 'Fabric woven from sleeping thoughts.');

-- Shells & Stones
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Star Sapphire Dust', 'MATERIAL', 'EPIC', 'materials/star_sapphire_dust.png', true, 'Ground sapphire that shows a star pattern.'),
('Diamond Dust', 'MATERIAL', 'EPIC', 'materials/diamond_dust.png', true, 'Glittering powder of crushed diamonds.'),
('Sunstone', 'MATERIAL', 'EPIC', 'materials/sunstone.png', true, 'An orange gem that feels warm to the touch.');

-- Animal
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Griffin Feather', 'MATERIAL', 'EPIC', 'materials/griffin_feather.png', true, 'A huge golden-brown feather from a griffin.'),
('Dragon Whisker', 'MATERIAL', 'EPIC', 'materials/dragon_whisker.png', true, 'A thin, heat-resistant dragon whisker.');

-- Foods
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Ambrosia Drop', 'MATERIAL', 'EPIC', 'materials/ambrosia_drop.png', true, 'A single drop of food fit for the gods.'),
('Golden Nectar', 'MATERIAL', 'EPIC', 'materials/golden_nectar.png', true, 'Concentrated flower nectar that glows.');

-- Essences
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Essence of Dawn', 'MATERIAL', 'EPIC', 'materials/essence_of_dawn.png', true, 'The first light of sunrise, bottled.'),
('Liquid Starlight', 'MATERIAL', 'EPIC', 'materials/liquid_starlight.png', true, 'Starlight condensed into a flowing liquid.');

-- Study-themed
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Knowledge Tome Page', 'MATERIAL', 'EPIC', 'materials/knowledge_tome_page.png', true, 'A page from an ancient book of wisdom.');

-- ==============================
-- LEGENDARY (11 items)
-- ==============================

-- Botanicals
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Ethereal Orchid', 'MATERIAL', 'LEGENDARY', 'materials/ethereal_orchid.png', true, 'A semi-transparent orchid that phases in and out.'),
('Dreamvine', 'MATERIAL', 'LEGENDARY', 'materials/dreamvine.png', true, 'A vine that only grows in the dreams of sleeping forests.');

-- Woods & Natural
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Heartwood', 'MATERIAL', 'LEGENDARY', 'materials/heartwood.png', true, 'The living core of an ancient guardian tree.');

-- Fibers & Textiles
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Celestial Thread', 'MATERIAL', 'LEGENDARY', 'materials/celestial_thread.png', true, 'Thread said to be spun from a comet tail.');

-- Shells & Stones
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Philosopher''s Stone Shard', 'MATERIAL', 'LEGENDARY', 'materials/philosophers_stone_shard.png', true, 'A fragment of the legendary transmutation stone.'),
('Void Crystal', 'MATERIAL', 'LEGENDARY', 'materials/void_crystal.png', true, 'A crystal that seems to absorb all light around it.');

-- Animal
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Phoenix Feather', 'MATERIAL', 'LEGENDARY', 'materials/phoenix_feather.png', true, 'A feather that is always warm, never burns.'),
('Kitsune Tail Fur', 'MATERIAL', 'LEGENDARY', 'materials/kitsune_tail_fur.png', true, 'Magical fur from the tail of a nine-tailed fox.');

-- Essences
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Bottled Aurora', 'MATERIAL', 'LEGENDARY', 'materials/bottled_aurora.png', true, 'The northern lights captured in a bottle.'),
('Time Sand', 'MATERIAL', 'LEGENDARY', 'materials/time_sand.png', true, 'Sand from an hourglass that measures eternity.');

-- Study-themed
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('Philosopher''s Notes', 'MATERIAL', 'LEGENDARY', 'materials/philosophers_notes.png', true, 'Handwritten notes from a great thinker, still warm with ideas.');

-- ==============================
-- MYTHICAL (7 items)
-- ==============================
INSERT INTO lg_items (name, category, rarity, asset_path, tradeable, description) VALUES
('World Tree Leaf', 'MATERIAL', 'MYTHICAL', 'materials/world_tree_leaf.png', true, 'A leaf from the tree that holds the world together.'),
('Yggdrasil Splinter', 'MATERIAL', 'MYTHICAL', 'materials/yggdrasil_splinter.png', true, 'A sliver from the cosmic world-tree.'),
('Cosmic Gem', 'MATERIAL', 'MYTHICAL', 'materials/cosmic_gem.png', true, 'A gemstone forged in the heart of a dying star.'),
('Celestial Feather', 'MATERIAL', 'MYTHICAL', 'materials/celestial_feather.png', true, 'A feather from a creature that flies between worlds.'),
('Essence of Infinity', 'MATERIAL', 'MYTHICAL', 'materials/essence_of_infinity.png', true, 'A drop of liquid that somehow contains everything.'),
('Cosmic Dust', 'MATERIAL', 'MYTHICAL', 'materials/cosmic_dust.png', true, 'Dust from the birth of the universe itself.'),
('Stardust Crown Fragment', 'MATERIAL', 'MYTHICAL', 'materials/stardust_crown_fragment.png', true, 'A piece of a crown made from condensed starlight.');

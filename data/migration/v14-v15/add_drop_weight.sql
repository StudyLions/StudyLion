-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-17
-- Purpose: Add per-item drop_weight for weighted random drops
--          (lower = rarer within same rarity tier)
-- ============================================================

ALTER TABLE lg_items ADD COLUMN IF NOT EXISTS drop_weight REAL NOT NULL DEFAULT 1.0;

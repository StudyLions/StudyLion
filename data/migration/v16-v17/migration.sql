-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-17
-- Purpose: Migration v16 -> v17
--          Add user_card_preferences table for LionHeart
--          animated card effect customization
-- ============================================================

CREATE TABLE IF NOT EXISTS user_card_preferences(
  userid BIGINT PRIMARY KEY,
  effects_enabled BOOLEAN NOT NULL DEFAULT true,
  sparkle_color TEXT,
  ring_color TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

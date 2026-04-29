-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-04-29
-- Purpose: Add setup_checklist_state column to guild_config for the
--          Dashboard Setup Checklist redesign. Bot does NOT read this
--          column -- dashboard-only state. Safe to apply at any time.
--
--          Also stamps any guild that already dismissed the legacy setup
--          wizard as "all 8 tasks skipped" so existing admins don't
--          suddenly see a fresh checklist demanding their attention.
--
-- Apply order:
--   1. studylion_test (free to run)
--   2. studylion (LIVE -- requires Ari's explicit approval per CONTEXT.md)
-- ============================================================

ALTER TABLE guild_config
  ADD COLUMN IF NOT EXISTS setup_checklist_state JSONB;

-- Mark legacy dismissed servers as all-tasks-skipped so they keep their
-- "I've already set this up" state. Uses jsonb_build_object so the
-- statement is idempotent (re-running won't double-write).
UPDATE guild_config
SET setup_checklist_state = jsonb_build_object(
    'essentials',    'skipped',
    'ranks',         'skipped',
    'rewards',       'skipped',
    'welcome',       'skipped',
    'notifications', 'skipped',
    'focus',         'skipped',
    'schedule',      'skipped',
    'pet',           'skipped'
  )
WHERE setup_wizard_dismissed_at IS NOT NULL
  AND setup_checklist_state IS NULL;

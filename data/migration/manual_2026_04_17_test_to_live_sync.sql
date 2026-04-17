-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-04-17
-- Purpose: One-shot migration to bring the studylion (live) DB
--          up to parity with studylion_test (staging) for the
--          additive changes that landed since the last sync.
--          Intentionally SKIPS items that would weaken live
--          (e.g. removing useful indexes / FKs / CHECK
--          constraints that exist on live but not on test).
-- ============================================================

BEGIN;

-- 1. study_time_between: defensive guard so a swapped/equal range returns 0
--    instead of a NULL or a corrupted EPOCH calc.
CREATE OR REPLACE FUNCTION public.study_time_between(
  _guildid bigint, _userid bigint,
  _start timestamp with time zone, _end timestamp with time zone
) RETURNS integer
LANGUAGE plpgsql
AS $$
  BEGIN
    IF _start >= _end THEN
      RETURN 0;
    END IF;
    RETURN (
      SELECT
        SUM(COALESCE(EXTRACT(EPOCH FROM (upper(part) - lower(part))), 0))
      FROM (
        SELECT
        unnest(range_agg(tstzrange(start_time, end_time)) * multirange(tstzrange(_start, _end))) AS part
        FROM voice_sessions_combined
        WHERE
          (_guildid IS NULL OR guildid=_guildid)
          AND userid=_userid
          AND start_time < _end
          AND end_time > _start
      ) AS disjoint_parts
    );
  END;
$$;

-- 2. study_time_since: defensive guard so a future timestamp returns 0
--    instead of a negative integer.
CREATE OR REPLACE FUNCTION public.study_time_since(
  _guildid bigint, _userid bigint,
  _timestamp timestamp with time zone
) RETURNS integer
LANGUAGE plpgsql
AS $$
  BEGIN
    IF _timestamp > NOW() THEN
      RETURN 0;
    END IF;
    RETURN (SELECT study_time_between(_guildid, _userid, _timestamp, NOW()));
  END;
$$;

-- 3. dashboard_admin_audit: new table for the dashboard's "Reset Member Stats"
--    feature audit log. Already exists on studylion_test (applied earlier).
CREATE TABLE IF NOT EXISTS dashboard_admin_audit (
    auditid       BIGSERIAL PRIMARY KEY,
    performed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_userid  BIGINT NOT NULL,
    guildid       BIGINT NOT NULL,
    target_userid BIGINT NOT NULL,
    action_type   VARCHAR(64) NOT NULL,
    selections    JSONB NOT NULL,
    time_frame    JSONB,
    reason        TEXT NOT NULL,
    result        JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dashboard_admin_audit_guild_target
    ON dashboard_admin_audit (guildid, target_userid);

CREATE INDEX IF NOT EXISTS idx_dashboard_admin_audit_actor
    ON dashboard_admin_audit (actor_userid);

CREATE INDEX IF NOT EXISTS idx_dashboard_admin_audit_time
    ON dashboard_admin_audit (performed_at);

-- 4. leaderboard_autopost_config: 3 new columns powering the dashboard
--    "Top 1 DM" feature (separate template + opt-in toggle).
ALTER TABLE leaderboard_autopost_config
    ADD COLUMN IF NOT EXISTS top1_dm_enabled boolean DEFAULT false NOT NULL,
    ADD COLUMN IF NOT EXISTS top1_dm_template_title character varying(256),
    ADD COLUMN IF NOT EXISTS top1_dm_template_body character varying(4096);

-- 5. lofi_play_history: index to make per-guild history lookups fast
--    (used by the SoundsBot dashboard play history view).
CREATE INDEX IF NOT EXISTS idx_lofi_play_history_guild
    ON lofi_play_history (guildid, played_at DESC);

-- 6. lofi_blacklist: enforce one row per (guildid, song_filename).
--    Verified live data has zero duplicates.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'lofi_blacklist_guildid_song_filename_key'
  ) THEN
    ALTER TABLE lofi_blacklist
      ADD CONSTRAINT lofi_blacklist_guildid_song_filename_key
      UNIQUE (guildid, song_filename);
  END IF;
END$$;

-- 7. lg_user_gameboy_skins: add referential integrity to the gameboy skin
--    catalog and user_config. Verified live data has zero orphans.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'lg_user_gameboy_skins_skin_id_fkey'
  ) THEN
    ALTER TABLE lg_user_gameboy_skins
      ADD CONSTRAINT lg_user_gameboy_skins_skin_id_fkey
      FOREIGN KEY (skin_id) REFERENCES lg_gameboy_skins(skin_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'lg_user_gameboy_skins_userid_fkey'
  ) THEN
    ALTER TABLE lg_user_gameboy_skins
      ADD CONSTRAINT lg_user_gameboy_skins_userid_fkey
      FOREIGN KEY (userid) REFERENCES user_config(userid);
  END IF;
END$$;

-- 8. varchar caps -- mirror the test schema's tighter limits. Verified
--    no live row currently exceeds these lengths, so the type narrow is
--    a no-op for existing data and only constrains future writes.
ALTER TABLE data_deletion_requests
    ALTER COLUMN approval_token TYPE varchar(128);

ALTER TABLE guild_config
    ALTER COLUMN lg_guild_display_name TYPE varchar(12);

ALTER TABLE lg_items
    ALTER COLUMN tag TYPE varchar(32);

ALTER TABLE sounds_bot_heartbeat
    ALTER COLUMN bot_username TYPE varchar(50);

COMMIT;

-- Sanity check after commit
\echo '=== Post-migration sanity ==='
\echo '--- dashboard_admin_audit row count (should be 0) ---'
SELECT COUNT(*) FROM dashboard_admin_audit;
\echo '--- leaderboard_autopost_config has new cols (should list 3) ---'
SELECT column_name FROM information_schema.columns
WHERE table_name = 'leaderboard_autopost_config'
  AND column_name LIKE 'top1_dm_%'
ORDER BY column_name;
\echo '--- lg_user_gameboy_skins constraints ---'
SELECT conname FROM pg_constraint
WHERE conrelid = 'lg_user_gameboy_skins'::regclass
ORDER BY conname;

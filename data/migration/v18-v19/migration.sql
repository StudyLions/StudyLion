-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-05-19
-- Purpose: Migration v18 -> v19
--          Adds schema for the "LionGotchi for Anki" desktop
--          addon integration.
--
--          The addon pairs to a user's Discord account via a
--          paste-back PKCE flow on the website, then submits
--          review events to /api/anki/reviews (on the WEBSITE,
--          not the bot's aiohttp server). The bot never opens a
--          new public port for this feature.
--
--          All operations are additive and idempotent — re-running
--          this migration on a database that already has parts
--          applied is safe.
-- ============================================================

-- 1. Extend the ExperienceType ENUM so Anki reviews can write
--    member_experience rows with exp_type = 'ANKI_XP' (used for
--    rank-role progression / level-ups). The Anki LEADERBOARD,
--    however, reads from anki_review_events directly so it doesn't
--    inflate the existing "text" leaderboard which sums all XP
--    types.
ALTER TYPE ExperienceType ADD VALUE IF NOT EXISTS 'ANKI_XP';

-- 1b. Extend the LGGoldTransactionType ENUM so the website can
--     write lg_gold_transactions rows attributed to Anki review
--     batches. The bot's existing gold-balance queries are
--     transaction-type-agnostic so they just pick up the new
--     rows without code changes. The Python enum in the bot is
--     updated at Stage 3 when the rest of the bot code ships.
ALTER TYPE LGGoldTransactionType ADD VALUE IF NOT EXISTS 'ANKI_REVIEW';

-- 2. Devices: one row per paired addon install. Long-lived.
--    refresh_token_hash + refresh_token_version is the classic
--    refresh-token-rotation-with-reuse-detection pattern: each
--    refresh rotates both. Submitting an already-rotated refresh
--    token is treated as evidence of token theft and the device
--    is revoked.
CREATE TABLE IF NOT EXISTS anki_devices (
  device_id              UUID PRIMARY KEY,
  userid                 BIGINT NOT NULL REFERENCES user_config(userid) ON DELETE CASCADE,
  device_name            TEXT NOT NULL CHECK (char_length(device_name) <= 64),
  refresh_token_hash     BYTEA NOT NULL,
  refresh_token_version  INTEGER NOT NULL DEFAULT 1,
  jwt_version            TEXT NOT NULL,
  scopes                 TEXT[] NOT NULL DEFAULT ARRAY['anki.review.write','anki.pet.read'],
  addon_version          TEXT,
  os_platform            TEXT,
  anki_version           TEXT,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_ip_prefix         INET,
  revoked_at             TIMESTAMPTZ,
  revoked_reason         TEXT
);
CREATE INDEX IF NOT EXISTS anki_devices_active_userid
  ON anki_devices(userid) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS anki_devices_last_seen
  ON anki_devices(last_seen_at);

-- 2b. Previous refresh-token hash (one back). On rotate we snapshot
--     the old hash here; on a refresh MISMATCH we revoke the device
--     ONLY if the presented token matches this previous hash (a
--     genuine stale-token replay = theft). A token matching neither
--     the current nor the previous hash is just wrong/garbage and
--     gets a plain 401 with no revoke — this stops a "knows your
--     device_id, posts garbage" attacker from force-revoking you.
ALTER TABLE anki_devices
  ADD COLUMN IF NOT EXISTS prev_refresh_token_hash BYTEA;

-- 3. Pairing codes: short-lived (5 minute TTL), single-use.
--    code_hash is sha256(code) — we never store the plaintext
--    pairing code at rest. PKCE binding (code_challenge) ties the
--    redemption to the addon's secret code_verifier.
CREATE TABLE IF NOT EXISTS anki_pairing_codes (
  code_hash      BYTEA PRIMARY KEY,
  userid         BIGINT NOT NULL,
  device_id      UUID NOT NULL,
  device_name    TEXT,
  code_challenge TEXT NOT NULL,
  state          TEXT NOT NULL,
  expires_at     TIMESTAMPTZ NOT NULL,
  consumed       BOOLEAN NOT NULL DEFAULT FALSE,
  consumed_at    TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS anki_pairing_codes_unconsumed
  ON anki_pairing_codes(expires_at) WHERE consumed = FALSE;

-- 4. Review events: one row per flashcard review accepted from
--    the addon. review_id is a server-recomputed sha256 hash so
--    a client cannot forge collisions. The UNIQUE constraint on
--    PRIMARY KEY blocks the "same review submitted twice" case
--    that happens when an Anki collection syncs across machines.
CREATE TABLE IF NOT EXISTS anki_review_events (
  review_id      BYTEA PRIMARY KEY,
  userid         BIGINT NOT NULL,
  device_id      UUID NOT NULL REFERENCES anki_devices(device_id) ON DELETE CASCADE,
  guildid        BIGINT NOT NULL,
  anki_user_guid TEXT NOT NULL,
  card_id        BIGINT NOT NULL,
  deck_id        BIGINT,
  ease           SMALLINT NOT NULL CHECK (ease BETWEEN 1 AND 4),
  time_ms        INTEGER NOT NULL CHECK (time_ms BETWEEN 0 AND 60000),
  reviewed_at    TIMESTAMPTZ NOT NULL,
  ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  reward_gold    INTEGER NOT NULL DEFAULT 0,
  reward_xp      INTEGER NOT NULL DEFAULT 0,
  was_throttled  BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS anki_review_events_user_time
  ON anki_review_events(userid, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS anki_review_events_guild_time
  ON anki_review_events(guildid, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS anki_review_events_ingested
  ON anki_review_events(ingested_at);

-- 5. Batch-level idempotency: replayed POSTs return the prior
--    stored response instead of double-crediting. 24h retention.
CREATE TABLE IF NOT EXISTS anki_batch_idempotency (
  device_id       UUID NOT NULL,
  idempotency_key UUID NOT NULL,
  response_body   JSONB NOT NULL,
  status_code     INTEGER NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (device_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS anki_batch_idempotency_created
  ON anki_batch_idempotency(created_at);

-- 6. User config: home guild for Anki review attribution. NULL =
--    fall back to support guild (resolved at ingest time, not
--    persisted at NULL state).
ALTER TABLE user_config
  ADD COLUMN IF NOT EXISTS anki_home_guildid BIGINT;

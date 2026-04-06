-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-04-01
-- Purpose: Text Branding -- guild text overrides for premium
--          server admins to customize all bot messages
-- ============================================================

-- Per-guild text string overrides, keyed by gettext context string.
-- Resolution: guild override -> locale translation -> English default.
CREATE TABLE IF NOT EXISTS guild_text_overrides (
    guildid         BIGINT NOT NULL REFERENCES guild_config(guildid) ON DELETE CASCADE,
    text_key        TEXT NOT NULL,
    domain          TEXT NOT NULL,
    custom_text     TEXT NOT NULL,
    custom_text_plural TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      BIGINT,
    PRIMARY KEY (guildid, text_key)
);

CREATE INDEX IF NOT EXISTS idx_guild_text_overrides_guild
    ON guild_text_overrides(guildid);

-- Backup snapshots for import/export/restore of text customizations.
CREATE TABLE IF NOT EXISTS text_override_backups (
    backup_id       SERIAL PRIMARY KEY,
    guildid         BIGINT NOT NULL REFERENCES guild_config(guildid) ON DELETE CASCADE,
    backup_name     TEXT NOT NULL,
    backup_data     JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      BIGINT
);

CREATE INDEX IF NOT EXISTS idx_text_override_backups_guild
    ON text_override_backups(guildid);

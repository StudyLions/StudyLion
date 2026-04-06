-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-04-06
-- Purpose: Schema for Anti AFK System config table
-- ============================================================

CREATE TABLE IF NOT EXISTS anti_afk_config (
    guildid BIGINT PRIMARY KEY REFERENCES guild_config(guildid),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    check_interval INTEGER NOT NULL DEFAULT 60,
    grace_period INTEGER NOT NULL DEFAULT 5,
    action TEXT NOT NULL DEFAULT 'kick',
    max_warnings INTEGER NOT NULL DEFAULT 1,
    min_users INTEGER NOT NULL DEFAULT 1,
    warning_message TEXT NOT NULL DEFAULT 'Are you still studying?',
    exempt_roles TEXT NOT NULL DEFAULT '[]',
    target_channels TEXT NOT NULL DEFAULT '[]',
    exclude_channels TEXT NOT NULL DEFAULT '[]',
    use_dms BOOLEAN NOT NULL DEFAULT FALSE,
    fallback_channelid BIGINT,
    skip_streaming BOOLEAN NOT NULL DEFAULT TRUE,
    notify_on_action BOOLEAN NOT NULL DEFAULT TRUE,
    notification_channelid BIGINT,
    max_actions_per_hour INTEGER NOT NULL DEFAULT 100
);

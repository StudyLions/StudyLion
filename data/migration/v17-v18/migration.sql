-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-31
-- Purpose: Migration v17 -> v18
--          Add screen share enforcement tables and columns
--          for the screen_channels module (mirrors video_channels)
-- ============================================================

-- New tables (mirroring video_channels structure)
CREATE TABLE IF NOT EXISTS screen_channels(
  guildid BIGINT NOT NULL,
  channelid BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS screen_channels_guilds ON screen_channels (guildid);

CREATE TABLE IF NOT EXISTS screen_exempt_roles(
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  _timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE ON UPDATE CASCADE,
  PRIMARY KEY (guildid, roleid)
);

CREATE TABLE IF NOT EXISTS screenban_durations(
  rowid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  duration INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS screenban_durations_guilds ON screenban_durations (guildid);

-- New columns on guild_config
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS screenban_role BIGINT;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS screen_grace_period INTEGER;

-- New column on members
ALTER TABLE members ADD COLUMN IF NOT EXISTS screen_warned BOOLEAN DEFAULT FALSE;

-- New ticket type
ALTER TYPE TicketType ADD VALUE IF NOT EXISTS 'SCREEN_BAN';

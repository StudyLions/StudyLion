ALTER TABLE guild_config ADD COLUMN pomodoro_channel BIGINT;

-- Timer Data {{{
create TABLE timers(
  channelid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL REFERENCES guild_config (guildid),
  text_channelid BIGINT,
  focus_length INTEGER NOT NULL,
  break_length INTEGER NOT NULL,
  last_started TIMESTAMPTZ NOT NULL,
  inactivity_threshold INTEGER,
  channel_name TEXT,
  pretty_name TEXT
);
CREATE INDEX timers_guilds ON timers (guildid);
-- }}}

INSERT INTO VersionHistory (version, author) VALUES (8, 'v7-v8 migration');

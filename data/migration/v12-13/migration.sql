-- Add gem support
ALTER TABLE user_config ADD COLUMN name TEXT;
INSERT INTO VersionHistory (version, author) VALUES (13, 'v12-v13 migration');

-- Add first_joined_at to guild table
-- Add left_at to guild table
ALTER TABLE guild_config ADD COLUMN first_joined_at TIMESTAMPTZ;
ALTER TABLE guild_config ADD COLUMN left_at TIMESTAMPTZ;


CREATE TABLE app_config(
  appname TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bot_config(
  appname TEXT PRIMARY KEY REFERENCES app_config(appname) ON DELETE CASCADE,
  default_skin TEXT
);

CREATE TABLE shard_data(
  shard_name TEXT PRIMARY KEY,
  appname TEXT REFERENCES bot_config(appname) ON DELETE CASCADE,
  shard_id INTEGER NOT NULL,
  shard_count INTEGER NOT NULL,
  last_login TIMESTAMPTZ,
  guild_count INTEGER
);

CREATE TYPE OnlineStatus AS ENUM(
  'ONLINE',
  'IDLE',
  'DND',
  'OFFLINE'
);

CREATE TYPE ActivityType AS ENUM(
  'PLAYING',
  'WATCHING',
  'LISTENING',
  'STREAMING'
);

CREATE TABLE bot_config_presence(
  appname TEXT PRIMARY KEY REFERENCES bot_config(appname) ON DELETE CASCADE,
  online_status OnlineStatus,
  activity_type ActivityType,
  activity_name Text
);

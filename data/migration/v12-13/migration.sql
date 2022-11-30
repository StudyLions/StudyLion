-- Add metdata to configuration tables {{{
ALTER TABLE user_config ADD COLUMN name TEXT;
ALTER TABLE user_config ADD COLUMN first_seen TIMESTAMPTZ DEFAULT now();
ALTER TABLE user_config ADD COLUMN last_seen TIMESTAMPTZ;

ALTER TABLE guild_config ADD COLUMN first_joined_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE guild_config ADD COLUMN left_at TIMESTAMPTZ;

ALTER TABLE members ADD COLUMN first_joined TIMESTAMPTZ DEFAULT now();
ALTER TABLE members ADD COLUMN last_left TIMESTAMPTZ;
-- }}}


-- Bot config data {{{
CREATE TABLE app_config(
  appname TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bot_config(
  appname TEXT PRIMARY KEY REFERENCES app_config(appname) ON DELETE CASCADE,
  default_skin TEXT
);

CREATE TABLE shard_data(
  shardname TEXT PRIMARY KEY,
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
-- }}}


-- Analytics data {{{
-- DROP SCHEMA IF EXISTS "analytics" CASCADE;
CREATE SCHEMA "analytics";

CREATE TABLE analytics.snapshots(
  snapshotid SERIAL PRIMARY KEY,
  appname TEXT NOT NULL REFERENCES bot_config (appname),
  guild_count INTEGER NOT NULL,
  member_count INTEGER NOT NULL,
  user_count INTEGER NOT NULL,
  in_voice INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc')
);


CREATE TABLE analytics.events(
  eventid SERIAL PRIMARY KEY,
  appname TEXT NOT NULL REFERENCES bot_config (appname),
  ctxid BIGINT,
  guildid BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc')
);

CREATE TYPE analytics.CommandStatus AS ENUM(
  'COMPLETED',
  'CANCELLED'
  'FAILED'
);

CREATE TABLE analytics.commands(
  cmdname TEXT NOT NULL,
  cogname TEXT,
  userid BIGINT NOT NULL,
  status analytics.CommandStatus NOT NULL,
  error TEXT,
  execution_time REAL NOT NULL
) INHERITS (analytics.events);


CREATE TYPE analytics.GuildAction AS ENUM(
  'JOINED',
  'LEFT'
);

CREATE TABLE analytics.guilds(
  guildid BIGINT NOT NULL,
  action analytics.GuildAction NOT NULL
) INHERITS (analytics.events);


CREATE TYPE analytics.VoiceAction AS ENUM(
  'JOINED',
  'LEFT'
);

CREATE TABLE analytics.voice_sessions(
  userid BIGINT NOT NULL,
  action analytics.VoiceAction NOT NULL
) INHERITS (analytics.events);

CREATE TABLE analytics.gui_renders(
  cardname TEXT NOT NULL,
  duration INTEGER NOT NULL
) INHERITS (analytics.events);
--- }}}


ALTER TABLE members
  ADD CONSTRAINT fk_members_users FOREIGN KEY (userid) REFERENCES user_config (userid) ON DELETE CASCADE NOT VALID;
ALTER TABLE members
  ADD CONSTRAINT fk_members_guilds FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE NOT VALID;

-- Localisation data {{{
ALTER TABLE user_config ADD COLUMN locale_hint TEXT;
ALTER TABLE user_config ADD COLUMN locale TEXT;
ALTER TABLE guild_config ADD COLUMN locale TEXT;
ALTER TABLE guild_config ADD COLUMN force_locale BOOLEAN;
--}}}

-- Reminder data {{{
ALTER TABLE reminders ADD COLUMN failed BOOLEAN;
ALTER TABLE reminders
  ADD CONSTRAINT fk_reminders_users FOREIGN KEY (userid) REFERENCES user_config (userid) ON DELETE CASCADE NOT VALID;
-- }}}


-- Economy data {{{
CREATE TYPE CoinTransactionType AS ENUM(
  'REFUND',
  'TRANSFER',
  'SHOP_PURCHASE',
  'STUDY_SESSION',
  'ADMIN',
  'TASKS'
);


CREATE TABLE coin_transactions(
  transactionid SERIAL PRIMARY KEY,
  transactiontype CoinTransactionType NOT NULL,
  guildid BIGINT NOT NULL REFERENCES guild_config (guildid) ON DELETE CASCADE,
  actorid BIGINT NOT NULL,
  amount INTEGER NOT NULL,
  bonus INTEGER NOT NULL,
  from_account BIGINT,
  to_account BIGINT,
  refunds INTEGER REFERENCES coin_transactions (transactionid) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc')
);
CREATE INDEX coin_transaction_guilds ON coin_transactions (guildid);

CREATE TABLE coin_transactions_shop(
  transactionid INTEGER PRIMARY KEY REFERENCES coin_transactions (transactionid) ON DELETE CASCADE,
  itemid INTEGER NOT NULL REFERENCES shop_items (itemid) ON DELETE CASCADE
);

CREATE TABLE coin_transactions_tasks(
  transactionid INTEGER PRIMARY KEY REFERENCES coin_transactions (transactionid) ON DELETE CASCADE,
  count INTEGER NOT NULL
);

CREATE TABLE coin_transactions_sessions(
  transactionid INTEGER PRIMARY KEY REFERENCES coin_transactions (transactionid) ON DELETE CASCADE,
  sessionid INTEGER NOT NULL REFERENCES session_history (sessionid) ON DELETE CASCADE 
);

CREATE TYPE EconAdminTarget AS ENUM(
  'ROLE',
  'USER',
  'GUILD'
);

CREATE TYPE EconAdminAction AS ENUM(
  'SET',
  'ADD'
);

CREATE TABLE economy_admin_actions(
  actionid SERIAL PRIMARY KEY,
  target_type EconAdminTarget NOT NULL,
  action_type EconAdminAction NOT NULL,
  targetid INTEGER NOT NULL,
  amount INTEGER NOT NULL
);

CREATE TABLE coin_transactions_admin_actions(
  actionid INTEGER NOT NULL REFERENCES economy_admin_actions (actionid),
  transactionid INTEGER NOT NULL REFERENCES coin_transactions (transactionid),
  PRIMARY KEY (actionid, transactionid)
);
CREATE INDEX coin_transactions_admin_actions_transactionid ON coin_transactions_admin_actions (transactionid);

-- }}}

INSERT INTO VersionHistory (version, author) VALUES (13, 'v12-v13 migration');

-- vim: set fdm=marker:

BEGIN;

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
-- DROP TABLE AppData CASCADE;
-- DROP TABLE AppConfig CASCADE;
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
  'VOICE_SESSION',
  'TEXT_SESSION',
  'ADMIN',
  'TASKS'
);


CREATE TABLE coin_transactions(
  transactionid SERIAL PRIMARY KEY,
  transactiontype CoinTransactionType NOT NULL,
  guildid BIGINT NOT NULL REFERENCES guild_config (guildid) ON DELETE CASCADE,
  actorid BIGINT NOT NULL,
  amount INTEGER NOT NULL,
  bonus INTEGER NOT NULL DEFAULT 0,
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

-- Shop data {{{
ALTER TABLE member_inventory DROP CONSTRAINT member_inventory_pkey;

ALTER TABLE member_inventory
  ADD COLUMN inventoryid SERIAL PRIMARY KEY;

ALTER TABLE member_inventory
  ADD COLUMN transactionid INTEGER REFERENCES coin_transactions (transactionid) ON DELETE SET NULL;

ALTER TABLE member_inventory
  DROP COLUMN count;

CREATE INDEX member_inventory_members ON member_inventory(guildid, userid);


CREATE VIEW member_inventory_info AS
  SELECT
    inv.inventoryid AS inventoryid,
    inv.guildid AS guildid,
    inv.userid AS userid,
    inv.transactionid AS transactionid,
    items.itemid AS itemid,
    items.item_type AS item_type,
    items.price AS price,
    items.purchasable AS purchasable,
    items.deleted AS deleted,
    items.guild_itemid AS guild_itemid,
    items.roleid AS roleid
  FROM
    member_inventory inv
  LEFT JOIN shop_item_info items USING (itemid)
  ORDER BY itemid ASC;
-- }}}

-- Task Data {{{
ALTER TABLE tasklist_channels
  ADD CONSTRAINT fk_tasklist_channels_guilds
  FOREIGN KEY (guildid)
  REFERENCES guild_config (guildid)
  ON DELETE CASCADE
  NOT VALID;

ALTER TABLE tasklist
  ADD CONSTRAINT fk_tasklist_users
  FOREIGN KEY (userid)
  REFERENCES user_config (userid)
  ON DELETE CASCADE
  NOT VALID;

ALTER TABLE tasklist
  ADD COLUMN parentid INTEGER REFERENCES tasklist (taskid) ON DELETE SET NULL;

-- DROP TABLE tasklist_reward_history CASCADE;
-- }}}

-- New tracking data {{
DROP TABLE IF EXISTS tracked_channels;
CREATE TABLE tracked_channels(
  channelid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL,
  deleted BOOLEAN DEFAULT FALSE,
  _timestamp TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE
);
CREATE INDEX tracked_channels_guilds ON tracked_channels (guildid);

DROP FUNCTION IF EXISTS study_time_between(_guildid BIGINT, _userid BIGINT, _start TIMESTAMPTZ, _end TIMESTAMPTZ);
DROP FUNCTION IF EXISTS study_time_since(_guildid BIGINT, _userid BIGINT, _timestamp TIMESTAMPTZ);
DROP VIEW IF EXISTS voice_sessions_combined;

DROP FUNCTION IF EXISTS close_study_sessions(_guildid BIGINT, _userid BIGINT);
DROP VIEW IF EXISTS new_study_badges; -- TODO
DROP VIEW IF EXISTS current_study_badges; -- TODO
DROP VIEW IF EXISTS member_ranks; -- TODO
DROP VIEW IF EXISTS members_totals;  -- TODO
DROP VIEW IF EXISTS current_sessions_totals;
DROP VIEW IF EXISTS member_totals;
DROP VIEW IF EXISTS member_ranks;

DROP TABLE current_sessions CASCADE;

ALTER TABLE session_history RENAME TO voice_sessions;
ALTER TABLE voice_sessions DROP COLUMN channel_type;
ALTER TABLE voice_sessions DROP COLUMN coins_earned;

ALTER TABLE voice_sessions
  ADD COLUMN transactionid INTEGER
  REFERENCES coin_transactions (transactionid)
  ON UPDATE CASCADE ON DELETE CASCADE;

INSERT INTO tracked_channels (guildid, channelid)
  SELECT guildid, channelid FROM voice_sessions ON CONFLICT DO NOTHING;

ALTER TABLE voice_sessions ADD FOREIGN KEY (channelid) REFERENCES tracked_channels (channelid);

CREATE TABLE voice_sessions_ongoing(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  channelid BIGINT REFERENCES tracked_channels (channelid),
  rating INTEGER,
  tag TEXT,
  start_time TIMESTAMPTZ DEFAULT (now() AT TIME ZONE 'UTC'),
  live_duration INTEGER NOT NULL DEFAULT 0,
  video_duration INTEGER NOT NULL DEFAULT 0,
  stream_duration INTEGER NOT NULL DEFAULT 0,
  coins_earned INTEGER NOT NULL DEFAULT 0,
  last_update TIMESTAMPTZ DEFAULT (now() AT TIME ZONE 'UTC'),
  live_stream BOOLEAN NOT NULL DEFAULT FALSE,
  live_video BOOLEAN NOT NULL DEFAULT FALSE,
  hourly_coins FLOAT NOT NULL DEFAULT 0,
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
);
CREATE UNIQUE INDEX voice_sessions_ongoing_members ON voice_sessions_ongoing (guildid, userid);

CREATE FUNCTION close_study_session_at(_guildid BIGINT, _userid BIGINT, _now TIMESTAMPTZ)
  RETURNS SETOF members
AS $$
  BEGIN
    RETURN QUERY
    WITH
      voice_session AS (
        DELETE FROM voice_sessions_ongoing
        WHERE guildid=_guildid AND userid=_userid
        RETURNING
          channelid, rating, tag, start_time,
          EXTRACT(EPOCH FROM (_now - start_time)) AS total_duration,
          (
            CASE WHEN live_stream
              THEN stream_duration + EXTRACT(EPOCH FROM (_now - last_update))
              ELSE stream_duration
            END
          ) AS stream_duration,
          (
            CASE WHEN live_video
              THEN video_duration + EXTRACT(EPOCH FROM (_now - last_update))
              ELSE video_duration
            END
          ) AS video_duration,
          (
            CASE WHEN live_stream OR live_video
              THEN live_duration + EXTRACT(EPOCH FROM (_now - last_update))
              ELSE live_duration
            END
          ) AS live_duration,
          (
            coins_earned + LEAST((EXTRACT(EPOCH FROM (_now - last_update)) * hourly_coins) / 3600, 2147483647)
          ) AS coins_earned
      ),
      economy_transaction AS (
        INSERT INTO coin_transactions (
          guildid, actorid,
          from_account, to_account,
          amount, bonus, transactiontype
        ) SELECT 
          _guildid, 0,
          NULL, _userid,
          voice_session.coins_earned, 0, 'VOICE_SESSION'
        FROM voice_session
        RETURNING 
          transactionid
      ),
      saved_session AS (
        INSERT INTO voice_sessions (
          guildid, userid, channelid,
          rating, tag,
          start_time, duration, live_duration, stream_duration, video_duration,
          transactionid
        ) SELECT 
          _guildid, _userid, voice_session.channelid,
          voice_session.rating, voice_session.tag,
          voice_session.start_time, voice_session.total_duration, voice_session.live_duration,
          voice_session.stream_duration, voice_session.video_duration,
          economy_transaction.transactionid
        FROM voice_session, economy_transaction
        RETURNING *
      )
    UPDATE members
    SET
      coins=LEAST(coins::BIGINT + voice_session.coins_earned::BIGINT, 2147483647)
    FROM
      voice_session
    WHERE
      members.guildid=_guildid AND members.userid=_userid
    RETURNING members.*;
  END;
$$ LANGUAGE PLPGSQL;

CREATE OR REPLACE FUNCTION update_voice_session(
  _guildid BIGINT, _userid BIGINT, _at TIMESTAMPTZ, _live_stream BOOLEAN, _live_video BOOLEAN, _hourly_coins FLOAT
) RETURNS SETOF voice_sessions_ongoing AS $$
  BEGIN
    RETURN QUERY
    UPDATE
      voice_sessions_ongoing
    SET
      stream_duration = (
        CASE WHEN live_stream
          THEN stream_duration + EXTRACT(EPOCH FROM (_at - last_update))
          ELSE stream_duration
        END
      ),
      video_duration = (
        CASE WHEN live_video
          THEN video_duration + EXTRACT(EPOCH FROM (_at - last_update))
          ELSE video_duration
        END
      ),
      live_duration = (
        CASE WHEN live_stream OR live_video
          THEN live_duration + EXTRACT(EPOCH FROM (_at - last_update))
          ELSE live_duration
        END
      ),
      coins_earned = (
        coins_earned + LEAST((EXTRACT(EPOCH FROM (_at - last_update)) * hourly_coins) / 3600, 2147483647)
      ),
      last_update = _at,
      live_stream = _live_stream,
      live_video = _live_video,
      hourly_coins = hourly_coins
    WHERE
      guildid = _guildid
      AND
      userid = _userid
    RETURNING *;
  END;
$$ LANGUAGE PLPGSQL;

-- Function to retouch session? Or handle in application?
-- Function to finish session? Or handle in application?
-- Does database function make transaction, or application?


CREATE VIEW voice_sessions_combined AS
  SELECT
    userid,
    guildid,
    start_time,
    duration,
    (start_time + duration * interval '1 second') AS end_time
  FROM voice_sessions
  UNION ALL
  SELECT
    userid,
    guildid,
    start_time,
    EXTRACT(EPOCH FROM (NOW() - start_time)) AS duration,
    NOW() AS end_time
  FROM voice_sessions_ongoing;

CREATE FUNCTION study_time_between(_guildid BIGINT, _userid BIGINT, _start TIMESTAMPTZ, _end TIMESTAMPTZ)
  RETURNS INTEGER
AS $$
  BEGIN
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
$$ LANGUAGE PLPGSQL;

CREATE FUNCTION study_time_since(_guildid BIGINT, _userid BIGINT, _timestamp TIMESTAMPTZ)
  RETURNS INTEGER
AS $$
  BEGIN
    RETURN (SELECT study_time_between(_guildid, _userid, _timestamp, NOW()));
  END;
$$ LANGUAGE PLPGSQL;
--}}

ALTER TABLE user_config ADD COLUMN show_global_stats BOOLEAN;

-- TODO: Profile tags, remove guildid not null restriction

-- Goal data {{{

CREATE TABLE user_weekly_goals(
  userid BIGINT NOT NULL,
  weekid INTEGER NOT NULL,
  task_goal INTEGER,
  study_goal INTEGER,
  review_goal INTEGER,
  message_goal INTEGER,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (userid, weekid),
  FOREIGN KEY (userid) REFERENCES user_config (userid) ON DELETE CASCADE
);
CREATE INDEX user_weekly_goals_users ON user_weekly_goals (userid);

ALTER TABLE member_weekly_goals ADD COLUMN review_goal INTEGER;
ALTER TABLE member_weekly_goals ADD COLUMN message_goal INTEGER;
ALTER TABLE member_monthly_goals ADD COLUMN review_goal INTEGER;
ALTER TABLE member_monthly_goals ADD COLUMN message_goal INTEGER;

CREATE TABLE user_monthly_goals(
  userid BIGINT NOT NULL,
  monthid INTEGER NOT NULL,
  task_goal INTEGER,
  study_goal INTEGER,
  review_goal INTEGER,
  message_goal INTEGER,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (userid, monthid),
  FOREIGN KEY (userid) REFERENCES user_config (userid) ON DELETE CASCADE
);
CREATE INDEX user_monthly_goals_users ON user_monthly_goals (userid);

/* CREATE TABLE weekly_goals( */
/*   goalid SERIAL PRIMARY KEY, */
/*   userid BIGINT NOT NULL, */
/*   weekid BIGINT NOT NULL, */
/*   guildid BIGINT, */
/*   goal_type GoalType, */
/*   goal INTEGER */
/* ); */

/* CREATE TABLE weeks( */
/*   weekid INTEGER PRIMARY KEY */
/* ); */

/* CREATE TABLE months( */
/*   monthid INTEGER PRIMARY KEY */
/* ); */

-- }}}

-- Timezone data {{{
ALTER TABLE guild_config ADD COLUMN timezone TEXT;
-- }}}

INSERT INTO VersionHistory (version, author) VALUES (13, 'v12-v13 migration');

COMMIT;

-- vim: set fdm=marker:

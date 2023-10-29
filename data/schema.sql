-- Metadata {{{
CREATE TABLE VersionHistory(
  version INTEGER NOT NULL,
  time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
  author TEXT
);
INSERT INTO VersionHistory (version, author) VALUES (14, 'Initial Creation');


CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW._timestamp = (now() at time zone 'utc'); 
  RETURN NEW;
END;
$$ language 'plpgsql';
-- }}}

-- App metadata {{{

CREATE TABLE global_user_blacklist(
  userid BIGINT PRIMARY KEY,
  ownerid BIGINT NOT NULL,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE global_guild_blacklist(
  guildid BIGINT PRIMARY KEY,
  ownerid BIGINT NOT NULL,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE app_config(
  appname TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bot_config(
  appname TEXT PRIMARY KEY REFERENCES app_config(appname) ON DELETE CASCADE,
  sponsor_prompt TEXT,
  sponsor_message TEXT,
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

-- User configuration data {{{
CREATE TABLE user_config(
  userid BIGINT PRIMARY KEY,
  timezone TEXT,
  name TEXT,
  topgg_vote_reminder BOOLEAN,
  avatar_hash TEXT,
  API_timestamp BIGINT,
  gems INTEGER DEFAULT 0,
  first_seen TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ,
  locale_hint TEXT,
  locale TEXT,
  show_global_stats BOOLEAN
);
-- }}}

-- Guild configuration data {{{
CREATE TYPE RankType AS ENUM(
  'XP',
  'VOICE',
  'MESSAGE'
);

CREATE TABLE guild_config(
  guildid BIGINT PRIMARY KEY,
  admin_role BIGINT,
  mod_role BIGINT,
  event_log_channel BIGINT,
  mod_log_channel BIGINT,
  alert_channel BIGINT,
  studyban_role BIGINT,
  min_workout_length INTEGER,
  workout_reward INTEGER,
  max_tasks INTEGER,
  task_reward INTEGER,
  task_reward_limit INTEGER,
  study_hourly_reward INTEGER,
  study_hourly_live_bonus INTEGER,
  renting_price INTEGER,
  renting_category BIGINT,
  renting_cap INTEGER,
  renting_role BIGINT,
  renting_sync_perms BOOLEAN,
  accountability_category BIGINT,
  accountability_lobby BIGINT,
  accountability_bonus INTEGER,
  accountability_reward INTEGER,
  accountability_price INTEGER,
  video_studyban BOOLEAN,
  video_grace_period INTEGER,
  greeting_channel BIGINT,
  greeting_message TEXT,
  returning_message TEXT,
  starting_funds INTEGER,
  persist_roles BOOLEAN,
  daily_study_cap INTEGER,
  pomodoro_channel BIGINT,
  name TEXT,
  locale TEXT,
  force_locale BOOLEAN,
  allow_transfers BOOLEAN,
  season_start TIMESTAMPTZ,
  xp_per_period INTEGER,
  xp_per_centiword INTEGER,
  coins_per_centixp INTEGER,
  timezone TEXT,
  rank_type RankType,
  rank_channel BIGINT,
  dm_ranks BOOLEAN,
  renting_visible BOOLEAN,
  first_joined_at TIMESTAMPTZ DEFAULT now(),
  left_at TIMESTAMPTZ
);

CREATE TABLE ignored_members(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL
);
CREATE INDEX ignored_member_guilds ON ignored_members (guildid);

CREATE TABLE unranked_roles(
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL
);
CREATE INDEX unranked_roles_guilds ON unranked_roles (guildid);

CREATE TABLE donator_roles(
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL
);
CREATE INDEX donator_roles_guilds ON donator_roles (guildid);

CREATE TABLE autoroles(
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL
);
CREATE INDEX autoroles_guilds ON autoroles (guildid);

CREATE TABLE bot_autoroles(
  guildid BIGINT NOT NULL ,
  roleid BIGINT NOT NULL
);
CREATE INDEX bot_autoroles_guilds ON bot_autoroles (guildid);

CREATE TYPE StatisticType AS ENUM(
  'VOICE',
  'TEXT',
  'ANKI'
);
CREATE TABLE visible_statistics(
  guildid BIGINT NOT NULL REFERENCES guild_config ON DELETE CASCADE,
  stat_type StatisticType NOT NULL
);
CREATE INDEX visible_statistics_guilds ON visible_statistics (guildid);

CREATE TABLE channel_webhooks(
  channelid BIGINT NOT NULL PRIMARY KEY,
  webhookid BIGINT NOT NULL,
  token TEXT NOT NULL
);
-- }}}

-- Economy Data {{{
CREATE TYPE CoinTransactionType AS ENUM(
  'REFUND',
  'TRANSFER',
  'SHOP_PURCHASE',
  'VOICE_SESSION',
  'TEXT_SESSION',
  'ADMIN',
  'TASKS',
  'SCHEDULE_BOOK',
  'SCHEDULE_REWARD',
  'OTHER'
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

-- Workout data {{{
CREATE TABLE workout_channels(
  guildid BIGINT NOT NULL,
  channelid BIGINT NOT NULL
);
CREATE INDEX workout_channels_guilds ON workout_channels (guildid);

CREATE TABLE workout_sessions(
  sessionid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  start_time TIMESTAMP DEFAULT (now() at time zone 'utc'),
  duration INTEGER,
  channelid BIGINT
);
CREATE INDEX workout_sessions_members ON workout_sessions (guildid, userid);
-- }}}

-- Tasklist data {{{
CREATE TABLE tasklist(
  taskid SERIAL PRIMARY KEY,
  userid BIGINT NOT NULL,
  content TEXT NOT NULL,
  rewarded BOOL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ,
  last_updated_at TIMESTAMPTZ
);
CREATE INDEX tasklist_users ON tasklist (userid);
ALTER TABLE tasklist
  ADD CONSTRAINT fk_tasklist_users
  FOREIGN KEY (userid)
  REFERENCES user_config (userid)
  ON DELETE CASCADE
  NOT VALID;
ALTER TABLE tasklist
  ADD COLUMN parentid INTEGER REFERENCES tasklist (taskid) ON DELETE SET NULL;

CREATE TABLE tasklist_channels(
  guildid BIGINT NOT NULL,
  channelid BIGINT NOT NULL
);
CREATE INDEX tasklist_channels_guilds ON tasklist_channels (guildid);
ALTER TABLE tasklist_channels
  ADD CONSTRAINT fk_tasklist_channels_guilds
  FOREIGN KEY (guildid)
  REFERENCES guild_config (guildid)
  ON DELETE CASCADE
  NOT VALID;

CREATE TABLE tasklist_reward_history(
  userid BIGINT NOT NULL,
  reward_time TIMESTAMP DEFAULT (now() at time zone 'utc'),
  reward_count INTEGER
);
CREATE INDEX tasklist_reward_history_users ON tasklist_reward_history (userid, reward_time);
-- }}}

-- Reminder data {{{
CREATE TABLE reminders(
    reminderid SERIAL PRIMARY KEY,
    userid BIGINT NOT NULL REFERENCES user_config(userid) ON DELETE CASCADE,
    remind_at TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL,
    message_link TEXT,
    interval INTEGER,
    failed BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT now(),
    title TEXT,
    footer TEXT
);
CREATE INDEX reminder_users ON reminders (userid);
-- }}}

-- Voice tracking data {{{
CREATE TABLE tracked_channels(
  channelid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL,
  deleted BOOLEAN DEFAULT FALSE,
  _timestamp TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE
);
CREATE INDEX tracked_channels_guilds ON tracked_channels (guildid);

CREATE TABLE untracked_channels(
  guildid BIGINT NOT NULL,
  channelid BIGINT NOT NULL
);
CREATE INDEX untracked_channels_guilds ON untracked_channels (guildid);

CREATE TABLE study_badges(
  badgeid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  required_time INTEGER NOT NULL
);
CREATE UNIQUE INDEX study_badge_guilds ON study_badges (guildid, required_time);

CREATE VIEW study_badge_roles AS
  SELECT
    *,
    row_number() OVER (PARTITION BY guildid ORDER BY required_time ASC) AS guild_badge_level
  FROM
    study_badges
  ORDER BY guildid, required_time ASC;
-- }}}

-- Shop data {{{
CREATE TYPE ShopItemType AS ENUM (
  'COLOUR_ROLE'
);

CREATE TABLE shop_items(
  itemid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  item_type ShopItemType NOT NULL,
  price INTEGER NOT NULL,
  purchasable BOOLEAN DEFAULT TRUE,
  deleted BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT (now() at time zone 'utc')
);
CREATE INDEX guild_shop_items ON shop_items (guildid);

CREATE TABLE coin_transactions_shop(
  transactionid INTEGER PRIMARY KEY REFERENCES coin_transactions (transactionid) ON DELETE CASCADE,
  itemid INTEGER NOT NULL REFERENCES shop_items (itemid) ON DELETE CASCADE
);

CREATE TABLE shop_items_colour_roles(
  itemid INTEGER PRIMARY KEY REFERENCES shop_items(itemid) ON DELETE CASCADE,
  roleid BIGINT NOT NULL
);

CREATE TABLE member_inventory(
  inventoryid SERiAL PRIMARY KEY,
  transactionid INTEGER REFERENCES coin_transactions (transactionid) ON DELETE SET NULL,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  itemid INTEGER NOT NULL REFERENCES shop_items(itemid) ON DELETE CASCADE
);

CREATE INDEX member_inventory_members ON member_inventory(guildid, userid);


CREATE VIEW shop_item_info AS
  SELECT
    *,
    row_number() OVER (PARTITION BY guildid ORDER BY itemid) AS guild_itemid
  FROM
    shop_items
  LEFT JOIN shop_items_colour_roles USING (itemid)
  ORDER BY itemid ASC;


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

/*
-- Shop config, not implemented
CREATE TABLE guild_shop_config(
  guildid BIGINT PRIMARY KEY
);

CREATE TABLE guild_colourroles_config(
);
*/
-- }}}

-- Moderation data {{{
CREATE TABLE video_channels(
  guildid BIGINT NOT NULL,
  channelid BIGINT NOT NULL
);
CREATE INDEX video_channels_guilds ON video_channels (guildid);

CREATE TABLE video_exempt_roles(
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  _timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE ON UPDATE CASCADE,
  PRIMARY KEY (guildid, roleid)
);

CREATE TYPE TicketType AS ENUM (
  'NOTE',
  'STUDY_BAN',
  'MESSAGE_CENSOR',
  'INVITE_CENSOR',
  'WARNING'
);

CREATE TYPE TicketState AS ENUM (
  'OPEN',
  'EXPIRING',
  'EXPIRED',
  'PARDONED'
);

CREATE TABLE tickets(
  ticketid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  targetid BIGINT NOT NULL,
  ticket_type TicketType NOT NULL, 
  ticket_state TicketState NOT NULL DEFAULT 'OPEN',
  moderator_id BIGINT NOT NULL,
  log_msg_id BIGINT,
  created_at TIMESTAMP DEFAULT (now() at time zone 'utc'),
  auto BOOLEAN DEFAULT FALSE,  -- Whether the ticket was automatically created
  content TEXT,  -- Main ticket content, usually contains the ticket reason
  context TEXT,  -- Optional flexible column only used by some TicketTypes
  addendum TEXT,  -- Optional extra text used for after-the-fact context information
  duration INTEGER,  -- Optional duration column, mostly used by automatic tickets
  file_name TEXT,  -- Optional file name to accompany the ticket
  file_data BYTEA,  -- Optional file data to accompany the ticket
  expiry TIMESTAMPTZ,  -- Time to automatically expire the ticket  
  pardoned_by BIGINT,  -- Actorid who pardoned the ticket
  pardoned_at TIMESTAMPTZ,  -- Time when the ticket was pardoned
  pardoned_reason TEXT  -- Reason the ticket was pardoned
);
CREATE INDEX tickets_members_types ON tickets (guildid, targetid, ticket_type);
CREATE INDEX tickets_states ON tickets (ticket_state);

CREATE VIEW ticket_info AS
  SELECT
    *,
    row_number() OVER (PARTITION BY guildid ORDER BY ticketid) AS guild_ticketid
  FROM tickets
  ORDER BY ticketid;

ALTER TABLE ticket_info ALTER ticket_state SET DEFAULT 'OPEN';
ALTER TABLE ticket_info ALTER created_at SET DEFAULT (now() at time zone 'utc');
ALTER TABLE ticket_info ALTER auto SET DEFAULT False;

CREATE OR REPLACE FUNCTION instead_of_ticket_info()
  RETURNS trigger AS
$$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO tickets(
          guildid,
          targetid,
          ticket_type, 
          ticket_state,
          moderator_id,
          log_msg_id,
          created_at,
          auto,
          content,
          context,
          addendum,
          duration,
          file_name,
          file_data,
          expiry,
          pardoned_by,
          pardoned_at,
          pardoned_reason
        ) VALUES (
          NEW.guildid,
          NEW.targetid,
          NEW.ticket_type, 
          NEW.ticket_state,
          NEW.moderator_id,
          NEW.log_msg_id,
          NEW.created_at,
          NEW.auto,
          NEW.content,
          NEW.context,
          NEW.addendum,
          NEW.duration,
          NEW.file_name,
          NEW.file_data,
          NEW.expiry,
          NEW.pardoned_by,
          NEW.pardoned_at,
          NEW.pardoned_reason
        ) RETURNING ticketid INTO NEW.ticketid;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE tickets SET
          guildid = NEW.guildid,
          targetid = NEW.targetid,
          ticket_type = NEW.ticket_type, 
          ticket_state = NEW.ticket_state,
          moderator_id = NEW.moderator_id,
          log_msg_id = NEW.log_msg_id,
          created_at = NEW.created_at,
          auto = NEW.auto,
          content = NEW.content,
          context = NEW.context,
          addendum = NEW.addendum,
          duration = NEW.duration,
          file_name = NEW.file_name,
          file_data = NEW.file_data,
          expiry = NEW.expiry,
          pardoned_by = NEW.pardoned_by,
          pardoned_at = NEW.pardoned_at,
          pardoned_reason = NEW.pardoned_reason
        WHERE
          ticketid = OLD.ticketid;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM tickets WHERE ticketid = OLD.ticketid;
        RETURN OLD;
    END IF;
END;
$$ LANGUAGE PLPGSQL;

CREATE TRIGGER instead_of_ticket_info_trig
    INSTEAD OF INSERT OR UPDATE OR DELETE ON
      ticket_info FOR EACH ROW 
      EXECUTE PROCEDURE instead_of_ticket_info();


CREATE TABLE studyban_durations(
  rowid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  duration INTEGER NOT NULL
);
CREATE INDEX studyban_durations_guilds ON studyban_durations (guildid);
-- }}}

-- Member configuration and stored data {{{
CREATE TABLE members(
  guildid BIGINT,
  userid BIGINT,
  tracked_time INTEGER DEFAULT 0,
  coins INTEGER DEFAULT 0,
  workout_count INTEGER DEFAULT 0,
  revision_mute_count INTEGER DEFAULT 0,
  last_workout_start TIMESTAMP,
  last_study_badgeid INTEGER REFERENCES study_badges ON DELETE SET NULL,
  video_warned BOOLEAN DEFAULT FALSE,
  display_name TEXT,
  first_joined TIMESTAMPTZ DEFAULT now(),
  last_left TIMESTAMPTZ,
  _timestamp TIMESTAMP DEFAULT (now() at time zone 'utc'),
  PRIMARY KEY(guildid, userid)
);
CREATE INDEX member_timestamps ON members (_timestamp);

CREATE TRIGGER update_members_timstamp BEFORE UPDATE
ON members FOR EACH ROW EXECUTE PROCEDURE 
update_timestamp_column();

ALTER TABLE members
  ADD CONSTRAINT fk_members_users FOREIGN KEY (userid) REFERENCES user_config (userid) ON DELETE CASCADE NOT VALID;
ALTER TABLE members
  ADD CONSTRAINT fk_members_guilds FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE NOT VALID;
-- }}}

-- Message tracking and statistics {{{
CREATE TYPE ExperienceType AS ENUM(
  'VOICE_XP',
  'TEXT_XP',
  'QUEST_XP',  -- Custom guild quests
  'ACHIEVEMENT_XP', -- Individual tracked achievements
  'BONUS_XP' -- Manually adjusted XP
);

CREATE TABLE member_experience(
  member_expid BIGSERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  earned_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'UTC'),
  amount INTEGER NOT NULL,
  exp_type ExperienceType NOT NULL,
  transactionid INTEGER REFERENCES coin_transactions ON DELETE SET NULL,
  FOREIGN KEY (guildid, userid) REFERENCES members ON DELETE CASCADE
);
CREATE INDEX member_experience_members ON member_experience (guildid, userid, earned_at);
CREATE INDEX member_experience_guilds ON member_experience (guildid, earned_at);

CREATE TABLE user_experience(
  user_expid BIGSERIAL PRIMARY KEY,
  userid BIGINT NOT NULL,
  earned_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'UTC'),
  amount INTEGER NOT NULL,
  exp_type ExperienceType NOT NULL,
  FOREIGN KEY (userid) REFERENCES user_config ON DELETE CASCADE
);
CREATE INDEX user_experience_users ON user_experience (userid, earned_at);


CREATE TABLE bot_config_experience_rates(
  appname TEXT PRIMARY KEY REFERENCES bot_config(appname) ON DELETE CASCADE,
  period_length INTEGER,
  xp_per_period INTEGER,
  xp_per_centiword INTEGER
);

CREATE TABLE text_sessions(
  sessionid BIGSERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  start_time TIMESTAMPTZ NOT NULL,
  duration INTEGER NOT NULL,
  messages INTEGER NOT NULL,
  words INTEGER NOT NULL,
  periods INTEGER NOT NULL,
  user_expid BIGINT REFERENCES user_experience,
  member_expid BIGINT REFERENCES member_experience,
  end_time TIMESTAMP GENERATED ALWAYS AS
    ((start_time AT TIME ZONE 'UTC') + duration * interval '1 second')
  STORED,
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
);
CREATE INDEX text_sessions_members ON text_sessions (guildid, userid);
CREATE INDEX text_sessions_start_time ON text_sessions (start_time);
CREATE INDEX text_sessions_end_time ON text_sessions (end_time);

CREATE TABLE untracked_text_channels(
  channelid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL,
  _timestamp TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE
);
CREATE INDEX untracked_text_channels_guilds ON untracked_text_channels (guildid);

-- }}}

-- Study Session Data {{{
CREATE TYPE SessionChannelType AS ENUM (
  'STANDARD',
  'ACCOUNTABILITY',
  'RENTED',
  'EXTERNAL'
);


CREATE TABLE voice_sessions(
  sessionid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  channelid BIGINT,
  rating INTEGER,
  tag TEXT,
  start_time TIMESTAMPTZ NOT NULL,
  duration INTEGER NOT NULL,
  live_duration INTEGER DEFAULT 0,
  stream_duration INTEGER DEFAULT 0,
  video_duration INTEGER DEFAULT 0,
  transactionid INTEGER REFERENCES coin_transactions (transactionid) ON UPDATE CASCADE ON DELETE CASCADE,
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
);
CREATE INDEX voice_session_members ON voice_sessions (guildid, userid, start_time);
CREATE INDEX voice_session_guild_time ON voice_sessions USING BTREE (guildid, start_time);
CREATE INDEX voice_session_user_time ON voice_sessions USING BTREE (userid, start_time);
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

-- }}}

-- Activity Rank Data {{{
CREATE TABLE xp_ranks(
  rankid SERIAL PRIMARY KEY,
  roleid BIGINT NOT NULL,
  guildid BIGINT NOT NULL REFERENCES guild_config ON DELETE CASCADE,
  required INTEGER NOT NULL,
  reward INTEGER NOT NULL,
  message TEXT
);
CREATE UNIQUE INDEX xp_ranks_roleid ON xp_ranks (roleid);
CREATE INDEX xp_ranks_guild_required ON xp_ranks (guildid, required);

CREATE TABLE voice_ranks(
  rankid SERIAL PRIMARY KEY,
  roleid BIGINT NOT NULL,
  guildid BIGINT NOT NULL REFERENCES guild_config ON DELETE CASCADE,
  required INTEGER NOT NULL,
  reward INTEGER NOT NULL,
  message TEXT
);
CREATE UNIQUE INDEX voice_ranks_roleid ON voice_ranks (roleid);
CREATE INDEX voice_ranks_guild_required ON voice_ranks (guildid, required);

CREATE TABLE msg_ranks(
  rankid SERIAL PRIMARY KEY,
  roleid BIGINT NOT NULL,
  guildid BIGINT NOT NULL REFERENCES guild_config ON DELETE CASCADE,
  required INTEGER NOT NULL,
  reward INTEGER NOT NULL,
  message TEXT
);
CREATE UNIQUE INDEX msg_ranks_roleid ON msg_ranks (roleid);
CREATE INDEX msg_ranks_guild_required ON msg_ranks (guildid, required);

CREATE TABLE member_ranks(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  current_xp_rankid INTEGER REFERENCES xp_ranks ON DELETE SET NULL,
  current_voice_rankid INTEGER REFERENCES voice_ranks ON DELETE SET NULL,
  current_msg_rankid INTEGER REFERENCES msg_ranks ON DELETE SET NULL,
  last_roleid BIGINT,
  PRIMARY KEY (guildid, userid),
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid)
);

CREATE TABLE season_stats(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  voice_stats INTEGER NOT NULL DEFAULT 0,
  xp_stats INTEGER NOT NULL DEFAULT 0,
  message_stats INTEGER NOT NULL DEFAULT 0,
  season_start TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guildid, userid),
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid)
);

-- }}}

-- Rented Room data {{{
CREATE TABLE rented_rooms(
  channelid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL,
  ownerid BIGINT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  coin_balance INTEGER NOT NULL DEFAULT 0,
  name TEXT,
  last_tick TIMESTAMPTZ,
  contribution INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (guildid, ownerid) REFERENCES members (guildid, userid) ON DELETE CASCADE
);
CREATE INDEX rented_owners ON rented_rooms(guildid, ownerid);

CREATE TABLE rented_members(
  channelid BIGINT NOT NULL REFERENCES rented_rooms(channelid) ON DELETE CASCADE,
  userid BIGINT NOT NULL
);
CREATE INDEX rented_members_channels ON rented_members (channelid);
CREATE INDEX rented_members_users ON rented_members (userid);
-- }}}

-- Scheduled Sessions {{{
CREATE TABLE schedule_slots(
  slotid INTEGER PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE schedule_guild_config(
  guildid BIGINT PRIMARY KEY REFERENCES guild_config ON DELETE CASCADE,
  schedule_cost INTEGER,
  reward INTEGER,
  bonus_reward INTEGER,
  min_attendance INTEGER,
  lobby_channel BIGINT,
  room_channel BIGINT,
  blacklist_after INTEGER,
  blacklist_role BIGINT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE schedule_channels(
  guildid BIGINT NOT NULL REFERENCES schedule_guild_config ON DELETE CASCADE,
  channelid BIGINT NOT NULL,
  PRIMARY KEY (guildid, channelid)
);

CREATE TABLE schedule_sessions(
  guildid BIGINT NOT NULL REFERENCES schedule_guild_config ON DELETE CASCADE,
  slotid INTEGER NOT NULL REFERENCES schedule_slots ON DELETE CASCADE,
  opened_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ,
  messageid BIGINT,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (guildid, slotid)
);

CREATE TABLE schedule_session_members(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  slotid INTEGER NOT NULL,
  booked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  attended BOOLEAN NOT NULL DEFAULT False,
  clock INTEGER NOT NULL DEFAULT 0,
  book_transactionid INTEGER REFERENCES coin_transactions,
  reward_transactionid INTEGER REFERENCES coin_transactions,
  PRIMARY KEY (guildid, userid, slotid),
  FOREIGN KEY (guildid, userid) REFERENCES members ON DELETE CASCADE,
  FOREIGN KEY (guildid, slotid) REFERENCES schedule_sessions (guildid, slotid) ON DELETE CASCADE
);
CREATE INDEX schedule_session_members_users ON schedule_session_members(userid, slotid);

-- }}}

-- RoleMenus {{{
CREATE TYPE RoleMenuType AS ENUM(
    'REACTION',
    'BUTTON',
    'DROPDOWN'
);


CREATE TABLE role_menus(
    menuid SERIAL PRIMARY KEY,
    guildid BIGINT NOT NULL REFERENCES guild_config (guildid) ON DELETE CASCADE,
    channelid BIGINT,
    messageid BIGINT,
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT True,
    required_roleid BIGINT,
    sticky BOOLEAN,
    refunds BOOLEAN,
    obtainable INTEGER,
    menutype RoleMenuType NOT NULL,
    templateid INTEGER,
    rawmessage TEXT,
    default_price INTEGER,
    event_log BOOLEAN
);
CREATE INDEX role_menu_guildid ON role_menus (guildid);



CREATE TABLE role_menu_roles(
    menuroleid SERIAL PRIMARY KEY,
    menuid INTEGER NOT NULL REFERENCES role_menus (menuid) ON DELETE CASCADE,
    roleid BIGINT NOT NULL,
    label TEXT NOT NULL,
    emoji TEXT,
    description TEXT,
    price INTEGER,
    duration INTEGER,
    rawreply TEXT
);
CREATE INDEX role_menu_roles_menuid ON role_menu_roles (menuid);
CREATE INDEX role_menu_roles_roleid ON role_menu_roles (roleid);


CREATE TABLE role_menu_history(
    equipid SERIAL PRIMARY KEY,
    menuid INTEGER NOT NULL REFERENCES role_menus (menuid) ON DELETE CASCADE,
    roleid BIGINT NOT NULL,
    userid BIGINT NOT NULL,
    obtained_at TIMESTAMPTZ NOT NULL,
    transactionid INTEGER REFERENCES coin_transactions (transactionid) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ,
    removed_at TIMESTAMPTZ
);
CREATE INDEX role_menu_history_menuid ON role_menu_history (menuid);
CREATE INDEX role_menu_history_roleid ON role_menu_history (roleid);
-- }}}

-- Member Role Data {{{
CREATE TABLE past_member_roles(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid)
);
CREATE INDEX member_role_persistence_members ON past_member_roles (guildid, userid);
-- }}}

-- Member profile tags {{{
CREATE TABLE member_profile_tags(
  tagid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  tag TEXT NOT NULL,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid)
);
CREATE INDEX member_profile_tags_members ON member_profile_tags (guildid, userid);
-- }}}

-- Member goals {{{
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

CREATE TABLE member_weekly_goals(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  weekid INTEGER NOT NULL, -- Epoch time of the start of the UTC week
  study_goal INTEGER,
  task_goal INTEGER,
  review_goal INTEGER,
  message_goal INTEGER,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (guildid, userid, weekid),
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
);
CREATE INDEX member_weekly_goals_members ON member_weekly_goals (guildid, userid);

CREATE TABLE member_weekly_goal_tasks(
  taskid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  weekid INTEGER NOT NULL,
  content TEXT NOT NULL,
  completed BOOLEAN NOT NULL DEFAULT FALSE,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  FOREIGN KEY (weekid, guildid, userid) REFERENCES member_weekly_goals (weekid, guildid, userid) ON DELETE CASCADE
);
CREATE INDEX member_weekly_goal_tasks_members_weekly ON member_weekly_goal_tasks (guildid, userid, weekid);

CREATE TABLE member_monthly_goals(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  monthid INTEGER NOT NULL, -- Epoch time of the start of the UTC month
  study_goal INTEGER,
  task_goal INTEGER,
  review_goal INTEGER,
  message_goal INTEGER,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (guildid, userid, monthid),
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
);
CREATE INDEX member_monthly_goals_members ON member_monthly_goals (guildid, userid);

CREATE TABLE member_monthly_goal_tasks(
  taskid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  monthid INTEGER NOT NULL,
  content TEXT NOT NULL,
  completed BOOLEAN NOT NULL DEFAULT FALSE,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  FOREIGN KEY (monthid, guildid, userid) REFERENCES member_monthly_goals (monthid, guildid, userid) ON DELETE CASCADE
);
CREATE INDEX member_monthly_goal_tasks_members_monthly ON member_monthly_goal_tasks (guildid, userid, monthid);

-- }}}

-- Timer Data {{{
create TABLE timers(
  channelid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL REFERENCES guild_config (guildid),
  notification_channelid BIGINT,
  focus_length INTEGER NOT NULL,
  break_length INTEGER NOT NULL,
  last_started TIMESTAMPTZ,
  inactivity_threshold INTEGER,
  channel_name TEXT,
  pretty_name TEXT,
  ownerid BIGINT REFERENCES user_config,
  manager_roleid BIGINT,
  last_messageid BIGINT,
  voice_alerts BOOLEAN,
  auto_restart BOOLEAN
);
CREATE INDEX timers_guilds ON timers (guildid);
-- }}}

-- Topgg Data {{{
create TABLE topgg(
  voteid SERIAL PRIMARY KEY,
  userid BIGINT NOT NULL,
  boostedTimestamp TIMESTAMPTZ NOT NULL
);
CREATE INDEX topgg_userid_timestamp ON topgg (userid, boostedTimestamp);

CREATE TABLE topgg_guild_whitelist(
  appid TEXT,
  guildid BIGINT,
  PRIMARY KEY(appid, guildid)
);
-- }}}

-- Sponsor Data {{{
CREATE TABLE sponsor_guild_whitelist(
  appid TEXT,
  guildid BIGINT,
  PRIMARY KEY(appid, guildid)
);
-- }}}

-- LionGem audit log {{{
CREATE TYPE GemTransactionType AS ENUM (
  'ADMIN',
  'GIFT',
  'PURCHASE',
  'AUTOMATIC'
);

CREATE TABLE gem_transactions(
  transactionid SERIAL PRIMARY KEY,
  transaction_type GemTransactionType NOT NULL,
  actorid BIGINT NOT NULL,
  from_account BIGINT,
  to_account BIGINT,
  amount INTEGER NOT NULL,
  description TEXT NOT NULL,
  note TEXT,
  reference TEXT,
  _timestamp TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX gem_transactions_from ON gem_transactions (from_account);
-- }}}

-- Skin Data {{{
CREATE TABLE global_available_skins(
  skin_id SERIAL PRIMARY KEY,
  skin_name TEXT NOT NULL
);
CREATE INDEX global_available_skin_names ON global_available_skins (skin_name);

CREATE TABLE customised_skins(
  custom_skin_id SERIAL PRIMARY KEY,
  base_skin_id INTEGER REFERENCES global_available_skins (skin_id),
  _timestamp TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE customised_skin_property_ids(
  property_id SERIAL PRIMARY KEY,
  card_id TEXT NOT NULL,
  property_name TEXT NOT NULL,
  UNIQUE(card_id, property_name)
);

CREATE TABLE customised_skin_properties(
  custom_skin_id INTEGER NOT NULL REFERENCES customised_skins (custom_skin_id),
  property_id INTEGER NOT NULL REFERENCES customised_skin_property_ids (property_id),
  value TEXT NOT NULL,
  PRIMARY KEY (custom_skin_id, property_id)
);
CREATE INDEX customised_skin_property_skin_id ON customised_skin_properties(custom_skin_id);

CREATE VIEW customised_skin_data AS
  SELECT
    skins.custom_skin_id AS custom_skin_id,
    skins.base_skin_id AS base_skin_id,
    properties.property_id AS property_id,
    prop_ids.card_id AS card_id,
    prop_ids.property_name AS property_name,
    properties.value AS value
  FROM
    customised_skins skins
  LEFT JOIN customised_skin_properties properties ON skins.custom_skin_id = properties.custom_skin_id
  LEFT JOIN customised_skin_property_ids prop_ids ON properties.property_id = prop_ids.property_id;


CREATE TABLE user_skin_inventory(
  itemid SERIAL PRIMARY KEY,
  userid BIGINT NOT NULL REFERENCES user_config (userid) ON DELETE CASCADE,
  custom_skin_id INTEGER NOT NULL REFERENCES customised_skins (custom_skin_id) ON DELETE CASCADE,
  transactionid INTEGER REFERENCES gem_transactions (transactionid),
  active BOOLEAN NOT NULL DEFAULT FALSE,
  acquired_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ
);
CREATE INDEX user_skin_inventory_users ON user_skin_inventory(userid);
CREATE UNIQUE INDEX user_skin_inventory_active ON user_skin_inventory(userid) WHERE active = TRUE;

CREATE VIEW user_active_skins AS
  SELECT
    *
  FROM user_skin_inventory
  WHERE active=True;
-- }}}


-- Premium Guild Data {{{
CREATE TABLE premium_guilds(
  guildid BIGINT PRIMARY KEY REFERENCES guild_config,
  premium_since TIMESTAMPTZ NOT NULL DEFAULT now(),
  premium_until TIMESTAMPTZ NOT NULL DEFAULT now(),
  custom_skin_id INTEGER REFERENCES customised_skins
);

-- Contributions members have made to guild premium funds
CREATE TABLE premium_guild_contributions(
  contributionid SERIAL PRIMARY KEY,
  userid BIGINT NOT NULL REFERENCES user_config,
  guildid BIGINT NOT NULL REFERENCES premium_guilds,
  transactionid INTEGER REFERENCES gem_transactions,
  duration INTEGER NOT NULL,
  _timestamp TIMESTAMPTZ DEFAULT now()
);
-- }}}


-- Analytics Data {{{
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
  'CANCELLED',
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
-- }}}

-- vim: set fdm=marker:

-- Metadata {{{
CREATE TABLE VersionHistory(
  version INTEGER NOT NULL,
  time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
  author TEXT
);
INSERT INTO VersionHistory (version, author) VALUES (0, 'Initial Creation');


CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW._timestamp = (now() at time zone 'utc'); 
  RETURN NEW;
END;
$$ language 'plpgsql';
-- }}}

-- App metadata {{{
CREATE TABLE AppData(
  appid TEXT PRIMARY KEY,
  last_study_badge_scan TIMESTAMP 
);
-- }}}


-- User configuration data {{{
CREATE TABLE user_config(
  userid BIGINT PRIMARY KEY,
  timezone TEXT
);
-- }}}

-- Guild configuration data {{{
CREATE TABLE guild_config(
  guildid BIGINT PRIMARY KEY,
  admin_role BIGINT,
  mod_role BIGINT,
  event_log_channel BIGINT,
  mod_log_channel BIGINT,
  study_ban_role BIGINT,
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
  accountability_price INTEGER
);

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
  complete BOOL DEFAULT FALSE,
  rewarded BOOL DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT (now() at time zone 'utc'),
  last_updated_at TIMESTAMP DEFAULT (now() at time zone 'utc')
);
CREATE INDEX tasklist_users ON tasklist (userid);

CREATE TABLE tasklist_channels(
  guildid BIGINT NOT NULL,
  channelid BIGINT NOT NULL
);
CREATE INDEX tasklist_channels_guilds ON tasklist_channels (guildid);

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
  userid BIGINT NOT NULL,
  remind_at TIMESTAMP NOT NULL,
  content TEXT NOT NULL,
  message_link TEXT,
  interval INTEGER,
  created_at TIMESTAMP DEFAULT (now() at time zone 'utc')
);
CREATE INDEX reminder_users ON reminders (userid);
-- }}}

-- Study tracking data {{{
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

CREATE TABLE shop_items_colour_roles(
  itemid INTEGER PRIMARY KEY REFERENCES shop_items(itemid) ON DELETE CASCADE,
  roleid BIGINT NOT NULL
);

CREATE TABLE member_inventory(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  itemid INTEGER NOT NULL REFERENCES shop_items(itemid) ON DELETE CASCADE,
  count INTEGER DEFAULT 1,
  PRIMARY KEY(guildid, userid)
);


CREATE VIEW shop_item_info AS
  SELECT
    *,
    row_number() OVER (PARTITION BY guildid ORDER BY itemid) AS guild_itemid
  FROM
    shop_items
  LEFT JOIN shop_items_colour_roles USING (itemid)
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

CREATE TYPE TicketType AS ENUM (
  'NOTE',
  'STUDY_BAN',
  'MESSAGE_CENSOR',
  'INVITE_CENSOR',
  'WARNING'
);

CREATE TABLE tickets(
  ticketid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  targetid BIGINT NOT NULL,
  ticket_type TicketType NOT NULL, 
  moderator_id BIGINT NOT NULL,
  log_msg_id BIGINT,
  created_at TIMESTAMP DEFAULT (now() at time zone 'utc'),
  content TEXT,
  expiry TIMESTAMP,
  auto BOOLEAN DEFAULT FALSE,
  pardoned BOOLEAN DEFAULT FALSE,
  pardoned_by BIGINT,
  pardoned_at TIMESTAMP,
  pardoned_reason TEXT
);
CREATE INDEX tickets_members_types ON tickets (guildid, targetid, ticket_type);

CREATE TABLE study_bans(
  ticketid INTEGER REFERENCES tickets(ticketid),
  study_ban_duration INTEGER
); 
CREATE INDEX study_ban_tickets ON study_bans (ticketid);

CREATE TABLE study_ban_auto_durations(
  rowid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  duration INTEGER NOT NULL
);
CREATE INDEX study_ban_auto_durations_guilds ON study_ban_auto_durations (guildid);


CREATE VIEW ticket_info AS
  SELECT
    *,
    row_number() OVER (PARTITION BY guildid ORDER BY ticketid) AS guild_ticketid
  FROM tickets
  LEFT JOIN study_bans USING (ticketid)
  ORDER BY ticketid;
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
  _timestamp TIMESTAMP DEFAULT (now() at time zone 'utc'),
  PRIMARY KEY(guildid, userid)
);
CREATE INDEX member_timestamps ON members (_timestamp);

CREATE TRIGGER update_members_timstamp BEFORE UPDATE
ON members FOR EACH ROW EXECUTE PROCEDURE 
update_timestamp_column();

CREATE VIEW member_ranks AS
  SELECT
    *,
    row_number() OVER (PARTITION BY guildid ORDER BY tracked_time DESC, userid ASC) AS time_rank,
    row_number() OVER (PARTITION BY guildid ORDER BY coins DESC, userid ASC) AS coin_rank
  FROM members;


CREATE VIEW current_study_badges AS
  SELECT
    *,
    (SELECT r.badgeid
      FROM study_badges r
      WHERE r.guildid = members.guildid AND members.tracked_time > r.required_time
      ORDER BY r.required_time DESC
      LIMIT 1) AS current_study_badgeid
    FROM members;

CREATE VIEW new_study_badges AS
  SELECT 
    current_study_badges.*
  FROM current_study_badges
  WHERE
    last_study_badgeid IS DISTINCT FROM current_study_badgeid
  ORDER BY guildid;
-- }}}

-- Rented Room data {{{
CREATE TABLE rented(
  channelid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL,
  ownerid BIGINT NOT NULL,
  expires_at TIMESTAMP DEFAULT ((now() at time zone 'utc') + INTERVAL '1 day'),
  created_at TIMESTAMP DEFAULT (now() at time zone 'utc'),
  FOREIGN KEY (guildid, ownerid) REFERENCES members (guildid, userid) ON DELETE CASCADE
);
CREATE UNIQUE INDEX rented_owners ON rented (guildid, ownerid);

CREATE TABLE rented_members(
  channelid BIGINT NOT NULL REFERENCES rented(channelid) ON DELETE CASCADE,
  userid BIGINT NOT NULL
);
CREATE INDEX rented_members_channels ON rented_members (channelid);
-- }}}

-- Accountability Rooms {{{
CREATE TABLE accountability_slots(
  slotid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL REFERENCES guild_config(guildid),
  channelid BIGINT,
  start_at TIMESTAMPTZ (0) NOT NULL,
  messageid BIGINT,
  closed_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX slot_channels ON accountability_slots(channelid);
CREATE UNIQUE INDEX slot_guilds ON accountability_slots(guildid, start_at);
CREATE INDEX slot_times ON accountability_slots(start_at);

CREATE TABLE accountability_members(
  slotid INTEGER NOT NULL REFERENCES accountability_slots(slotid) ON DELETE CASCADE,
  userid BIGINT NOT NULL,
  paid INTEGER NOT NULL,
  duration INTEGER DEFAULT 0,
  last_joined_at TIMESTAMPTZ,
  PRIMARY KEY (slotid, userid)
);
CREATE INDEX slot_members ON accountability_members(userid);
CREATE INDEX slot_members_slotid ON accountability_members(slotid);

CREATE VIEW accountability_member_info AS
  SELECT
    *
  FROM accountability_members
  JOIN accountability_slots USING (slotid);

CREATE VIEW accountability_open_slots AS
  SELECT
    *
  FROM accountability_slots
  WHERE closed_at IS NULL
  ORDER BY start_at ASC;
-- }}}
-- vim: set fdm=marker:

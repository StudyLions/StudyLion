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
  study_hourly_live_bonus INTEGER
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
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  content TEXT NOT NULL,
  complete BOOL DEFAULT FALSE,
  rewarded BOOL DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT (now() at time zone 'utc'),
  last_updated_at TIMESTAMP DEFAULT (now() at time zone 'utc')
);
CREATE INDEX tasklist_members ON tasklist (guildid, userid);

CREATE TABLE tasklist_channels(
  guildid BIGINT NOT NULL,
  channelid BIGINT NOT NULL
);
CREATE INDEX tasklist_channels_guilds ON tasklist_channels (guildid);

CREATE TABLE tasklist_reward_history(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  reward_time TIMESTAMP DEFAULT (now() at time zone 'utc'),
  reward_count INTEGER
);
CREATE INDEX tasklist_reward_history_members ON tasklist_reward_history (guildid, userid, reward_time);
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

-- vim: set fdm=marker

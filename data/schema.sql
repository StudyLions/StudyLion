-- Metadata {{{
CREATE TABLE VersionHistory(
  version INTEGER NOT NULL,
  time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
  author TEXT
);
INSERT INTO VersionHistory (version, author) VALUES (5, 'Initial Creation');


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
  alert_channel BIGINT,
  coin_alert_channel BIGINT,
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
  persist_roles BOOLEAN
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
  last_study_session_start TIMESTAMP,
  last_workout_start TIMESTAMP,
  session_start_coins INTEGER DEFAULT 0,
  last_study_badgeid INTEGER REFERENCES study_badges ON DELETE SET NULL,
  video_warned BOOLEAN DEFAULT FALSE,
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
CREATE INDEX rented_members_users ON rented_members (userid);
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

-- Reaction Roles {{{
CREATE TABLE reaction_role_messages(
  messageid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL REFERENCES guild_config (guildid) ON DELETE CASCADE,
  channelid BIGINT NOT NULL,
  enabled BOOLEAN DEFAULT TRUE,
  required_role BIGINT,
  removable BOOLEAN,
  maximum INTEGER,
  refunds BOOLEAN,
  event_log BOOLEAN,
  default_price INTEGER
);
CREATE INDEX reaction_role_guilds ON reaction_role_messages (guildid);

CREATE TABLE reaction_role_reactions(
  reactionid SERIAL PRIMARY KEY,
  messageid BIGINT NOT NULL REFERENCES reaction_role_messages (messageid) ON DELETE CASCADE,
  roleid BIGINT NOT NULL,
  emoji_name TEXT,
  emoji_id BIGINT,
  emoji_animated BOOLEAN,
  price INTEGER,
  timeout INTEGER
);
CREATE INDEX reaction_role_reaction_messages ON reaction_role_reactions (messageid);

CREATE TABLE reaction_role_expiring(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  expiry TIMESTAMPTZ NOT NULL,
  reactionid INTEGER REFERENCES reaction_role_reactions (reactionid) ON DELETE SET NULL
);
CREATE UNIQUE INDEX reaction_role_expiry_members ON reaction_role_expiring (guildid, userid, roleid);

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
-- vim: set fdm=marker:

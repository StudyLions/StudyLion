DROP TABLE IF EXISTS schedule_slots CASCADE;
DROP TABLE IF EXISTS schedule_guild_config CASCADE;
DROP TABLE IF EXISTS schedule_channels CASCADE;
DROP TABLE IF EXISTS schedule_sessions CASCADE;
DROP TABLE IF EXISTS schedule_session_members CASCADE;

-- Create new schema

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

-- Migrate data
--- Create schedule_slots from accountability_slots
INSERT INTO schedule_slots (slotid)
  SELECT EXTRACT(EPOCH FROM old_slots.start_time)
  FROM (SELECT DISTINCT(start_at) AS start_time FROM accountability_slots) AS old_slots;

--- Create schedule_guild_config from guild_config
INSERT INTO schedule_guild_config (guildid, schedule_cost, reward, bonus_reward, lobby_channel)
  SELECT guildid, accountability_price, accountability_reward, accountability_bonus, accountability_lobby
  FROM guild_config
  WHERE guildid IN (SELECT DISTINCT(guildid) FROM accountability_slots);

--- Update session rooms from accountability_slots
WITH open_slots AS (
  SELECT guildid, MAX(channelid) AS channelid
  FROM accountability_slots
  WHERE closed_at IS NULL
  GROUP BY guildid
)
UPDATE schedule_guild_config
SET room_channel = open_slots.channelid
FROM open_slots
WHERE schedule_guild_config.guildid = open_slots.guildid;

--- Create schedule_sessions from accountability_slots
INSERT INTO schedule_sessions (guildid, slotid, opened_at, closed_at)
  SELECT guildid, new_slots.slotid, start_at, closed_at
  FROM accountability_slots old_slots
  LEFT JOIN schedule_slots new_slots
  ON EXTRACT(EPOCH FROM old_slots.start_at) = new_slots.slotid;

--- Create schedule_session_members from accountability_members
INSERT INTO schedule_session_members (guildid, userid, slotid, booked_at, attended, clock)
  SELECT old_slots.guildid, members.userid, new_slots.slotid, old_slots.start_at, (members.duration > 0), members.duration
  FROM accountability_members members
  LEFT JOIN accountability_slots old_slots ON members.slotid = old_slots.slotid
  LEFT JOIN schedule_slots new_slots
  ON EXTRACT(EPOCH FROM old_slots.start_at) = new_slots.slotid;

-- Drop old schema

-- DROP TYPE IF EXISTS SessionChannelType CASCADE;
-- DROP TABLE IF EXISTS session_history CASCADE;
-- DROP TABLE IF EXISTS current_sessions CASCADE;
-- DROP FUNCTION IF EXISTS close_study_session(_guildid BIGINT, _userid BIGINT);
-- DROP FUNCTION IF EXISTS study_time_since(_guildid BIGINT, _userid BIGINT, _timestamp TIMESTAMPTZ)

-- DROP VIEW IF EXISTS current_sessions_totals CASCADE;

DROP VIEW IF EXISTS member_totals CASCADE;
DROP VIEW IF EXISTS member_ranks CASCADE;
DROP VIEW IF EXISTS current_study_badges CASCADE;
DROP VIEW IF EXISTS new_study_badges CASCADE;


CREATE TYPE SessionChannelType AS ENUM (
  'STANDARD',
  'ACCOUNTABILITY',
  'RENTED',
  'EXTERNAL'
);

CREATE TABLE session_history(
  sessionid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  channelid BIGINT,
  channel_type SessionChannelType,
  start_time TIMESTAMPTZ NOT NULL,
  duration INTEGER NOT NULL,
  coins_earned INTEGER NOT NULL,
  live_duration INTEGER DEFAULT 0,
  stream_duration INTEGER DEFAULT 0,
  video_duration INTEGER DEFAULT 0,
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
);
CREATE INDEX session_history_members ON session_history (guildid, userid, start_time);

CREATE TABLE current_sessions(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  channelid BIGINT,
  channel_type SessionChannelType,
  start_time TIMESTAMPTZ DEFAULT now(),
  live_duration INTEGER DEFAULT 0,
  live_start TIMESTAMPTZ,
  stream_duration INTEGER DEFAULT 0,
  stream_start TIMESTAMPTZ,
  video_duration INTEGER DEFAULT 0,
  video_start TIMESTAMPTZ,
  hourly_coins INTEGER NOT NULL,
  hourly_live_coins INTEGER NOT NULL,
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
);
CREATE UNIQUE INDEX current_session_members ON current_sessions (guildid, userid);


CREATE FUNCTION close_study_session(_guildid BIGINT, _userid BIGINT)
  RETURNS SETOF members
AS $$
  BEGIN
    RETURN QUERY
    WITH 
      current_sesh AS (
        DELETE FROM current_sessions
        WHERE guildid=_guildid AND userid=_userid
        RETURNING
          *,
          EXTRACT(EPOCH FROM (NOW() - start_time)) AS total_duration,
          stream_duration + COALESCE(EXTRACT(EPOCH FROM (NOW() - stream_start)), 0) AS total_stream_duration,
          video_duration + COALESCE(EXTRACT(EPOCH FROM (NOW() - video_start)), 0) AS total_video_duration,
          live_duration + COALESCE(EXTRACT(EPOCH FROM (NOW() - live_start)), 0) AS total_live_duration
      ), saved_sesh AS (
        INSERT INTO session_history (
          guildid, userid, channelid, channel_type, start_time,
          duration, stream_duration, video_duration, live_duration,
          coins_earned
        ) SELECT
          guildid, userid, channelid, channel_type, start_time,
          total_duration, total_stream_duration, total_video_duration, total_live_duration,
          (total_duration * hourly_coins + live_duration * hourly_live_coins) / 3600
        FROM current_sesh
        RETURNING *
      )
    UPDATE members
      SET
        tracked_time=(tracked_time + saved_sesh.duration),
        coins=(coins + saved_sesh.coins_earned)
      FROM saved_sesh
      WHERE members.guildid=saved_sesh.guildid AND members.userid=saved_sesh.userid
      RETURNING members.*;
  END;
$$ LANGUAGE PLPGSQL;



CREATE VIEW current_sessions_totals AS
  SELECT
    *,
    EXTRACT(EPOCH FROM (NOW() - start_time)) AS total_duration,
    stream_duration + COALESCE(EXTRACT(EPOCH FROM (NOW() - stream_start)), 0) AS total_stream_duration,
    video_duration + COALESCE(EXTRACT(EPOCH FROM (NOW() - video_start)), 0) AS total_video_duration,
    live_duration + COALESCE(EXTRACT(EPOCH FROM (NOW() - live_start)), 0) AS total_live_duration
  FROM current_sessions;


CREATE VIEW members_totals AS
  SELECT
    *,
    sesh.start_time AS session_start,
    tracked_time + COALESCE(sesh.total_duration, 0) AS total_tracked_time,
    coins + COALESCE((sesh.total_duration * sesh.hourly_coins + sesh.live_duration * sesh.hourly_live_coins) / 3600, 0) AS total_coins
  FROM members
  LEFT JOIN current_sessions_totals sesh USING (guildid, userid);


CREATE VIEW member_ranks AS
  SELECT
    *,
    row_number() OVER (PARTITION BY guildid ORDER BY total_tracked_time DESC, userid ASC) AS time_rank,
    row_number() OVER (PARTITION BY guildid ORDER BY total_coins DESC, userid ASC) AS coin_rank
  FROM members_totals;

CREATE VIEW current_study_badges AS
  SELECT
    *,
    (SELECT r.badgeid
      FROM study_badges r
      WHERE r.guildid = members_totals.guildid AND members_totals.total_tracked_time > r.required_time
      ORDER BY r.required_time DESC
      LIMIT 1) AS current_study_badgeid
    FROM members_totals;

CREATE VIEW new_study_badges AS
  SELECT 
    current_study_badges.*
  FROM current_study_badges
  WHERE
    last_study_badgeid IS DISTINCT FROM current_study_badgeid
  ORDER BY guildid;


CREATE FUNCTION study_time_since(_guildid BIGINT, _userid BIGINT, _timestamp TIMESTAMPTZ)
  RETURNS INTEGER
AS $$
  BEGIN
    RETURN (
      SELECT
          SUM(
            CASE
              WHEN start_time >= _timestamp THEN duration
              ELSE EXTRACT(EPOCH FROM (end_time - _timestamp))
            END
          )
      FROM (
        SELECT
          start_time,
          duration,
          (start_time + duration * interval '1 second') AS end_time
        FROM session_history
        WHERE
          guildid=_guildid
          AND userid=_userid
          AND (start_time + duration * interval '1 second') >= _timestamp
        UNION
        SELECT
          start_time,
          EXTRACT(EPOCH FROM (NOW() - start_time)) AS duration,
          NOW() AS end_time
        FROM current_sessions
        WHERE
          guildid=_guildid
          AND userid=_userid
      ) AS sessions
    );
  END;
$$ LANGUAGE PLPGSQL;

ALTER TABLE guild_config ADD COLUMN daily_study_cap INTEGER;

INSERT INTO VersionHistory (version, author) VALUES (6, 'v5-v6 Migration');

-- Add coin cap to close_study_session
DROP FUNCTION close_study_session(_guildid BIGINT, _userid BIGINT);

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
      ), bonus_userid AS (
        SELECT COUNT(boostedTimestamp), 
          CASE WHEN EXISTS (
            SELECT 1 FROM Topgg
            WHERE Topgg.userid=_userid AND EXTRACT(EPOCH FROM (NOW() - boostedTimestamp)) < 12.5*60*60
          ) THEN
          (array_agg( 
            CASE WHEN boostedTimestamp <= current_sesh.start_time THEN
              1.25
            ELSE
              (((current_sesh.total_duration - EXTRACT(EPOCH FROM (boostedTimestamp - current_sesh.start_time)))/current_sesh.total_duration)*0.25)+1
            END))[1]
          ELSE
            1
          END
          AS bonus
        FROM Topgg, current_sesh 
        WHERE Topgg.userid=_userid AND EXTRACT(EPOCH FROM (NOW() - boostedTimestamp)) < 12.5*60*60
        ORDER BY (array_agg(boostedTimestamp))[1] DESC LIMIT 1         
      ), saved_sesh AS (
        INSERT INTO session_history (
          guildid, userid, channelid, rating, tag, channel_type, start_time,
          duration, stream_duration, video_duration, live_duration,
          coins_earned
        ) SELECT
          guildid, userid, channelid, rating, tag, channel_type, start_time,
          total_duration, total_stream_duration, total_video_duration, total_live_duration,
          ((total_duration * hourly_coins + live_duration * hourly_live_coins) * bonus_userid.bonus )/ 3600
        FROM current_sesh, bonus_userid
        RETURNING *
      )
    UPDATE members
      SET
        tracked_time=(tracked_time + saved_sesh.duration),
        coins=LEAST(coins + saved_sesh.coins_earned, 2147483647)
      FROM saved_sesh
      WHERE members.guildid=saved_sesh.guildid AND members.userid=saved_sesh.userid
      RETURNING members.*;
  END;
$$ LANGUAGE PLPGSQL;


-- Add support for NULL guildid
DROP FUNCTION study_time_since(_guildid BIGINT, _userid BIGINT, _timestamp TIMESTAMPTZ);

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
          (_guildid IS NULL OR guildid=_guildid)
          AND userid=_userid
          AND (start_time + duration * interval '1 second') >= _timestamp
        UNION
        SELECT
          start_time,
          EXTRACT(EPOCH FROM (NOW() - start_time)) AS duration,
          NOW() AS end_time
        FROM current_sessions
        WHERE
          (_guildid IS NULL OR guildid=_guildid)
          AND userid=_userid
      ) AS sessions
    );
  END;
$$ LANGUAGE PLPGSQL;


-- Rebuild study data views
DROP VIEW current_sessions_totals CASCADE;

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


-- API changes
ALTER TABLE user_config ADD COLUMN API_timestamp BIGINT;


INSERT INTO VersionHistory (version, author) VALUES (10, 'v9-v10 migration');

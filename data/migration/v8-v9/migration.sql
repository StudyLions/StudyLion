ALTER TABLE user_config
  ADD COLUMN topgg_vote_reminder BOOLEAN;

ALTER TABLE reminders
  ADD COLUMN title TEXT,
  ADD COLUMN footer TEXT;

-- Topgg Data {{{
CREATE TABLE IF NOT EXISTS topgg(
  voteid SERIAL PRIMARY KEY,
  userid BIGINT NOT NULL,
  boostedTimestamp TIMESTAMPTZ NOT NULL
);
CREATE INDEX topgg_userid_timestamp ON topgg (userid, boostedTimestamp);
-- }}}

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
        coins=(coins + saved_sesh.coins_earned)
      FROM saved_sesh
      WHERE members.guildid=saved_sesh.guildid AND members.userid=saved_sesh.userid
      RETURNING members.*;
  END;
$$ LANGUAGE PLPGSQL;
-- }}}


ALTER TABLE user_config
  ADD COLUMN avatar_hash TEXT;

ALTER TABLE guild_config
  ADD COLUMN name TEXT;

ALTER TABLE members
  ADD COLUMN display_name TEXT;


INSERT INTO VersionHistory (version, author) VALUES (9, 'v8-v9 migration');

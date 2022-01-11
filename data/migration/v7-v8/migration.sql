ALTER TABLE guild_config ADD COLUMN pomodoro_channel BIGINT;

-- Timer Data {{{
create TABLE timers(
  channelid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL REFERENCES guild_config (guildid),
  text_channelid BIGINT,
  focus_length INTEGER NOT NULL,
  break_length INTEGER NOT NULL,
  last_started TIMESTAMPTZ NOT NULL,
  inactivity_threshold INTEGER,
  channel_name TEXT,
  pretty_name TEXT
);
CREATE INDEX timers_guilds ON timers (guildid);
-- }}}

-- Session tags {{{
ALTER TABLE current_sessions
  ADD COLUMN rating INTEGER,
  ADD COLUMN tag TEXT;

ALTER TABLE session_history
  ADD COLUMN rating INTEGER,
  ADD COLUMN tag TEXT;

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
      ), saved_sesh AS (
        INSERT INTO session_history (
          guildid, userid, channelid, rating, tag, channel_type, start_time,
          duration, stream_duration, video_duration, live_duration,
          coins_earned
        ) SELECT
          guildid, userid, channelid, rating, tag, channel_type, start_time,
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
-- }}}

INSERT INTO VersionHistory (version, author) VALUES (8, 'v7-v8 migration');

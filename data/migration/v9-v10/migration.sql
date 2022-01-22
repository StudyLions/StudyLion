DROP VIEW current_sessions_totals CASCADE;


-- Rebuild study data views
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

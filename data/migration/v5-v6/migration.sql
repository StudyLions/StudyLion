ALTER TABLE guild_config
  ADD COLUMN coin_alert_channel BIGINT;

ALTER TABLE members
  ADD COLUMN last_study_session_start TIMESTAMP,
  ADD COLUMN session_start_coins INTEGER DEFAULT 0;
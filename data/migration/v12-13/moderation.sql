DROP TABLE IF EXISTS video_exempt_roles CASCADE;
UPDATE guild_config SET studyban_role = NULL WHERE video_studyban = False;

CREATE TABLE video_exempt_roles(
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  _timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE ON UPDATE CASCADE,
  PRIMARY KEY (guildid, roleid)
);

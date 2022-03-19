-- App Config Data {{{
CREATE TABLE AppConfig(
  appid TEXT,
  key TEXT,
  value TEXT,
  PRIMARY KEY(appid, key)
);
-- }}}


-- Sponsor Data {{{
CREATE TABLE sponsor_guild_whitelist(
  appid TEXT,
  guildid BIGINT,
  PRIMARY KEY(appid, guildid)
);
-- }}}

-- Topgg Data {{{
CREATE TABLE topgg_guild_whitelist(
  appid TEXT,
  guildid BIGINT,
  PRIMARY KEY(appid, guildid)
);
-- }}}

INSERT INTO VersionHistory (version, author) VALUES (11, 'v10-v11 migration');

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

CREATE TABLE ignored_members(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL
);
CREATE INDEX ignored_member_guilds ON ignored_members (guildid);


INSERT INTO VersionHistory (version, author) VALUES (3, 'v2-v3 Migration');

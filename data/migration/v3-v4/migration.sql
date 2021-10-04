ALTER TABLE guild_config
  ADD COLUMN greeting_channel BIGINT,
  ADD COLUMN greeting_message TEXT,
  ADD COLUMN returning_message TEXT,
  ADD COLUMN starting_funds INTEGER,
  ADD COLUMN persist_roles BOOLEAN;

CREATE INDEX rented_members_users ON rented_members (userid);

CREATE TABLE autoroles(
  guildid BIGINT NOT NULL ,
  roleid BIGINT NOT NULL
);
CREATE INDEX autoroles_guilds ON autoroles (guildid);

CREATE TABLE bot_autoroles(
  guildid BIGINT NOT NULL ,
  roleid BIGINT NOT NULL
);
CREATE INDEX bot_autoroles_guilds ON bot_autoroles (guildid);

CREATE TABLE past_member_roles(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid)
);
CREATE INDEX member_role_persistence_members ON past_member_roles (guildid, userid);

INSERT INTO VersionHistory (version, author) VALUES (4, 'v3-v4 Migration');

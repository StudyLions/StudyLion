CREATE TABLE reaction_role_messages(
  messageid BIGINT PRIMARY KEY,
  guildid BIGINT NOT NULL REFERENCES guild_config (guildid) ON DELETE CASCADE,
  channelid BIGINT NOT NULL,
  enabled BOOLEAN DEFAULT TRUE,
  required_role BIGINT,
  removable BOOLEAN,
  maximum INTEGER,
  refunds BOOLEAN,
  event_log BOOLEAN,
  default_price INTEGER
);
CREATE INDEX reaction_role_guilds ON reaction_role_messages (guildid);

CREATE TABLE reaction_role_reactions(
  reactionid SERIAL PRIMARY KEY,
  messageid BIGINT NOT NULL REFERENCES reaction_role_messages (messageid) ON DELETE CASCADE,
  roleid BIGINT NOT NULL,
  emoji_name TEXT,
  emoji_id BIGINT,
  emoji_animated BOOLEAN,
  price INTEGER,
  timeout INTEGER
);
CREATE INDEX reaction_role_reaction_messages ON reaction_role_reactions (messageid);

CREATE TABLE reaction_role_expiring(
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  expiry TIMESTAMPTZ NOT NULL,
  reactionid INTEGER REFERENCES reaction_role_reactions (reactionid) ON DELETE SET NULL
);
CREATE UNIQUE INDEX reaction_role_expiry_members ON reaction_role_expiring (guildid, userid, roleid);

INSERT INTO VersionHistory (version, author) VALUES (5, 'v4-v5 Migration');

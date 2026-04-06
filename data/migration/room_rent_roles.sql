-- Room Rent Role Gate: Two tables for configuring role requirements on /room rent
-- Safe to run on any database version (uses IF NOT EXISTS)

CREATE TABLE IF NOT EXISTS room_rent_required_roles(
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE ON UPDATE CASCADE,
  PRIMARY KEY (guildid, roleid)
);

CREATE TABLE IF NOT EXISTS room_rent_anyof_roles(
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE ON UPDATE CASCADE,
  PRIMARY KEY (guildid, roleid)
);

GRANT ALL ON room_rent_required_roles TO leo;
GRANT ALL ON room_rent_anyof_roles TO leo;

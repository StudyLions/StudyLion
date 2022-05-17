-- Add gem support
ALTER TABLE user_config ADD COLUMN gems INTEGER DEFAULT 0;

-- LionGem audit log {{{
CREATE TYPE GemTransactionType AS ENUM (
  'ADMIN',
  'GIFT',
  'PURCHASE',
  'AUTOMATIC'
);

CREATE TABLE gem_transactions(
  transactionid SERIAL PRIMARY KEY,
  transaction_type GemTransactionType NOT NULL,
  actorid BIGINT NOT NULL,
  from_account BIGINT,
  to_account BIGINT,
  amount INTEGER NOT NULL,
  description TEXT NOT NULL,
  note TEXT,
  reference TEXT,
  _timestamp TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX gem_transactions_from ON gem_transactions (from_account);
-- }}}

-- Skin Data {{{
CREATE TABLE global_available_skins(
  skin_id SERIAL PRIMARY KEY,
  skin_name TEXT NOT NULL
);
CREATE INDEX global_available_skin_names ON global_available_skins (skin_name);

CREATE TABLE customised_skins(
  custom_skin_id SERIAL PRIMARY KEY,
  base_skin_id INTEGER REFERENCES global_available_skins (skin_id),
  _timestamp TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE customised_skin_property_ids(
  property_id SERIAL PRIMARY KEY,
  card_id TEXT NOT NULL,
  property_name TEXT NOT NULL,
  UNIQUE(card_id, property_name)
);

CREATE TABLE customised_skin_properties(
  custom_skin_id INTEGER NOT NULL REFERENCES customised_skins (custom_skin_id),
  property_id INTEGER NOT NULL REFERENCES customised_skin_property_ids (property_id),
  value TEXT NOT NULL,
  PRIMARY KEY (custom_skin_id, property_id)
);
CREATE INDEX customised_skin_property_skin_id ON customised_skin_properties(custom_skin_id);

CREATE VIEW customised_skin_data AS
  SELECT
    skins.custom_skin_id AS custom_skin_id,
    skins.base_skin_id AS base_skin_id,
    properties.property_id AS property_id,
    prop_ids.card_id AS card_id,
    prop_ids.property_name AS property_name,
    properties.value AS value
  FROM
    customised_skins skins
  LEFT JOIN customised_skin_properties properties ON skins.custom_skin_id = properties.custom_skin_id
  LEFT JOIN customised_skin_property_ids prop_ids ON properties.property_id = prop_ids.property_id;


CREATE TABLE user_skin_inventory(
  itemid SERIAL PRIMARY KEY,
  userid BIGINT NOT NULL REFERENCES user_config (userid) ON DELETE CASCADE,
  custom_skin_id INTEGER NOT NULL REFERENCES customised_skins (custom_skin_id) ON DELETE CASCADE,
  transactionid INTEGER REFERENCES gem_transactions (transactionid),
  active BOOLEAN NOT NULL DEFAULT FALSE,
  acquired_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ
);
CREATE INDEX user_skin_inventory_users ON user_skin_inventory(userid);
CREATE UNIQUE INDEX user_skin_inventory_active ON user_skin_inventory(userid) WHERE active = TRUE;

CREATE VIEW user_active_skins AS
  SELECT
    *
  FROM user_skin_inventory
  WHERE active=True;
-- }}}


-- Premium Guild Data {{{
CREATE TABLE premium_guilds(
  guildid BIGINT PRIMARY KEY REFERENCES guild_config,
  premium_since TIMESTAMPTZ NOT NULL DEFAULT now(),
  premium_until TIMESTAMPTZ NOT NULL DEFAULT now(),
  custom_skin_id INTEGER REFERENCES customised_skins
);

-- Contributions members have made to guild premium funds
CREATE TABLE premium_guild_contributions(
  contributionid SERIAL PRIMARY KEY,
  userid BIGINT NOT NULL REFERENCES user_config,
  guildid BIGINT NOT NULL REFERENCES premium_guilds,
  transactionid INTEGER REFERENCES gem_transactions,
  duration INTEGER NOT NULL,
  _timestamp TIMESTAMPTZ DEFAULT now()
);
-- }}}

INSERT INTO VersionHistory (version, author) VALUES (12, 'v11-v12 migration');

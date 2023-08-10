DROP TABLE IF EXISTS role_menu_history CASCADE;
DROP TABLE IF EXISTS role_menu_roles CASCADE;
DROP TABLE IF EXISTS role_menus CASCADE;
DROP TYPE IF EXISTS RoleMenuType;


CREATE TYPE RoleMenuType AS ENUM(
    'REACTION',
    'BUTTON',
    'DROPDOWN'
);


CREATE TABLE role_menus(
    menuid SERIAL PRIMARY KEY,
    guildid BIGINT NOT NULL REFERENCES guild_config (guildid) ON DELETE CASCADE,
    channelid BIGINT,
    messageid BIGINT,
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT True,
    required_roleid BIGINT,
    sticky BOOLEAN,
    refunds BOOLEAN,
    obtainable INTEGER,
    menutype RoleMenuType NOT NULL,
    templateid INTEGER,
    rawmessage TEXT,
    default_price INTEGER,
    event_log BOOLEAN
);
CREATE INDEX role_menu_guildid ON role_menus (guildid);



CREATE TABLE role_menu_roles(
    menuroleid SERIAL PRIMARY KEY,
    menuid INTEGER NOT NULL REFERENCES role_menus (menuid) ON DELETE CASCADE,
    roleid BIGINT NOT NULL,
    label TEXT NOT NULL,
    emoji TEXT,
    description TEXT,
    price INTEGER,
    duration INTEGER,
    rawreply TEXT
);
CREATE INDEX role_menu_roles_menuid ON role_menu_roles (menuid);
CREATE INDEX role_menu_roles_roleid ON role_menu_roles (roleid);


CREATE TABLE role_menu_history(
    equipid SERIAL PRIMARY KEY,
    menuid INTEGER NOT NULL REFERENCES role_menus (menuid) ON DELETE CASCADE,
    roleid BIGINT NOT NULL,
    userid BIGINT NOT NULL,
    obtained_at TIMESTAMPTZ NOT NULL,
    transactionid INTEGER REFERENCES coin_transactions (transactionid) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ,
    removed_at TIMESTAMPTZ
);
CREATE INDEX role_menu_history_menuid ON role_menu_history (menuid);
CREATE INDEX role_menu_history_roleid ON role_menu_history (roleid);


-- Migration
INSERT INTO role_menus (messageid, guildid, channelid, enabled, required_roleid, sticky, obtainable, refunds, event_log, default_price, name, menutype)
  SELECT
    messageid, guildid, channelid, enabled,
    required_role, NOT removable, maximum,
    refunds, event_log, default_price, messageid :: TEXT,
    'REACTION'
  FROM reaction_role_messages;

INSERT INTO role_menu_roles (menuid, roleid, label, emoji, price, duration)
  SELECT
    role_menus.menuid, reactions.roleid, reactions.roleid::TEXT,
    COALESCE('<:' || reactions.emoji_name || ':' || reactions.emoji_id :: TEXT || '>', reactions.emoji_name),
    reactions.price, reactions.timeout
  FROM reaction_role_reactions reactions
  LEFT JOIN role_menus
    ON role_menus.messageid = reactions.messageid;

INSERT INTO role_menu_history (menuid, roleid, userid, obtained_at, expires_at)
  SELECT
    rmr.menuid, expiring.roleid, expiring.userid, NOW(), expiring.expiry
  FROM reaction_role_expiring expiring
  LEFT JOIN role_menu_roles rmr
    ON rmr.roleid = expiring.roleid
  WHERE rmr.menuid IS NOT NULL;


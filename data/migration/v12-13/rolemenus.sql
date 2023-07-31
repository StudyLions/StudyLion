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
    rawmessage TEXT
);


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


CREATE TABLE role_menu_history(
    equipid SERIAL PRIMARY KEY,
    menuid INTEGER NOT NULL REFERENCES role_menus (menuid) ON DELETE CASCADE,
    roleid BIGINT NOT NULL,
    userid BIGINT NOT NULL,
    obtained_at TIMESTAMPTZ NOT NULL,
    transactionid INTEGER REFERENCES coin_transactions (transactionid) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ,
    expired_at TIMESTAMPTZ
);

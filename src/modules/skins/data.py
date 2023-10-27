from data import Registry, RowModel, Table
from data.columns import Integer, Bool, Timestamp, String


class CustomSkinData(Registry):
    class GlobalSkin(RowModel):
        """
        Schema
        ------
        CREATE TABLE global_available_skins(
          skin_id SERIAL PRIMARY KEY,
          skin_name TEXT NOT NULL
        );
        CREATE INDEX global_available_skin_names ON global_available_skins (skin_name);
        """
        _tablename_ = 'global_available_skins'
        _cache_ = {}

        skin_id = Integer(primary=True)
        skin_name = String()

    class CustomisedSkin(RowModel):
        """
        Schema
        ------
        CREATE TABLE customised_skins(
          custom_skin_id SERIAL PRIMARY KEY,
          base_skin_id INTEGER REFERENCES global_available_skins (skin_id),
          _timestamp TIMESTAMPTZ DEFAULT now()
        );
        """
        _tablename_ = 'customised_skins'

        custom_skin_id = Integer(primary=True)
        base_skin_id = Integer()

        _timestamp = Timestamp()

    """
    Schema
    ------
    CREATE TABLE customised_skin_property_ids(
      property_id SERIAL PRIMARY KEY,
      card_id TEXT NOT NULL,
      property_name TEXT NOT NULL,
      UNIQUE(card_id, property_name)
    );
    """
    skin_property_map = Table('customised_skin_property_ids')

    """
    Schema
    ------
    CREATE TABLE customised_skin_properties(
      custom_skin_id INTEGER NOT NULL REFERENCES customised_skins (custom_skin_id),
      property_id INTEGER NOT NULL REFERENCES customised_skin_property_ids (property_id),
      value TEXT NOT NULL,
      PRIMARY KEY (custom_skin_id, property_id)
    );
    CREATE INDEX customised_skin_property_skin_id ON customised_skin_properties(custom_skin_id);
    """
    skin_properties = Table('customised_skin_properties')

    """
    Schema
    ------
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
    """
    custom_skin_info = Table('customised_skin_data')

    class UserSkin(RowModel):
        """
        Schema
        ------
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
        """
        _tablename_ = 'user_skin_inventory'

        itemid = Integer(primary=True)
        userid = Integer()
        custom_skin_id = Integer()
        transactionid = Integer()
        active = Bool()
        acquired_at = Timestamp()
        expires_at = Timestamp()

    """
    Schema
    ------
    CREATE VIEW user_active_skins AS
      SELECT
        *
      FROM user_skin_inventory
      WHERE active=True;
    """
    user_active_skins = Table('user_active_skins')

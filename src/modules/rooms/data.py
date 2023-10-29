from data import Registry, RowModel
from data.columns import Integer, Timestamp, String


class RoomData(Registry):
    class Room(RowModel):
        """
        CREATE TABLE rented_rooms(
          channelid BIGINT PRIMARY KEY,
          guildid BIGINT NOT NULL,
          ownerid BIGINT NOT NULL,
          coin_balance INTEGER NOT NULL DEFAULT 0,
          name TEXT,
          created_at TIMESTAMPTZ DEFAULT now(),
          last_tick TIMESTAMPTZ,
          deleted_at TIMESTAMPTZ,
          FOREIGN KEY (guildid, ownerid) REFERENCES members (guildid, userid) ON DELETE CASCADE
        );
        CREATE INDEX rented_owners ON rented (guildid, ownerid);
        """
        _tablename_ = 'rented_rooms'

        channelid = Integer(primary=True)
        guildid = Integer()
        ownerid = Integer()
        coin_balance = Integer()
        name = String()
        created_at = Timestamp()
        last_tick = Timestamp()
        deleted_at = Timestamp()

    class RoomMember(RowModel):
        """
        Schema
        ------
        CREATE TABLE rented_members(
          channelid BIGINT NOT NULL REFERENCES rented(channelid) ON DELETE CASCADE,
          userid BIGINT NOT NULL,
          contribution INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX rented_members_channels ON rented_members (channelid);
        CREATE INDEX rented_members_users ON rented_members (userid);
        """
        _tablename_ = 'rented_members'

        channelid = Integer(primary=True)
        userid = Integer(primary=True)
        contribution = Integer()

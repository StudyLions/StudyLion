from data import Registry, RowModel, Table
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
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Freeze support for admin panel
        frozen_at = Timestamp()
        frozen_by = Integer()
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: Dashboard rename support -- set to NOW() by dashboard,
        # cleared by bot after syncing to Discord. NULL = no pending rename.
        name_changed_at = Timestamp()
        # --- END AI-MODIFIED ---

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

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Tables for room rent role gate feature (required roles AND any-of roles)
    room_rent_required_roles = Table('room_rent_required_roles')
    room_rent_anyof_roles = Table('room_rent_anyof_roles')
    # --- END AI-MODIFIED ---

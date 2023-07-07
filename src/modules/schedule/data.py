from data import Registry, RowModel, Table
from data.columns import Integer, Timestamp, String, Bool
from utils.data import MULTIVALUE_IN


class ScheduleData(Registry):
    class ScheduleSlot(RowModel):
        """
        Schema
        ------
        """
        _tablename_ = 'schedule_slots'

        slotid = Integer(primary=True)
        created_at = Timestamp()

        @classmethod
        async def fetch_multiple(cls, *slotids, create=True):
            """
            Fetch multiple rows, applying cache where possible.
            """
            results = {}
            to_fetch = set()
            for slotid in slotids:
                row = cls._cache_.get((slotid,), None)
                if row is None or row.data is None:
                    to_fetch.add(slotid)
                else:
                    results[slotid] = row

            if to_fetch:
                rows = await cls.fetch_where(slotid=list(to_fetch))
                for row in rows:
                    results[row.slotid] = row
                    to_fetch.remove(row.slotid)
            if to_fetch and create:
                rows = await cls.table.insert_many(
                    ('slotid',),
                    *((slotid,) for slotid in to_fetch)
                ).with_adapter(cls._make_rows)
                for row in rows:
                    results[row.slotid] = row
            return results

    class ScheduleSessionMember(RowModel):
        """
        Schema
        ------
        """
        _tablename_ = 'schedule_session_members'

        guildid = Integer(primary=True)
        userid = Integer(primary=True)
        slotid = Integer(primary=True)
        booked_at = Timestamp()
        attended = Bool()
        clock = Integer()
        book_transactionid = Integer()
        reward_transactionid = Integer()

    class ScheduleSession(RowModel):
        """
        Schema
        ------
        """
        _tablename_ = 'schedule_sessions'

        guildid = Integer(primary=True)
        slotid = Integer(primary=True)
        opened_at = Timestamp()
        closed_at = Timestamp()
        messageid = Integer()
        created_at = Timestamp()

        @classmethod
        async def fetch_multiple(cls, *keys, create=True):
            """
            Fetch multiple rows, applying cache where possible.
            """
            # TODO: Factor this into a general multikey fetch many
            results = {}
            to_fetch = set()
            for key in keys:
                row = cls._cache_.get(key, None)
                if row is None or row.data is None:
                    to_fetch.add(key)
                else:
                    results[key] = row

            if to_fetch:
                condition = MULTIVALUE_IN(cls._key_, *to_fetch)
                rows = await cls.fetch_where(condition)
                for row in rows:
                    results[row._rowid_] = row
                    to_fetch.remove(row._rowid_)
            if to_fetch and create:
                rows = await cls.table.insert_many(
                    cls._key_,
                    *to_fetch
                ).with_adapter(cls._make_rows)
                for row in rows:
                    results[row._rowid_] = row
            return results

    class ScheduleGuild(RowModel):
        """
        Schema
        ------
        """
        _tablename_ = 'schedule_guild_config'
        _cache_ = {}

        guildid = Integer(primary=True)

        schedule_cost = Integer()
        reward = Integer()
        bonus_reward = Integer()
        min_attendance = Integer()
        lobby_channel = Integer()
        room_channel = Integer()
        blacklist_after = Integer()
        blacklist_role = Integer()

        @classmethod
        async def fetch_multiple(cls, *guildids, create=True):
            """
            Fetch multiple rows, applying cache where possible.
            """
            results = {}
            to_fetch = set()
            for guildid in guildids:
                row = cls._cache_.get((guildid,), None)
                if row is None or row.data is None:
                    to_fetch.add(guildid)
                else:
                    results[guildid] = row

            if to_fetch:
                rows = await cls.fetch_where(guildid=list(to_fetch))
                for row in rows:
                    results[row.guildid] = row
                    to_fetch.remove(row.guildid)
            if to_fetch and create:
                rows = await cls.table.insert_many(
                    ('guildid',),
                    *((guildid,) for guildid in to_fetch)
                ).with_adapter(cls._make_rows)
                for row in rows:
                    results[row.guildid] = row
            return results

    """
    Schema
    ------
    """
    schedule_channels = Table('schedule_channels')

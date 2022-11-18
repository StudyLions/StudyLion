from cachetools import TTLCache

from data import Table, Registry, Column, RowModel
from data.columns import Integer, String, Bool, Timestamp


class CoreData(Registry, name="core"):
    class AppConfig(RowModel):
        """
        Schema
        ------
        CREATE TABLE app_config(
            appname TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        _tablename_ = 'app_config'

        appname = String(primary=True)
        created_at = Timestamp()

    class BotConfig(RowModel):
        """
        Schema
        ------
        CREATE TABLE bot_config(
            appname TEXT PRIMARY KEY REFERENCES app_config(appname) ON DELETE CASCADE,
            default_skin TEXT
        );
        """
        _tablename_ = 'bot_config'

        appname = String(primary=True)
        default_skin = String()

    class Shard(RowModel):
        """
        Schema
        ------
        CREATE TABLE shard_data(
            shardname TEXT PRIMARY KEY,
            appname TEXT REFERENCES bot_config(appname) ON DELETE CASCADE,
            shard_id INTEGER NOT NULL,
            shard_count INTEGER NOT NULL,
            last_login TIMESTAMPTZ,
            guild_count INTEGER
        );
        """
        _tablename_ = 'shard_data'

        shardname = String(primary=True)
        appname = String()
        shard_id = Integer()
        shard_count = Integer()
        last_login = Timestamp()
        guild_count = Integer()

    class User(RowModel):
        """User model, representing configuration data for a single user."""

        _tablename_ = "user_config"
        _cache_: TTLCache[tuple[int], 'User'] = TTLCache(5000, ttl=60*5)

        userid = Integer(primary=True)
        timezone = Column()
        topgg_vote_reminder = Column()
        avatar_hash = String()
        gems = Integer()

    class Guild(RowModel):
        """Guild model, representing configuration data for a single guild."""

        _tablename_ = "guild_config"
        _cache_: TTLCache[tuple[int], 'Guild'] = TTLCache(2500, ttl=60*5)

        guildid = Integer(primary=True)

        admin_role = Integer()
        mod_role = Integer()
        event_log_channel = Integer()
        mod_log_channel = Integer()
        alert_channel = Integer()

        studyban_role = Integer()
        max_study_bans = Integer()

        min_workout_length = Integer()
        workout_reward = Integer()

        max_tasks = Integer()
        task_reward = Integer()
        task_reward_limit = Integer()

        study_hourly_reward = Integer()
        study_hourly_live_bonus = Integer()
        daily_study_cap = Integer()

        renting_price = Integer()
        renting_category = Integer()
        renting_cap = Integer()
        renting_role = Integer()
        renting_sync_perms = Bool()

        accountability_category = Integer()
        accountability_lobby = Integer()
        accountability_bonus = Integer()
        accountability_reward = Integer()
        accountability_price = Integer()

        video_studyban = Bool()
        video_grace_period = Integer()

        greeting_channel = Integer()
        greeting_message = String()
        returning_message = String()

        starting_funds = Integer()
        persist_roles = Bool()

        pomodoro_channel = Integer()

        name = String()

    unranked_rows = Table('unranked_rows')

    donator_roles = Table('donator_roles')

    class Member(RowModel):
        """Member model, representing configuration data for a single member."""

        _tablename_ = 'members'
        _cache_: TTLCache[tuple[int, int], 'Member'] = TTLCache(5000, ttl=60*5)

        guildid = Integer(primary=True)
        userid = Integer(primary=True)

        tracked_time = Integer()
        coins = Integer()

        workout_count = Integer()
        last_workout_start = Column()
        revision_mute_count = Integer()
        last_study_badgeid = Integer()
        video_warned = Bool()
        display_name = String()

        _timestamp = Column()

        @classmethod
        async def add_pending(cls, pending: tuple[int, int, int]) -> list['Member']:
            """
            Safely add pending coins to a list of members.

            Arguments
            ---------
            pending:
                List of tuples of the form `(guildid, userid, pending_coins)`.
            """
            # TODO: Replace with copy syntax/query?
            ...

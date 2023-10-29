from enum import Enum
from itertools import chain
from psycopg import sql
from cachetools import TTLCache
import discord

from meta import conf
from meta.logger import log_wrap
from data import Table, Registry, Column, RowModel, RegisterEnum
from data.models import WeakCache
from data.columns import Integer, String, Bool, Timestamp


class RankType(Enum):
    """
    Schema
    ------
    CREATE TYPE RankType AS ENUM(
        'XP',
        'VOICE',
        'MESSAGE'
    );
    """
    XP = 'XP',
    VOICE = 'VOICE',
    MESSAGE = 'MESSAGE',


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
            sponsor_prompt TEXT,
            sponsor_message TEXT,
            default_skin TEXT
        );
        """
        _tablename_ = 'bot_config'

        appname = String(primary=True)
        default_skin = String()
        sponsor_prompt = String()
        sponsor_message = String()

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
        """
        User model, representing configuration data for a single user.

        Schema
        ------
        CREATE TABLE user_config(
            userid BIGINT PRIMARY KEY,
            timezone TEXT,
            show_global_stats BOOLEAN,
            topgg_vote_reminder BOOLEAN,
            avatar_hash TEXT,
            name TEXT,
            API_timestamp BIGINT,
            gems INTEGER DEFAULT 0,
            first_seen TIMESTAMPTZ DEFAULT now(),
            last_seen TIMESTAMPTZ,
            locale TEXT,
            locale_hint TEXT
        );
        """

        _tablename_ = "user_config"
        _cache_: WeakCache[tuple[int], 'CoreData.User'] = WeakCache(TTLCache(1000, ttl=60*5))

        userid = Integer(primary=True)
        timezone = String()
        show_global_stats = Bool()
        topgg_vote_reminder = Bool()
        avatar_hash = String()
        name = String()
        API_timestamp = Integer()
        gems = Integer()
        first_seen = Timestamp()
        last_seen = Timestamp()
        locale = String()
        locale_hint = String()

    class Guild(RowModel):
        """
        Guild model, representing configuration data for a single guild.

        Schema
        ------
        CREATE TABLE guild_config(
            guildid BIGINT PRIMARY KEY,
            admin_role BIGINT,
            mod_role BIGINT,
            event_log_channel BIGINT,
            mod_log_channel BIGINT,
            alert_channel BIGINT,
            studyban_role BIGINT,
            min_workout_length INTEGER,
            workout_reward INTEGER,
            max_tasks INTEGER,
            task_reward INTEGER,
            task_reward_limit INTEGER,
            study_hourly_reward INTEGER,
            study_hourly_live_bonus INTEGER,
            renting_price INTEGER,
            renting_category BIGINT,
            renting_cap INTEGER,
            renting_role BIGINT,
            renting_sync_perms BOOLEAN,
            accountability_category BIGINT,
            accountability_lobby BIGINT,
            accountability_bonus INTEGER,
            accountability_reward INTEGER,
            accountability_price INTEGER,
            video_studyban BOOLEAN,
            video_grace_period INTEGER,
            greeting_channel BIGINT,
            greeting_message TEXT,
            returning_message TEXT,
            starting_funds INTEGER,
            persist_roles BOOLEAN,
            daily_study_cap INTEGER,
            pomodoro_channel BIGINT,
            name TEXT,
            first_joined_at TIMESTAMPTZ DEFAULT now(),
            left_at TIMESTAMPTZ,
            locale TEXT,
            timezone TEXT,
            force_locale BOOLEAN,
            season_start TIMESTAMPTZ,
            xp_per_period INTEGER,
            xp_per_centiword INTEGER
        );

        """

        _tablename_ = "guild_config"
        _cache_: WeakCache[tuple[int], 'CoreData.Guild'] = WeakCache(TTLCache(1000, ttl=60*5))

        guildid = Integer(primary=True)

        admin_role = Integer()
        mod_role = Integer()
        event_log_channel = Integer()
        mod_log_channel = Integer()
        alert_channel = Integer()

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
        renting_visible = Bool()

        accountability_category = Integer()
        accountability_lobby = Integer()
        accountability_bonus = Integer()
        accountability_reward = Integer()
        accountability_price = Integer()

        video_studyban = Bool()
        video_grace_period = Integer()

        studyban_role = Integer()

        greeting_channel = Integer()
        greeting_message = String()
        returning_message = String()

        starting_funds = Integer()
        persist_roles = Bool()

        pomodoro_channel = Integer()

        name = String()

        first_joined_at = Timestamp()
        left_at = Timestamp()

        timezone = String()

        locale = String()
        force_locale = Bool()

        season_start = Timestamp()
        rank_type: Column[RankType] = Column()
        rank_channel = Integer()
        dm_ranks = Bool()

        xp_per_period = Integer()
        xp_per_centiword = Integer()
        coins_per_centixp = Integer()

        allow_transfers = Bool()

    donator_roles = Table('donator_roles')

    member_ranks = Table('member_ranks')

    class Member(RowModel):
        """
        Member model, representing configuration data for a single member.

        Schema
        ------
        CREATE TABLE members(
            guildid BIGINT,
            userid BIGINT,
            tracked_time INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            workout_count INTEGER DEFAULT 0,
            revision_mute_count INTEGER DEFAULT 0,
            last_workout_start TIMESTAMP,
            last_study_badgeid INTEGER REFERENCES study_badges ON DELETE SET NULL,
            video_warned BOOLEAN DEFAULT FALSE,
            display_name TEXT,
            first_joined TIMESTAMPTZ DEFAULT now(),
            last_left TIMESTAMPTZ,
            _timestamp TIMESTAMP DEFAULT (now() at time zone 'utc'),
            PRIMARY KEY(guildid, userid)
        );
        CREATE INDEX member_timestamps ON members (_timestamp);
        """
        _tablename_ = 'members'
        _cache_: WeakCache[tuple[int, int], 'CoreData.Member'] = WeakCache(TTLCache(5000, ttl=60*5))

        guildid = Integer(primary=True)
        userid = Integer(primary=True)

        tracked_time = Integer()
        coins = Integer()

        workout_count = Integer()
        revision_mute_count = Integer()
        last_workout_start = Timestamp()
        last_study_badgeid = Integer()
        video_warned = Bool()
        display_name = String()

        first_joined = Timestamp()
        last_left = Timestamp()
        _timestamp = Timestamp()

        @classmethod
        @log_wrap(action="Add Pending Coins")
        async def add_pending(cls, pending: list[tuple[int, int, int]]) -> list['CoreData.Member']:
            """
            Safely add pending coins to a list of members.

            Arguments
            ---------
            pending:
                List of tuples of the form `(guildid, userid, pending_coins)`.
            """
            query = sql.SQL("""
                UPDATE members
                SET
                    coins = LEAST(coins + t.coin_diff, 2147483647)
                FROM
                    (VALUES {})
                AS
                    t (guildid, userid, coin_diff)
                WHERE
                    members.guildid = t.guildid
                AND
                    members.userid = t.userid
                RETURNING *
            """).format(
                sql.SQL(', ').join(
                    sql.SQL("({}, {}, {})").format(sql.Placeholder(), sql.Placeholder(), sql.Placeholder())
                    for _ in pending
                )
            )
            # TODO: Replace with copy syntax/query?
            async with cls.table.connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        tuple(chain(*pending))
                    )
                    rows = await cursor.fetchall()
                    return cls._make_rows(*rows)

        @classmethod
        @log_wrap(action='get_member_rank')
        async def get_member_rank(cls, guildid, userid, untracked):
            """
            Get the time and coin ranking for the given member, ignoring the provided untracked members.
            """
            async with cls.table.connector.connection() as conn:
                async with conn.cursor() as curs:
                    await curs.execute(
                        """
                        SELECT
                        time_rank, coin_rank
                        FROM (
                        SELECT
                            userid,
                            row_number() OVER (ORDER BY total_tracked_time DESC, userid ASC) AS time_rank,
                            row_number() OVER (ORDER BY total_coins DESC, userid ASC) AS coin_rank
                        FROM members_totals
                        WHERE
                            guildid=%s AND userid NOT IN %s
                        ) AS guild_ranks WHERE userid=%s
                        """,
                        (guildid, tuple(untracked), userid)
                    )
                    return (await curs.fetchone()) or (None, None)

    class LionHook(RowModel):
        """
        Schema
        ------
        CREATE TABLE channel_webhooks(
          channelid BIGINT NOT NULL PRIMARY KEY,
          webhookid BIGINT NOT NULL,
          token TEXT NOT NULL
        );
        """
        _tablename_ = 'channel_webhooks'
        _cache_ = {}

        channelid = Integer(primary=True)
        webhookid = Integer()
        token = String()

        def as_webhook(self, **kwargs):
            webhook = discord.Webhook.partial(self.webhookid, self.token, **kwargs)
            webhook.proxy = conf.bot.get('proxy', None)
            return webhook

    workouts = Table('workout_sessions')
    topgg = Table('topgg')

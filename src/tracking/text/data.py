from itertools import chain
from psycopg import sql

from meta.logger import log_wrap
from data import RowModel, Registry, Table
from data.columns import Integer, String, Timestamp, Bool

from core.data import CoreData


class TextTrackerData(Registry):
    class BotConfigText(RowModel):
        """
        App configuration for text tracker XP.

        Schema
        ------
        CREATE TABLE bot_config_experience_rates(
          appname TEXT PRIMARY KEY REFERENCES bot_config(appname) ON DELETE CASCADE,
          period_length INTEGER,
          xp_per_period INTEGER,
          xp_per_centiword INTEGER
        );

        """
        _tablename_ = 'bot_config_experience_rates'
        _cache_ = {}

        appname = String(primary=True)
        period_length = Integer()
        xp_per_period = Integer()
        xp_per_centiword = Integer()

    class TextSessions(RowModel):
        """
        Model describing completed text chat sessions.

        Schema
        ------
        CREATE TABLE text_sessions(
          sessionid BIGSERIAL PRIMARY KEY,
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          start_time TIMESTAMPTZ NOT NULL,
          duration INTEGER NOT NULL,
          messages INTEGER NOT NULL,
          words INTEGER NOT NULL,
          periods INTEGER NOT NULL,
          user_expid BIGINT REFERENCES user_experience,
          member_expid BIGINT REFERENCES member_experience,
          end_time TIMESTAMP GENERATED ALWAYS AS
            ((start_time AT TIME ZONE 'UTC') + duration * interval '1 second')
          STORED,
          FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
        );
        CREATE INDEX text_sessions_members ON text_sessions (guildid, userid);
        CREATE INDEX text_sessions_start_time ON text_sessions (start_time);
        CREATE INDEX text_sessions_end_time ON text_sessions (end_time);
        """
        _tablename_ = 'text_sessions'

        sessionid = Integer(primary=True)
        guildid = Integer()
        userid = Integer()
        start_time = Timestamp()
        duration = Integer()
        messages = Integer()
        words = Integer()
        periods = Integer()
        end_time = Timestamp()
        user_expid = Integer()
        member_expid = Integer()

        @classmethod
        @log_wrap(action='end_text_sessions')
        async def end_sessions(cls, connector, *session_data):
            query = sql.SQL("""
                WITH
                    data (
                        _guildid, _userid,
                        _start_time, _duration,
                        _messages, _words, _periods,
                        _memberxp, _userxp,
                        _coins
                    )
                    AS
                    (VALUES {})
                , transactions AS (
                    INSERT INTO coin_transactions (
                        guildid, actorid,
                        from_account, to_account,
                        amount, bonus, transactiontype
                    ) SELECT
                            data._guildid, 0,
                            NULL, data._userid,
                            LEAST(SUM(_coins :: BIGINT), 2147483647), 0, 'TEXT_SESSION'
                        FROM data
                        WHERE data._coins > 0
                        GROUP BY (data._guildid, data._userid)
                    RETURNING guildid, to_account AS userid, amount, transactionid
                )
                , member AS (
                    UPDATE members
                    SET coins = LEAST(coins :: BIGINT + data._coins :: BIGINT, 2147483647)
                    FROM data
                    WHERE members.userid = data._userid AND members.guildid = data._guildid
                )
                , member_exp AS (
                    INSERT INTO member_experience (
                        guildid, userid,
                        earned_at,
                        amount, exp_type,
                        transactionid
                    ) SELECT
                        data._guildid, data._userid,
                        MAX(data._start_time),
                        SUM(data._memberxp), 'TEXT_XP',
                        transactions.transactionid
                    FROM data
                    LEFT JOIN transactions ON
                        data._userid = transactions.userid AND
                        data._guildid = transactions.guildid
                    WHERE data._memberxp > 0
                    GROUP BY (data._guildid, data._userid, transactions.transactionid)
                    RETURNING guildid, userid, member_expid
                )
                , user_exp AS(
                    INSERT INTO user_experience (
                        userid,
                        earned_at,
                        amount, exp_type
                    ) SELECT
                        data._userid,
                        MAX(data._start_time),
                        SUM(data._userxp), 'TEXT_XP'
                    FROM data
                    WHERE data._userxp > 0
                    GROUP BY (data._userid)
                    RETURNING userid, user_expid
                )
                INSERT INTO text_sessions(
                    guildid, userid,
                    start_time, duration,
                    messages, words, periods,
                    user_expid, member_expid
                ) SELECT
                    data._guildid, data._userid,
                    data._start_time, data._duration,
                    data._messages, data._words, data._periods,
                    user_exp.user_expid, member_exp.member_expid
                FROM data
                LEFT JOIN member_exp ON data._userid = member_exp.userid AND data._guildid = member_exp.guildid
                LEFT JOIN user_exp ON data._userid = user_exp.userid
            """).format(
                sql.SQL(', ').join(
                    sql.SQL("({}, {}, {}, {}, {}, {}, {}, {}, {}, {})").format(
                        sql.Placeholder(), sql.Placeholder(),
                        sql.Placeholder(), sql.Placeholder(),
                        sql.Placeholder(), sql.Placeholder(), sql.Placeholder(),
                        sql.Placeholder(), sql.Placeholder(),
                        sql.Placeholder(),
                    )
                    for _ in session_data
                )
            )
            # TODO: Consider asking for a *new* temporary connection here, to avoid blocking
            # Or ask for a connection from the connection pool
            # Transaction may take some time due to index updates
            # Alternatively maybe use the "do not expect response mode"
            async with connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        tuple(chain(*session_data))
                    )
            return

        @classmethod
        @log_wrap(action='user_messages_between')
        async def user_messages_between(cls, userid: int, *points):
            """
            Compute messages written between the given points.
            """
            blocks = zip(points, points[1:])
            query = sql.SQL(
                """
                SELECT
                    (
                        SELECT
                            SUM(messages)
                        FROM text_sessions s
                        WHERE
                            s.userid = %s
                            AND s.start_time >= periods._start
                            AND s.start_time < periods._end
                    ) AS period_m
                FROM
                    (VALUES {})
                    AS
                    periods (_start, _end)
                ORDER BY periods._start
                """
            ).format(
                sql.SQL(', ').join(
                    sql.SQL("({}, {})").format(sql.Placeholder(), sql.Placeholder()) for _ in points[1:]
                )
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        tuple(chain((userid,), *blocks))
                    )
                    return [r['period_m'] or 0 for r in await cursor.fetchall()]

        @classmethod
        @log_wrap(action='member_messages_between')
        async def member_messages_between(cls, guildid: int, userid: int, *points):
            """
            Compute messages written between the given points.
            """
            blocks = zip(points, points[1:])
            query = sql.SQL(
                """
                SELECT
                    (
                        SELECT
                            SUM(messages)
                        FROM text_sessions s
                        WHERE
                            s.userid = %s
                            AND s.guildid = %s
                            AND s.start_time >= periods._start
                            AND s.start_time < periods._end
                    ) AS period_m
                FROM
                    (VALUES {})
                    AS
                    periods (_start, _end)
                ORDER BY periods._start
                """
            ).format(
                sql.SQL(', ').join(
                    sql.SQL("({}, {})").format(sql.Placeholder(), sql.Placeholder()) for _ in points[1:]
                )
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        tuple(chain((userid, guildid), *blocks))
                    )
                    return [r['period_m'] or 0 for r in await cursor.fetchall()]

        @classmethod
        @log_wrap(action='member_messages_since')
        async def member_messages_since(cls, guildid: int, userid: int, *points):
            """
            Compute messages written between the given points.
            """
            query = sql.SQL(
                """
                SELECT
                    (
                        SELECT
                            SUM(messages)
                        FROM text_sessions s
                        WHERE
                            s.userid = %s
                            AND s.guildid = %s
                            AND s.start_time >= t._start
                    ) AS messages
                FROM
                    (VALUES {})
                    AS
                t (_start)
                ORDER BY t._start
                """
            ).format(
                sql.SQL(', ').join(
                    sql.SQL("({})").format(sql.Placeholder()) for _ in points
                )
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        tuple(chain((userid, guildid), points))
                    )
                    return [r['messages'] or 0 for r in await cursor.fetchall()]

        @classmethod
        @log_wrap(action='user_messages_since')
        async def user_messages_since(cls, userid: int, *points):
            """
            Compute messages written between the given points.
            """
            query = sql.SQL(
                """
                SELECT
                    (
                        SELECT
                            SUM(messages)
                        FROM text_sessions s
                        WHERE
                            s.userid = %s
                            AND s.start_time >= t._start
                    ) AS messages
                FROM
                    (VALUES {})
                    AS
                t (_start)
                ORDER BY t._start
                """
            ).format(
                sql.SQL(', ').join(
                    sql.SQL("({})").format(sql.Placeholder()) for _ in points
                )
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        tuple(chain((userid,), points))
                    )
                    return [r['messages'] or 0 for r in await cursor.fetchall()]
        
        @classmethod
        @log_wrap(action='msgs_leaderboard_all')
        async def leaderboard_since(cls, guildid: int, since):
            """
            Return the message count totals for the given guild since the given time.
            """
            query = sql.SQL(
                """
                SELECT userid, sum(messages) as user_total
                FROM text_sessions
                WHERE guildid = %s AND start_time >= %s
                GROUP BY userid
                ORDER BY user_total DESC
                """
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (guildid, since))
                    leaderboard = [
                        (row['userid'], int(row['user_total']))
                        for row in await cursor.fetchall()
                    ]
            return leaderboard

        @classmethod
        @log_wrap(action='msgs_leaderboard_all')
        async def leaderboard_all(cls, guildid: int):
            """
            Return the all-time message count totals for the given guild.
            """
            query = sql.SQL(
                """
                SELECT userid, sum(messages) as user_total
                FROM text_sessions
                WHERE guildid = %s
                GROUP BY userid
                ORDER BY user_total DESC
                """
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (guildid,))
                    leaderboard = [
                        (row['userid'], int(row['user_total']))
                        for row in await cursor.fetchall()
                    ]
            return leaderboard

    untracked_channels = Table('untracked_text_channels')

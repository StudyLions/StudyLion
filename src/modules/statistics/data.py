from typing import Optional, Iterable
import datetime as dt
from enum import Enum
from itertools import chain
from psycopg import sql

from meta.logger import log_wrap
from data import RowModel, Registry, Table, RegisterEnum
from data.columns import Integer, String, Timestamp, Bool, Column

from utils.lib import utc_now


class StatisticType(Enum):
    """
    Schema
    ------
    CREATE TYPE StatisticType AS ENUM(
        'VOICE',
        'TEXT',
        'ANKI'
    )
    """
    VOICE = ('VOICE',)
    TEXT = ('TEXT',)
    ANKI = ('ANKI',)


class ExpType(Enum):
    """
    Schema
    ------
    CREATE TYPE ExperienceType AS ENUM(
      'VOICE_XP',
      'TEXT_XP',
      'QUEST_XP',  -- Custom guild quests
      'ACHIEVEMENT_XP', -- Individual tracked achievements
      'BONUS_XP' -- Manually adjusted XP
    );
    """
    VOICE_XP = 'VOICE_XP',
    TEXT_XP = 'TEXT_XP',
    QUEST_XP = 'QUEST_XP',
    ACHIEVEMENT_XP = 'ACHIEVEMENT_XP'
    BONUS_XP = 'BONUS_XP'


class StatsData(Registry):
    StatisticType = RegisterEnum(StatisticType, name='StatisticType')
    ExpType = RegisterEnum(ExpType, name='ExperienceType')

    class VoiceSessionStats(RowModel):
        """
        View containing voice session statistics.

        Schema
        ------
        CREATE VIEW voice_sessions_combined AS
          SELECT
            userid,
            guildid,
            start_time,
            duration,
            (timezone('UTC', start_time) + duration * interval '1 second') AS end_time
          FROM session_history
          UNION ALL
          SELECT
            userid,
            guildid,
            start_time,
            EXTRACT(EPOCH FROM (NOW() - start_time)) AS duration,
            NOW() AS end_time
          FROM current_sessions;
        """
        _tablename_ = "voice_sessions_combined"

        userid = Integer()
        guildid = Integer()
        start_time = Timestamp()
        duration = Integer()
        end_time = Timestamp()

        @classmethod
        @log_wrap(action='tracked_time_between')
        async def tracked_time_between(cls, *points: tuple[int, int, dt.datetime, dt.datetime]):
            query = sql.SQL(
                """
                SELECT
                    t._guildid AS guildid,
                    t._userid AS userid,
                    t._start AS start_time,
                    t._end AS end_time,
                    study_time_between(t._guildid, t._userid, t._start, t._end) AS stime
                FROM
                    (VALUES {})
                AS
                    t (_guildid, _userid, _start, _end)
                """
            ).format(
                sql.SQL(', ').join(
                    sql.SQL("({}, {}, {}, {})").format(
                        sql.Placeholder(), sql.Placeholder(),
                        sql.Placeholder(), sql.Placeholder()
                    )
                    for _ in points
                )
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        chain(*points)
                    )
                    return cursor.fetchall()

        @classmethod
        @log_wrap(action='study_time_between')
        async def study_time_between(cls, guildid: int, userid: int, _start, _end) -> int:
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "SELECT study_time_between(%s, %s, %s, %s)",
                        (guildid, userid, _start, _end)
                    )
                    return (await cursor.fetchone())[0] or 0

        @classmethod
        @log_wrap(action='study_times_between')
        async def study_times_between(cls, guildid: Optional[int], userid: int, *points) -> list[int]:
            if len(points) < 2:
                raise ValueError('Not enough block points given!')

            blocks = zip(points, points[1:])
            query = sql.SQL(
                """
                SELECT
                    study_time_between(%s, %s, t._start, t._end) AS stime
                FROM
                (VALUES {})
                AS
                t (_start, _end)
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
                        tuple(chain((guildid, userid), *blocks))
                    )
                    return [r['stime'] or 0 for r in await cursor.fetchall()]

        @classmethod
        @log_wrap(action='study_time_since')
        async def study_time_since(cls, guildid: int, userid: int, _start) -> int:
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "SELECT study_time_since(%s, %s, %s)",
                        (guildid, userid, _start)
                    )
                    return (await cursor.fetchone())[0] or 0

        @classmethod
        @log_wrap(action='study_times_since')
        async def study_times_since(cls, guildid: Optional[int], userid: int, *starts) -> list[int]:
            if len(starts) < 1:
                raise ValueError('No starting points given!')

            query = sql.SQL(
                """
                SELECT
                study_time_since(%s, %s, t._start) AS stime
                FROM
                (VALUES {})
                AS
                t (_start)
                """
            ).format(
                sql.SQL(', ').join(
                    sql.SQL("({})").format(sql.Placeholder()) for _ in starts
                )
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        tuple(chain((guildid, userid), starts))
                    )
                    return [r['stime'] or 0 for r in await cursor.fetchall()]

        @classmethod
        @log_wrap(action='leaderboard_since')
        async def leaderboard_since(cls, guildid: int, since):
            """
            Return the voice totals since the given time for each member in the guild.
            """
            # Retrieve sum of all sessions (incl. ongoing) ending after given time
            first_query = sql.SQL(
                """
                SELECT
                    userid,
                    sum(duration) as total_duration
                FROM voice_sessions_combined
                WHERE
                    guildid = %s
                    AND
                    end_time > %s
                GROUP BY userid
                ORDER BY total_duration DESC
                """
            )
            first_query_args = (guildid, since)

            # Retrieve how much we "overshoot", from sessions which intersect the given time
            second_query = sql.SQL(
                """
                SELECT
                    SUM(EXTRACT(EPOCH FROM (%s - start_time))) AS diff,
                    userid
                FROM voice_sessions_combined
                WHERE
                    guildid = %s
                    AND
                    start_time < %s
                    AND
                    end_time > %s
                GROUP BY userid
                """
            )
            second_query_args = (since, guildid, since, since)

            async with cls._connector.connection() as conn:
                cls._connector.conn = conn
                async with conn.transaction():
                    async with conn.cursor() as cursor:
                        await cursor.execute(second_query, second_query_args)
                        overshoot_rows = await cursor.fetchall()
                        overshoot = {row['userid']: int(row['diff']) for row in overshoot_rows}

                    async with conn.cursor() as cursor:
                        await cursor.execute(first_query, first_query_args)
                        leaderboard = [
                            (row['userid'], int(row['total_duration'] - overshoot.get(row['userid'], 0)))
                            for row in await cursor.fetchall()
                        ]
                    leaderboard.sort(key=lambda t: t[1], reverse=True)
            return leaderboard

        @classmethod
        @log_wrap(action='leaderboard_all')
        async def leaderboard_all(cls, guildid: int):
            """
            Return the all-time voice totals for the given guild.
            """
            query = sql.SQL(
                """
                SELECT userid, sum(duration) as total_duration
                FROM voice_sessions_combined
                WHERE guildid = %s
                GROUP BY userid
                ORDER BY total_duration DESC
                """
            )

            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (guildid, ))
                    leaderboard = [
                        (row['userid'], int(row['total_duration']))
                        for row in await cursor.fetchall()
                    ]
            return leaderboard

    class MemberExp(RowModel):
        """
        Model representing a member experience update.

        Schema
        ------
        CREATE TABLE member_experience(
          member_expid BIGSERIAL PRIMARY KEY,
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          earned_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'UTC'),
          amount INTEGER NOT NULL,
          exp_type ExperienceType NOT NULL,
          transactionid INTEGER REFERENCES coin_transactions ON DELETE SET NULL,
          FOREIGN KEY (guildid, userid) REFERENCES members ON DELETE CASCADE
        );
        CREATE INDEX member_experience_members ON member_experience (guildid, userid, earned_at);
        CREATE INDEX member_experience_guilds ON member_experience (guildid, earned_at);
        """
        _tablename_ = 'member_experience'

        member_expid = Integer(primary=True)
        guildid = Integer()
        userid = Integer()
        earned_at = Timestamp()
        amount = Integer()
        exp_type: Column[ExpType] = Column()
        transactionid = Integer()

        @classmethod
        @log_wrap(action='xp_since')
        async def xp_since(cls, guildid: int, userid: int, *starts):
            query = sql.SQL(
                """
                SELECT
                    (
                        SELECT
                            SUM(amount)
                        FROM member_experience s
                        WHERE
                            s.guildid = %s
                            AND s.userid = %s
                            AND s.earned_at >= t._start
                    ) AS exp
                FROM
                    (VALUES ({}))
                    AS
                    t (_start)
                ORDER BY t._start
                """
            ).format(
                sql.SQL('), (').join(
                    sql.Placeholder() for _ in starts
                )
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        tuple(chain((guildid, userid), starts))
                    )
                    return [r['exp'] or 0 for r in await cursor.fetchall()]

        @classmethod
        @log_wrap(action='xp_between')
        async def xp_between(cls, guildid: int, userid: int, *points):
            blocks = zip(points, points[1:])
            query = sql.SQL(
                """
                SELECT
                    (
                        SELECT
                            SUM(amount)
                        FROM member_experience s
                        WHERE
                            s.guildid = %s
                            AND s.userid = %s
                            AND s.earned_at >= periods._start
                            AND s.earned_at < periods._end
                    ) AS period_xp
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
                        tuple(chain((guildid, userid), *blocks))
                    )
                    return [r['period_xp'] or 0 for r in await cursor.fetchall()]

        @classmethod
        @log_wrap(action='leaderboard_since')
        async def leaderboard_since(cls, guildid: int, since):
            """
            Return the XP totals for the given guild since the given time.
            """
            query = sql.SQL(
                """
                SELECT userid, sum(amount) AS total_xp
                FROM member_experience
                WHERE guildid = %s AND earned_at >= %s
                GROUP BY userid
                ORDER BY total_xp DESC
                """
            )

            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (guildid, since))
                    leaderboard = [
                        (row['userid'], int(row['total_xp']))
                        for row in await cursor.fetchall()
                    ]
            return leaderboard

        @classmethod
        @log_wrap(action='leaderboard_all')
        async def leaderboard_all(cls, guildid: int):
            """
            Return the all-time XP totals for the given guild.
            """
            query = sql.SQL(
                """
                SELECT userid, sum(amount) AS total_xp
                FROM member_experience
                WHERE guildid = %s
                GROUP BY userid
                ORDER BY total_xp DESC
                """
            )

            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (guildid, ))
                    leaderboard = [
                        (row['userid'], int(row['total_xp']))
                        for row in await cursor.fetchall()
                    ]
            return leaderboard

    class UserExp(RowModel):
        """
        Model representing a user experience update.

        Schema
        ------
        CREATE TABLE user_experience(
          user_expid BIGSERIAL PRIMARY KEY,
          userid BIGINT NOT NULL,
          earned_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'UTC'),
          amount INTEGER NOT NULL,
          exp_type ExperienceType NOT NULL,
          FOREIGN KEY (userid) REFERENCES user_config ON DELETE CASCADE
        );
        CREATE INDEX user_experience_users ON user_experience (userid, earned_at);
        """
        _tablename_ = 'user_experience'

        user_expid = Integer(primary=True)
        userid = Integer()
        earned_at = Timestamp()
        amount = Integer()
        exp_type: Column[ExpType] = Column()

        @classmethod
        @log_wrap(action='user_xp_since')
        async def xp_since(cls, userid: int, *starts):
            query = sql.SQL(
                """
                SELECT
                    (
                        SELECT
                            SUM(amount)
                        FROM user_experience s
                        WHERE
                            s.userid = %s
                            AND s.earned_at >= t._start
                    ) AS exp
                FROM
                    (VALUES ({}))
                    AS
                    t (_start)
                ORDER BY t._start
                """
            ).format(
                sql.SQL('), (').join(
                    sql.Placeholder() for _ in starts
                )
            )
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        query,
                        tuple(chain((userid,), starts))
                    )
                    return [r['exp'] or 0 for r in await cursor.fetchall()]

        @classmethod
        @log_wrap(action='user_xp_since')
        async def xp_between(cls, userid: int, *points):
            blocks = zip(points, points[1:])
            query = sql.SQL(
                """
                SELECT
                    (
                        SELECT
                            SUM(amount)
                        FROM user_experience s
                        WHERE
                            s.userid = %s
                            AND s.earned_at >= periods._start
                            AND s.earned_at < periods._end
                    ) AS period_xp
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
                    return [r['period_xp'] or 0 for r in await cursor.fetchall()]

    class ProfileTag(RowModel):
        """
        Schema
        ------
        CREATE TABLE member_profile_tags(
          tagid SERIAL PRIMARY KEY,
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          tag TEXT NOT NULL,
          _timestamp TIMESTAMPTZ DEFAULT now(),
          FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid)
        );
        CREATE INDEX member_profile_tags_members ON member_profile_tags (guildid, userid);
        """
        _tablename_ = 'member_profile_tags'

        tagid = Integer(primary=True)
        guildid = Integer()
        userid = Integer()
        tag = String()
        _timestamp = Timestamp()

        @classmethod
        async def fetch_tags(cls, guildid: Optional[int], userid: int):
            tags = await cls.fetch_where(guildid=guildid, userid=userid).order_by(cls.tagid)
            if not tags and guildid is not None:
                tags = await cls.fetch_where(guildid=None, userid=userid)
            return [tag.tag for tag in tags]

        @classmethod
        @log_wrap(action='set_profile_tags')
        async def set_tags(cls, guildid: Optional[int], userid: int, tags: Iterable[str]):
            async with cls._connector.connection() as conn:
                cls._connector.conn = conn
                async with conn.transaction():
                    await cls.table.delete_where(guildid=guildid, userid=userid)
                    if tags:
                        await cls.table.insert_many(
                            ('guildid', 'userid', 'tag'),
                            *((guildid, userid, tag) for tag in tags)
                        )

    class WeeklyGoals(RowModel):
        """
        Schema
        ------
        CREATE TABLE member_weekly_goals(
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          weekid INTEGER NOT NULL, -- Epoch time of the start of the UTC week
          study_goal INTEGER,
          task_goal INTEGER,
          _timestamp TIMESTAMPTZ DEFAULT now(),
          PRIMARY KEY (guildid, userid, weekid),
          FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
        );
        CREATE INDEX member_weekly_goals_members ON member_weekly_goals (guildid, userid);
        """
        _tablename_ = 'member_weekly_goals'

        guildid = Integer(primary=True)
        userid = Integer(primary=True)
        weekid = Integer(primary=True)
        study_goal = Integer()
        task_goal = Integer()
        _timestamp = Timestamp()

    class WeeklyTasks(RowModel):
        """
        Schema
        ------
        CREATE TABLE member_weekly_goal_tasks(
          taskid SERIAL PRIMARY KEY,
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          weekid INTEGER NOT NULL,
          content TEXT NOT NULL,
          completed BOOLEAN NOT NULL DEFAULT FALSE,
          _timestamp TIMESTAMPTZ DEFAULT now(),
          FOREIGN KEY (weekid, guildid, userid) REFERENCES member_weekly_goals (weekid, guildid, userid) ON DELETE CASCADE
        );
        CREATE INDEX member_weekly_goal_tasks_members_weekly ON member_weekly_goal_tasks (guildid, userid, weekid);
        """
        _tablename_ = 'member_weekly_goal_tasks'

        taskid = Integer(primary=True)
        guildid = Integer()
        userid = Integer()
        weekid = Integer()
        content = String()
        completed = Bool()
        _timestamp = Timestamp()

    class MonthlyGoals(RowModel):
        """
        Schema
        ------
        CREATE TABLE member_monthly_goals(
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          monthid INTEGER NOT NULL, -- Epoch time of the start of the UTC month
          study_goal INTEGER,
          task_goal INTEGER,
          _timestamp TIMESTAMPTZ DEFAULT now(),
          PRIMARY KEY (guildid, userid, monthid),
          FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
        );
        CREATE INDEX member_monthly_goals_members ON member_monthly_goals (guildid, userid);
        """
        _tablename_ = 'member_monthly_goals'

        guildid = Integer(primary=True)
        userid = Integer(primary=True)
        monthid = Integer(primary=True)
        study_goal = Integer()
        task_goal = Integer()
        _timestamp = Timestamp()

    class MonthlyTasks(RowModel):
        """
        Schema
        ------
        CREATE TABLE member_monthly_goal_tasks(
          taskid SERIAL PRIMARY KEY,
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          monthid INTEGER NOT NULL,
          content TEXT NOT NULL,
          completed BOOLEAN NOT NULL DEFAULT FALSE,
          _timestamp TIMESTAMPTZ DEFAULT now(),
          FOREIGN KEY (monthid, guildid, userid) REFERENCES member_monthly_goals (monthid, guildid, userid) ON DELETE CASCADE
        );
        CREATE INDEX member_monthly_goal_tasks_members_monthly ON member_monthly_goal_tasks (guildid, userid, monthid);
        """
        _tablename_ = 'member_monthly_goal_tasks'

        taskid = Integer(primary=True)
        guildid = Integer()
        userid = Integer()
        monthid = Integer()
        content = String()
        completed = Bool()
        _timestamp = Timestamp()

    unranked_roles = Table('unranked_roles')
    visible_statistics = Table('visible_statistics')

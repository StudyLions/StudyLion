from typing import Optional, Iterable
from itertools import chain
from psycopg import sql

from data import RowModel, Registry, Table
from data.columns import Integer, String, Timestamp, Bool

from utils.lib import utc_now


class StatsData(Registry):
    class PastSession(RowModel):
        """
        Schema
        ------
        CREATE TABLE session_history(
          sessionid SERIAL PRIMARY KEY,
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          channelid BIGINT,
          channel_type SessionChannelType,
          rating INTEGER,
          tag TEXT,
          start_time TIMESTAMPTZ NOT NULL,
          duration INTEGER NOT NULL,
          coins_earned INTEGER NOT NULL,
          live_duration INTEGER DEFAULT 0,
          stream_duration INTEGER DEFAULT 0,
          video_duration INTEGER DEFAULT 0,
          FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
        );
        CREATE INDEX session_history_members ON session_history (guildid, userid, start_time);
        """
        _tablename_ = "session_history"

    class CurrentSession(RowModel):
        """
        Schema
        ------
        CREATE TABLE current_sessions(
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          channelid BIGINT,
          channel_type SessionChannelType,
          rating INTEGER,
          tag TEXT,
          start_time TIMESTAMPTZ DEFAULT now(),
          live_duration INTEGER DEFAULT 0,
          live_start TIMESTAMPTZ,
          stream_duration INTEGER DEFAULT 0,
          stream_start TIMESTAMPTZ,
          video_duration INTEGER DEFAULT 0,
          video_start TIMESTAMPTZ,
          hourly_coins INTEGER NOT NULL,
          hourly_live_coins INTEGER NOT NULL,
          FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX current_session_members ON current_sessions (guildid, userid);
        """
        _tablename_ = "current_sessions"

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
            (start_time + duration * interval '1 second') AS end_time
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
        async def study_time_between(cls, guildid: int, userid: int, _start, _end) -> int:
            conn = cls._connector.get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT study_time_between(%s, %s, %s, %s)",
                    (guildid, userid, _start, _end)
                )
                return (await cursor.fetchone()[0]) or 0

        @classmethod
        async def study_times_between(cls, guildid: int, userid: int, *points) -> list[int]:
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
            conn = await cls._connector.get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(
                    query,
                    tuple(chain((guildid, userid), *blocks))
                )
                return [r['stime'] or 0 for r in await cursor.fetchall()]

        @classmethod
        async def study_time_since(cls, guildid: int, userid: int, _start) -> int:
            conn = cls._connector.get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT study_time_since(%s, %s, %s)",
                    (guildid, userid, _start)
                )
                return (await cursor.fetchone()[0]) or 0

        @classmethod
        async def study_times_since(cls, guildid: int, userid: int, *starts) -> int:
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
            conn = await cls._connector.get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(
                    query,
                    tuple(chain((guildid, userid), starts))
                )
                return [r['stime'] or 0 for r in await cursor.fetchall()]

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
        async def fetch_tags(self, guildid: Optional[int], userid: int):
            tags = await self.fetch_where(guildid=guildid, userid=userid)
            if not tags and guildid is not None:
                tags = await self.fetch_where(guildid=None, userid=userid)
            return [tag.tag for tag in tags]

        @classmethod
        async def set_tags(self, guildid: Optional[int], userid: int, tags: Iterable[str]):
            conn = await self._connector.get_connection()
            async with conn.transaction():
                await self.table.delete_where(guildid=guildid, userid=userid)
                if tags:
                    await self.table.insert_many(
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

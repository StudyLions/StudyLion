from psycopg import sql

from data import RowModel, Registry, Table
from data.columns import Integer, String, Timestamp, Bool


class TasklistData(Registry):
    class Task(RowModel):
        """
        Row model describing a single task in a tasklist.

        Schema
        ------
        CREATE TABLE tasklist(
          taskid SERIAL PRIMARY KEY,
          userid BIGINT NOT NULL REFERENCES user_config ON DELETE CASCADE,
          parentid INTEGER REFERENCES tasklist (taskid) ON DELETE SET NULL,
          content TEXT NOT NULL,
          rewarded BOOL DEFAULT FALSE,
          deleted_at TIMESTAMPTZ,
          completed_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ,
          last_updated_at TIMESTAMPTZ
        );
        CREATE INDEX tasklist_users ON tasklist (userid);

        CREATE TABLE tasklist_channels(
          guildid BIGINT NOT NULL REFERENCES guild_config (guildid) ON DELETE CASCADE,
          channelid BIGINT NOT NULL
        );
        CREATE INDEX tasklist_channels_guilds ON tasklist_channels (guildid);
        """
        _tablename_ = "tasklist"

        taskid = Integer(primary=True)
        userid = Integer()
        parentid = Integer()
        rewarded = Bool()
        content = String()
        completed_at = Timestamp()
        created_at = Timestamp()
        deleted_at = Timestamp()
        last_updated_at = Timestamp()

    channels = Table('tasklist_channels')

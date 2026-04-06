# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Data registry for shared tasklist (kanban boards)
# ============================================================
from data import RowModel, Registry, Table
from data.columns import Integer, String, Timestamp


class SharedTasklistData(Registry):
    class Board(RowModel):
        """
        Schema
        ------
        CREATE TABLE shared_tasklist(
          listid SERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          description TEXT,
          ownerid BIGINT NOT NULL,
          color TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW(),
          deleted_at TIMESTAMPTZ
        );
        """
        _tablename_ = "shared_tasklist"

        listid = Integer(primary=True)
        name = String()
        description = String()
        ownerid = Integer()
        color = String()
        created_at = Timestamp()
        updated_at = Timestamp()
        deleted_at = Timestamp()

    class Column(RowModel):
        """
        Schema
        ------
        CREATE TABLE shared_tasklist_column(
          columnid SERIAL PRIMARY KEY,
          listid INTEGER NOT NULL,
          name TEXT NOT NULL,
          position INTEGER NOT NULL,
          color TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        _tablename_ = "shared_tasklist_column"

        columnid = Integer(primary=True)
        listid = Integer()
        name = String()
        position = Integer()
        color = String()
        created_at = Timestamp()

    class Member(RowModel):
        """
        Schema
        ------
        CREATE TABLE shared_tasklist_member(
          listid INTEGER NOT NULL,
          userid BIGINT NOT NULL,
          role TEXT NOT NULL DEFAULT 'viewer',
          joined_at TIMESTAMPTZ DEFAULT NOW(),
          invited_by BIGINT,
          PRIMARY KEY (listid, userid)
        );
        """
        _tablename_ = "shared_tasklist_member"

        listid = Integer(primary=True)
        userid = Integer(primary=True)
        role = String()
        joined_at = Timestamp()
        invited_by = Integer()

    class Task(RowModel):
        """
        Schema
        ------
        CREATE TABLE shared_task(
          taskid SERIAL PRIMARY KEY,
          listid INTEGER NOT NULL,
          columnid INTEGER,
          content TEXT NOT NULL,
          description TEXT,
          position INTEGER NOT NULL DEFAULT 0,
          color TEXT,
          assignee_id BIGINT,
          created_by BIGINT NOT NULL,
          completed_at TIMESTAMPTZ,
          deleted_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          last_updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        _tablename_ = "shared_task"

        taskid = Integer(primary=True)
        listid = Integer()
        columnid = Integer()
        content = String()
        description = String()
        position = Integer()
        color = String()
        assignee_id = Integer()
        created_by = Integer()
        completed_at = Timestamp()
        deleted_at = Timestamp()
        created_at = Timestamp()
        last_updated_at = Timestamp()

    history = Table('shared_task_history')

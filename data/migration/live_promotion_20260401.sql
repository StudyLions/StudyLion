-- ============================================================
-- LIVE DB PROMOTION: 2026-04-01
-- Applies all schema changes from test (studylion_test) to live (studylion)
-- 
-- Changes:
--   1. Screen channels module (v17-v18 migration)
--   2. Shared kanban boards (5 tables)
--
-- Rollback: restore from /home/leo/live/schema_backup_20260401.sql
-- ============================================================

BEGIN;

-- ============================================================
-- PART 1: Screen Channels (v17-v18)
-- ============================================================

CREATE TABLE IF NOT EXISTS screen_channels(
  guildid BIGINT NOT NULL,
  channelid BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS screen_channels_guilds ON screen_channels (guildid);

CREATE TABLE IF NOT EXISTS screen_exempt_roles(
  guildid BIGINT NOT NULL,
  roleid BIGINT NOT NULL,
  _timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (guildid) REFERENCES guild_config (guildid) ON DELETE CASCADE ON UPDATE CASCADE,
  PRIMARY KEY (guildid, roleid)
);

CREATE TABLE IF NOT EXISTS screenban_durations(
  rowid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  duration INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS screenban_durations_guilds ON screenban_durations (guildid);

ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS screenban_role BIGINT;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS screen_grace_period INTEGER;

ALTER TABLE members ADD COLUMN IF NOT EXISTS screen_warned BOOLEAN DEFAULT FALSE;

ALTER TYPE TicketType ADD VALUE IF NOT EXISTS 'SCREEN_BAN';

-- ============================================================
-- PART 2: Shared Kanban Boards
-- ============================================================

CREATE TABLE IF NOT EXISTS shared_tasklist(
  listid SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  ownerid BIGINT NOT NULL,
  color TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS shared_tasklist_owners ON shared_tasklist (ownerid);
ALTER TABLE shared_tasklist
  ADD CONSTRAINT fk_shared_tasklist_owner
  FOREIGN KEY (ownerid)
  REFERENCES user_config (userid)
  ON DELETE CASCADE
  NOT VALID;

CREATE TABLE IF NOT EXISTS shared_tasklist_column(
  columnid SERIAL PRIMARY KEY,
  listid INTEGER NOT NULL,
  name TEXT NOT NULL,
  position INTEGER NOT NULL,
  color TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS shared_tasklist_column_lists ON shared_tasklist_column (listid);
ALTER TABLE shared_tasklist_column
  ADD CONSTRAINT fk_shared_tasklist_column_list
  FOREIGN KEY (listid)
  REFERENCES shared_tasklist (listid)
  ON DELETE CASCADE
  NOT VALID;

CREATE TABLE IF NOT EXISTS shared_tasklist_member(
  listid INTEGER NOT NULL,
  userid BIGINT NOT NULL,
  role TEXT NOT NULL DEFAULT 'viewer',
  joined_at TIMESTAMPTZ DEFAULT NOW(),
  invited_by BIGINT,
  PRIMARY KEY (listid, userid)
);
CREATE INDEX IF NOT EXISTS shared_tasklist_member_users ON shared_tasklist_member (userid);
ALTER TABLE shared_tasklist_member
  ADD CONSTRAINT fk_shared_tasklist_member_list
  FOREIGN KEY (listid)
  REFERENCES shared_tasklist (listid)
  ON DELETE CASCADE
  NOT VALID;
ALTER TABLE shared_tasklist_member
  ADD CONSTRAINT fk_shared_tasklist_member_user
  FOREIGN KEY (userid)
  REFERENCES user_config (userid)
  ON DELETE CASCADE
  NOT VALID;

CREATE TABLE IF NOT EXISTS shared_task(
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
CREATE INDEX IF NOT EXISTS shared_task_lists ON shared_task (listid);
CREATE INDEX IF NOT EXISTS shared_task_columns ON shared_task (columnid);
ALTER TABLE shared_task
  ADD CONSTRAINT fk_shared_task_list
  FOREIGN KEY (listid)
  REFERENCES shared_tasklist (listid)
  ON DELETE CASCADE
  NOT VALID;
ALTER TABLE shared_task
  ADD CONSTRAINT fk_shared_task_column
  FOREIGN KEY (columnid)
  REFERENCES shared_tasklist_column (columnid)
  ON DELETE SET NULL
  NOT VALID;
ALTER TABLE shared_task
  ADD CONSTRAINT fk_shared_task_assignee
  FOREIGN KEY (assignee_id)
  REFERENCES user_config (userid)
  ON DELETE SET NULL
  NOT VALID;

CREATE TABLE IF NOT EXISTS shared_task_history(
  historyid SERIAL PRIMARY KEY,
  listid INTEGER NOT NULL,
  taskid INTEGER,
  userid BIGINT NOT NULL,
  action TEXT NOT NULL,
  details JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS shared_task_history_lists ON shared_task_history (listid, created_at DESC);
ALTER TABLE shared_task_history
  ADD CONSTRAINT fk_shared_task_history_list
  FOREIGN KEY (listid)
  REFERENCES shared_tasklist (listid)
  ON DELETE CASCADE
  NOT VALID;

-- ============================================================
-- PART 3: Grant permissions to leo user
-- ============================================================

GRANT ALL ON screen_channels TO leo;
GRANT ALL ON screen_exempt_roles TO leo;
GRANT ALL ON screenban_durations TO leo;
GRANT ALL ON SEQUENCE screenban_durations_rowid_seq TO leo;

GRANT ALL ON shared_tasklist TO leo;
GRANT ALL ON SEQUENCE shared_tasklist_listid_seq TO leo;
GRANT ALL ON shared_tasklist_column TO leo;
GRANT ALL ON SEQUENCE shared_tasklist_column_columnid_seq TO leo;
GRANT ALL ON shared_tasklist_member TO leo;
GRANT ALL ON shared_task TO leo;
GRANT ALL ON SEQUENCE shared_task_taskid_seq TO leo;
GRANT ALL ON shared_task_history TO leo;
GRANT ALL ON SEQUENCE shared_task_history_historyid_seq TO leo;

COMMIT;

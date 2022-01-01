-- Improved tasklist statistics
ALTER TABLE tasklist
  ADD COLUMN completed_at TIMESTAMPTZ,
  ADD COLUMN deleted_at TIMESTAMPTZ,
  ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN last_updated_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';

UPDATE tasklist SET deleted_at = NOW() WHERE last_updated_at < NOW() - INTERVAL '24h';
UPDATE tasklist SET completed_at = last_updated_at WHERE complete;

ALTER TABLE tasklist
  DROP COLUMN complete;


-- New member profile tags
CREATE TABLE member_profile_tags(
  tagid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  userid BIGINT NOT NULL,
  tag TEXT NOT NULL,
  _timestamp TIMESTAMPTZ DEFAULT now(),
  FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid)
);
CREATE INDEX member_profile_tags_members ON member_profile_tags (guildid, userid);


-- New member weekly and monthly goals
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

INSERT INTO VersionHistory (version, author) VALUES (7, 'v6-v7 migration');

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


INSERT INTO VersionHistory (version, author) VALUES (7, 'v6-v7 migration');

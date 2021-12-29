-- Add deletion column to tasklist entries
-- Add completed_at column to the tasklist entries, replacing complete


ALTER TABLE tasklist
  ADD COLUMN completed_at TIMESTAMPTZ,
  ADD COLUMN deleted_at TIMESTAMPTZ,
  ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN last_updated_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';

UPDATE tasklist SET deleted_at = NOW() WHERE last_updated_at < NOW() - INTERVAL '24h';
UPDATE tasklist SET completed_at = last_updated_at WHERE complete;

ALTER TABLE tasklist
  DROP COLUMN complete;


-- Mark all tasklist entries older than a day as deleted

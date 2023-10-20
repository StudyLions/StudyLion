BEGIN;

ALTER TABLE bot_config ADD COLUMN sponsor_prompt TEXT;
ALTER TABLE bot_config ADD COLUMN sponsor_message TEXT;

INSERT INTO VersionHistory (version, author) VALUES (14, 'v13-v14 migration');
COMMIT;

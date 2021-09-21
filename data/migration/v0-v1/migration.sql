ALTER TABLE tasklist DROP COLUMN guildid;
CREATE INDEX tasklist_users ON tasklist (userid);

ALTER TABLE tasklist_reward_history DROP COLUMN guildid;
CREATE INDEX tasklist_reward_history_users ON tasklist_reward_history (userid, reward_time);


INSERT INTO VersionHistory (version, author) VALUES (1, 'Migration v0-v1');

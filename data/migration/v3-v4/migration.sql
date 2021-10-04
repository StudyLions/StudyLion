ALTER TABLE guild_config
  ADD COLUMN greeting_channel BIGINT,
  ADD COLUMN greeting_message TEXT,
  ADD COLUMN returning_message TEXT,
  ADD COLUMN starting_funds INTEGER;

CREATE INDEX rented_members_users ON rented_members (userid);

INSERT INTO VersionHistory (version, author) VALUES (4, 'v3-v4 Migration');

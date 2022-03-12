-- Sponsor Data {{{
CREATE TABLE sponsor_text(
  ID INTEGER PRIMARY KEY DEFAULT 0,
  prompt_text TEXT,
  command_response TEXT
);
-- }}}

INSERT INTO VersionHistory (version, author) VALUES (11, 'v10-v11 migration');

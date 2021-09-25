DROP TABLE IF EXISTS study_bans CASCADE;
DROP TABLE IF EXISTS tickets CASCADE;
DROP TABLE IF EXISTS study_ban_auto_durations CASCADE;

ALTER TABLE members ADD COLUMN
  video_warned BOOLEAN DEFAULT FALSE;

ALTER TABLE guild_config DROP COLUMN study_ban_role;

ALTER TABLE guild_config
  ADD COLUMN alert_channel BIGINT,
  ADD COLUMN video_studyban BOOLEAN,
  ADD COLUMN video_grace_period INTEGER,
  ADD COLUMN studyban_role BIGINT;


CREATE TYPE TicketState AS ENUM (
  'OPEN',
  'EXPIRING',
  'EXPIRED',
  'PARDONED'
);

CREATE TABLE tickets(
  ticketid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  targetid BIGINT NOT NULL,
  ticket_type TicketType NOT NULL, 
  ticket_state TicketState NOT NULL DEFAULT 'OPEN',
  moderator_id BIGINT NOT NULL,
  log_msg_id BIGINT,
  created_at TIMESTAMP DEFAULT (now() at time zone 'utc'),
  auto BOOLEAN DEFAULT FALSE,  -- Whether the ticket was automatically created
  content TEXT,  -- Main ticket content, usually contains the ticket reason
  context TEXT,  -- Optional flexible column only used by some TicketTypes
  addendum TEXT,  -- Optional extra text used for after-the-fact context information
  duration INTEGER,  -- Optional duration column, mostly used by automatic tickets
  file_name TEXT,  -- Optional file name to accompany the ticket
  file_data BYTEA,  -- Optional file data to accompany the ticket
  expiry TIMESTAMPTZ,  -- Time to automatically expire the ticket  
  pardoned_by BIGINT,  -- Actorid who pardoned the ticket
  pardoned_at TIMESTAMPTZ,  -- Time when the ticket was pardoned
  pardoned_reason TEXT  -- Reason the ticket was pardoned
);
CREATE INDEX tickets_members_types ON tickets (guildid, targetid, ticket_type);
CREATE INDEX tickets_states ON tickets (ticket_state);

CREATE VIEW ticket_info AS
  SELECT
    *,
    row_number() OVER (PARTITION BY guildid ORDER BY ticketid) AS guild_ticketid
  FROM tickets
  ORDER BY ticketid;

ALTER TABLE ticket_info ALTER ticket_state SET DEFAULT 'OPEN';
ALTER TABLE ticket_info ALTER created_at SET DEFAULT (now() at time zone 'utc');
ALTER TABLE ticket_info ALTER auto SET DEFAULT False;

CREATE OR REPLACE FUNCTION instead_of_ticket_info()
  RETURNS trigger AS
$$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO tickets(
          guildid,
          targetid,
          ticket_type, 
          ticket_state,
          moderator_id,
          log_msg_id,
          created_at,
          auto,
          content,
          context,
          addendum,
          duration,
          file_name,
          file_data,
          expiry,
          pardoned_by,
          pardoned_at,
          pardoned_reason
        ) VALUES (
          NEW.guildid,
          NEW.targetid,
          NEW.ticket_type, 
          NEW.ticket_state,
          NEW.moderator_id,
          NEW.log_msg_id,
          NEW.created_at,
          NEW.auto,
          NEW.content,
          NEW.context,
          NEW.addendum,
          NEW.duration,
          NEW.file_name,
          NEW.file_data,
          NEW.expiry,
          NEW.pardoned_by,
          NEW.pardoned_at,
          NEW.pardoned_reason
        ) RETURNING ticketid INTO NEW.ticketid;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE tickets SET
          guildid = NEW.guildid,
          targetid = NEW.targetid,
          ticket_type = NEW.ticket_type, 
          ticket_state = NEW.ticket_state,
          moderator_id = NEW.moderator_id,
          log_msg_id = NEW.log_msg_id,
          created_at = NEW.created_at,
          auto = NEW.auto,
          content = NEW.content,
          context = NEW.context,
          addendum = NEW.addendum,
          duration = NEW.duration,
          file_name = NEW.file_name,
          file_data = NEW.file_data,
          expiry = NEW.expiry,
          pardoned_by = NEW.pardoned_by,
          pardoned_at = NEW.pardoned_at,
          pardoned_reason = NEW.pardoned_reason
        WHERE
          ticketid = OLD.ticketid;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM tickets WHERE ticketid = OLD.ticketid;
        RETURN OLD;
    END IF;
END;
$$ LANGUAGE PLPGSQL;

CREATE TRIGGER instead_of_ticket_info_trig
    INSTEAD OF INSERT OR UPDATE OR DELETE ON
      ticket_info FOR EACH ROW 
      EXECUTE PROCEDURE instead_of_ticket_info();

CREATE TABLE studyban_durations(
  rowid SERIAL PRIMARY KEY,
  guildid BIGINT NOT NULL,
  duration INTEGER NOT NULL
);
CREATE INDEX studyban_durations_guilds ON studyban_durations(guildid);


INSERT INTO VersionHistory (version, author) VALUES (2, 'v1-v2 Migration');

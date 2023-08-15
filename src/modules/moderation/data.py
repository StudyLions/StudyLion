from enum import Enum

from data import Registry, Table, RowModel, RegisterEnum
from data.columns import (
    Column,
    Integer, String, Bool, Timestamp,
)


class TicketType(Enum):
    """
    Schema
    ------
    CREATE TYPE TicketType AS ENUM (
      'NOTE',
      'STUDY_BAN',
      'MESSAGE_CENSOR',
      'INVITE_CENSOR',
      'WARNING'
    );
    """
    NOTE = 'NOTE',
    STUDY_BAN = 'STUDY_BAN',
    MESSAGE_CENSOR = 'MESSAGE_CENSOR',
    INVITE_CENSOR = 'INVITE_CENSOR',
    WARNING = 'WARNING',


class TicketState(Enum):
    """
    Schema
    ------
    CREATE TYPE TicketState AS ENUM (
      'OPEN',
      'EXPIRING',
      'EXPIRED',
      'PARDONED'
    );
    """
    OPEN = 'OPEN',
    EXPIRING = 'EXPIRING',
    EXPIRED = 'EXPIRED',
    PARDONED = 'PARDONED',


class ModerationData(Registry):
    _TicketType = RegisterEnum(TicketType, 'TicketType')
    _TicketState = RegisterEnum(TicketState, 'TicketState')

    class Ticket(RowModel):
        """
        Schema
        ------
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
        """
        _tablename_ = 'ticket_info'

        ticketid = Integer(primary=True)
        guild_ticketid = Integer()
        guildid = Integer()
        targetid = Integer()
        ticket_type: Column[TicketType] = Column()
        ticket_state: Column[TicketState] = Column()
        moderator_id = Integer()
        log_msg_id = Integer()
        auto = Bool()
        content = String()
        context = String()
        addendum = String()
        duration = Integer()
        file_name = String()
        file_data = String()
        expiry = Timestamp()
        pardoned_by = Integer()
        pardoned_at = Integer()
        pardoned_reason = String()
        created_at = Timestamp()

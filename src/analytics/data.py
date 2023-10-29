from enum import Enum

from data.registry import Registry
from data.adapted import RegisterEnum
from data.models import RowModel
from data.columns import Integer, String, Timestamp, Column


class CommandStatus(Enum):
    """
    Schema
    ------
    CREATE TYPE analytics.CommandStatus AS ENUM(
        'COMPLETED',
        'CANCELLED'
        'FAILED'
    );
    """
    COMPLETED = ('COMPLETED',)
    CANCELLED = ('CANCELLED',)
    FAILED = ('FAILED',)


class GuildAction(Enum):
    """
    Schema
    ------
    CREATE TYPE analytics.GuildAction AS ENUM(
        'JOINED',
        'LEFT'
    );
    """
    JOINED = ('JOINED',)
    LEFT = ('LEFT',)


class VoiceAction(Enum):
    """
    Schema
    ------
    CREATE TYPE analytics.VoiceAction AS ENUM(
        'JOINED',
        'LEFT'
    );
    """
    JOINED = ('JOINED',)
    LEFT = ('LEFT',)


class AnalyticsData(Registry, name='analytics'):
    CommandStatus = RegisterEnum(CommandStatus, name="analytics.CommandStatus")
    GuildAction = RegisterEnum(GuildAction, name="analytics.GuildAction")
    VoiceAction = RegisterEnum(VoiceAction, name="analytics.VoiceAction")

    class Snapshots(RowModel):
        """
        Schema
        ------
        CREATE TABLE analytics.snapshots(
            snapshotid SERIAL PRIMARY KEY,
            appname TEXT NOT NULL REFERENCES bot_config (appname),
            guild_count INTEGER NOT NULL,
            member_count INTEGER NOT NULL,
            user_count INTEGER NOT NULL,
            in_voice INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc')
        );
        """
        _schema_ = 'analytics'
        _tablename_ = 'snapshots'

        snapshotid = Integer(primary=True)
        appname = String()
        guild_count = Integer()
        member_count = Integer()
        user_count = Integer()
        in_voice = Integer()
        created_at = Timestamp()

    class Events(RowModel):
        """
        Schema
        ------
        CREATE TABLE analytics.events(
            eventid SERIAL PRIMARY KEY,
            appname TEXT NOT NULL REFERENCES bot_config (appname),
            ctxid BIGINT,
            guildid BIGINT,
            _created_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc')
        );
        """
        _schema_ = 'analytics'
        _tablename_ = 'events'

        eventid = Integer(primary=True)
        appname = String()
        ctxid = Integer()
        guildid = Integer()
        created_at = Timestamp()

    class Commands(RowModel):
        """
        Schema
        ------
        CREATE TABLE analytics.commands(
            cmdname TEXT NOT NULL,
            cogname TEXT,
            userid BIGINT NOT NULL,
            status analytics.CommandStatus NOT NULL,
            execution_time REAL NOT NULL
        ) INHERITS (analytics.events);
        """
        _schema_ = 'analytics'
        _tablename_ = 'commands'

        eventid = Integer(primary=True)
        appname = String()
        ctxid = Integer()
        guildid = Integer()
        created_at = Timestamp()

        cmdname = String()
        cogname = String()
        userid = Integer()
        status: Column[CommandStatus] = Column()
        error = String()
        execution_time: Column[float] = Column()

    class Guilds(RowModel):
        """
        Schema
        ------
        CREATE TABLE analytics.guilds(
            guildid BIGINT NOT NULL,
            action analytics.GuildAction NOT NULL
        ) INHERITS (analytics.events);
        """
        _schema_ = 'analytics'
        _tablename_ = 'guilds'

        eventid = Integer(primary=True)
        appname = String()
        ctxid = Integer()
        guildid = Integer()
        created_at = Timestamp()

        action: Column[GuildAction] = Column()

    class VoiceSession(RowModel):
        """
        Schema
        ------
        CREATE TABLE analytics.voice_sessions(
            userid BIGINT NOT NULL,
            action analytics.VoiceAction NOT NULL
        ) INHERITS (analytics.events);
        """
        _schema_ = 'analytics'
        _tablename_ = 'voice_sessions'

        eventid = Integer(primary=True)
        appname = String()
        ctxid = Integer()
        guildid = Integer()
        created_at = Timestamp()

        userid = Integer()
        action: Column[GuildAction] = Column()

    class GuiRender(RowModel):
        """
        Schema
        ------
        CREATE TABLE analytics.gui_renders(
            cardname TEXT NOT NULL,
            duration INTEGER NOT NULL
        ) INHERITS (analytics.events);
        """
        _schema_ = 'analytics'
        _tablename_ = 'gui_renders'

        eventid = Integer(primary=True)
        appname = String()
        ctxid = Integer()
        guildid = Integer()
        created_at = Timestamp()

        cardname = String()
        duration = Integer()

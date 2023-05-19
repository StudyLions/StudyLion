from data import Registry, RowModel
from data.columns import Integer, Bool, Timestamp, String


class TimerData(Registry):
    class Timer(RowModel):
        """
        Schema
        ------
        CREATE TABLE timers(
          channelid BIGINT PRIMARY KEY,
          guildid BIGINT NOT NULL REFERENCES guild_config (guildid),
          ownerid BIGINT REFERENCES user_config,
          manager_roleid BIGINT,
          notification_channelid BIGINT,
          focus_length INTEGER NOT NULL,
          break_length INTEGER NOT NULL,
          last_started TIMESTAMPTZ,
          last_messageid BIGINT,
          voice_alerts BOOLEAN,
          inactivity_threshold INTEGER,
          auto_restart BOOLEAN,
          channel_name TEXT,
          pretty_name TEXT
        );
        CREATE INDEX timers_guilds ON timers (guildid);
        """
        _tablename_ = 'timers'

        channelid = Integer(primary=True)
        guildid = Integer()
        ownerid = Integer()
        manager_roleid = Integer()

        last_started = Timestamp()
        focus_length = Integer()
        break_length = Integer()
        auto_restart = Bool()

        inactivity_threshold = Integer()
        notification_channelid = Integer()
        last_messageid = Integer()
        voice_alerts = Bool()

        channel_name = String()
        pretty_name = String()

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

    # --- AI-MODIFIED (2026-03-18) ---
    # Purpose: Premium pomodoro config, streak tracking, and milestone tables
    class PremiumPomodoroConfig(RowModel):
        """
        Schema
        ------
        CREATE TABLE premium_pomodoro_config(
          guildid BIGINT PRIMARY KEY REFERENCES guild_config (guildid),
          focus_roleid BIGINT,
          session_summary BOOLEAN NOT NULL DEFAULT TRUE,
          animated_timer BOOLEAN NOT NULL DEFAULT TRUE,
          timer_theme VARCHAR(32) DEFAULT 'default',
          group_goal_hours INTEGER,
          coin_multiplier BOOLEAN NOT NULL DEFAULT TRUE,
          golden_hour_start TIME,
          golden_hour_end TIME
        );
        """
        _tablename_ = 'premium_pomodoro_config'

        guildid = Integer(primary=True)
        focus_roleid = Integer()
        session_summary = Bool()
        animated_timer = Bool()
        timer_theme = String()
        group_goal_hours = Integer()
        coin_multiplier = Bool()
        golden_hour_start = String()
        golden_hour_end = String()

    class PomodoroStreak(RowModel):
        """
        Schema
        ------
        CREATE TABLE pomodoro_streaks(
          userid BIGINT PRIMARY KEY REFERENCES user_config (userid),
          current_daily_streak INTEGER NOT NULL DEFAULT 0,
          longest_daily_streak INTEGER NOT NULL DEFAULT 0,
          current_weekly_streak INTEGER NOT NULL DEFAULT 0,
          longest_weekly_streak INTEGER NOT NULL DEFAULT 0,
          last_pomodoro_date DATE,
          total_cycles_completed INTEGER NOT NULL DEFAULT 0,
          total_focus_minutes INTEGER NOT NULL DEFAULT 0,
          focus_power INTEGER NOT NULL DEFAULT 0
        );
        """
        _tablename_ = 'pomodoro_streaks'

        userid = Integer(primary=True)
        current_daily_streak = Integer()
        longest_daily_streak = Integer()
        current_weekly_streak = Integer()
        longest_weekly_streak = Integer()
        last_pomodoro_date = String()
        total_cycles_completed = Integer()
        total_focus_minutes = Integer()
        focus_power = Integer()

    class PomodoroMilestone(RowModel):
        """
        Schema
        ------
        CREATE TABLE pomodoro_milestones(
          milestoneid SERIAL PRIMARY KEY,
          userid BIGINT NOT NULL REFERENCES user_config (userid),
          guildid BIGINT NOT NULL REFERENCES guild_config (guildid),
          milestone_type VARCHAR(32) NOT NULL,
          milestone_value INTEGER NOT NULL,
          achieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (userid, guildid, milestone_type, milestone_value)
        );
        CREATE INDEX pomodoro_milestones_user ON pomodoro_milestones (userid);
        """
        _tablename_ = 'pomodoro_milestones'

        milestoneid = Integer(primary=True)
        userid = Integer()
        guildid = Integer()
        milestone_type = String()
        milestone_value = Integer()
        achieved_at = Timestamp()
    # --- END AI-MODIFIED ---

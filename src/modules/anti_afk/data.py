# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-06
# Purpose: Database models for Anti AFK System module.
#          Single config table with one row per guild.
# ============================================================
import json

from data import Registry, RowModel
from data.columns import Integer, String, Bool
from meta.logger import log_wrap


class AntiAfkData(Registry, name='anti_afk'):

    class Config(RowModel):
        """
        Schema
        ------
        CREATE TABLE IF NOT EXISTS anti_afk_config (
            guildid BIGINT PRIMARY KEY REFERENCES guild_config(guildid),
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            check_interval INTEGER NOT NULL DEFAULT 60,
            grace_period INTEGER NOT NULL DEFAULT 5,
            action TEXT NOT NULL DEFAULT 'kick',
            max_warnings INTEGER NOT NULL DEFAULT 1,
            min_users INTEGER NOT NULL DEFAULT 1,
            warning_message TEXT NOT NULL DEFAULT 'Are you still studying?',
            exempt_roles TEXT NOT NULL DEFAULT '[]',
            target_channels TEXT NOT NULL DEFAULT '[]',
            exclude_channels TEXT NOT NULL DEFAULT '[]',
            use_dms BOOLEAN NOT NULL DEFAULT FALSE,
            fallback_channelid BIGINT,
            skip_streaming BOOLEAN NOT NULL DEFAULT TRUE,
            notify_on_action BOOLEAN NOT NULL DEFAULT TRUE,
            notification_channelid BIGINT,
            max_actions_per_hour INTEGER NOT NULL DEFAULT 100
        );
        """
        _tablename_ = 'anti_afk_config'

        guildid = Integer(primary=True)
        enabled = Bool()
        check_interval = Integer()
        grace_period = Integer()
        action = String()
        max_warnings = Integer()
        min_users = Integer()
        warning_message = String()
        exempt_roles = String()
        target_channels = String()
        exclude_channels = String()
        use_dms = Bool()
        fallback_channelid = Integer()
        skip_streaming = Bool()
        notify_on_action = Bool()
        notification_channelid = Integer()
        max_actions_per_hour = Integer()

        @property
        def exempt_roles_list(self) -> list[int]:
            val = self.exempt_roles
            if val and isinstance(val, str):
                try:
                    return [int(r) for r in json.loads(val)]
                except (json.JSONDecodeError, ValueError):
                    return []
            if isinstance(val, list):
                return [int(r) for r in val]
            return []

        @property
        def target_channels_list(self) -> list[int]:
            val = self.target_channels
            if val and isinstance(val, str):
                try:
                    return [int(c) for c in json.loads(val)]
                except (json.JSONDecodeError, ValueError):
                    return []
            if isinstance(val, list):
                return [int(c) for c in val]
            return []

        @property
        def exclude_channels_list(self) -> list[int]:
            val = self.exclude_channels
            if val and isinstance(val, str):
                try:
                    return [int(c) for c in json.loads(val)]
                except (json.JSONDecodeError, ValueError):
                    return []
            if isinstance(val, list):
                return [int(c) for c in val]
            return []

        @classmethod
        @log_wrap(action='fetch_anti_afk_config')
        async def fetch_config(cls, guildid: int):
            rows = await cls.fetch_where(guildid=guildid)
            return rows[0] if rows else None

        @classmethod
        @log_wrap(action='fetch_enabled_anti_afk')
        async def fetch_all_enabled(cls):
            return await cls.fetch_where(enabled=True)

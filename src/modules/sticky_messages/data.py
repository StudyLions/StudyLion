# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-22
# Purpose: Database models for sticky messages module
# ============================================================
from data import Registry, RowModel
from data.columns import Integer, String, Bool, Timestamp
from meta.logger import log_wrap


class StickyData(Registry, name='sticky_messages'):

    class StickyMessage(RowModel):
        """
        Schema
        ------
        CREATE TABLE sticky_messages (
            stickyid SERIAL PRIMARY KEY,
            guildid BIGINT NOT NULL REFERENCES guild_config(guildid) ON DELETE CASCADE,
            channelid BIGINT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            color INTEGER DEFAULT 3447003,
            image_url TEXT,
            footer_text TEXT,
            interval_seconds INTEGER NOT NULL DEFAULT 60,
            last_posted_id BIGINT,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_by BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(guildid, channelid)
        );
        """
        _tablename_ = 'sticky_messages'

        stickyid = Integer(primary=True)
        guildid = Integer()
        channelid = Integer()
        title = String()
        content = String()
        color = Integer()
        image_url = String()
        footer_text = String()
        interval_seconds = Integer()
        last_posted_id = Integer()
        enabled = Bool()
        created_by = Integer()
        created_at = Timestamp()

        @classmethod
        @log_wrap(action='fetch_guild_stickies')
        async def fetch_guild_stickies(cls, guildid: int):
            return await cls.fetch_where(guildid=guildid)

        @classmethod
        @log_wrap(action='fetch_enabled_for_guild')
        async def fetch_enabled_for_guild(cls, guildid: int):
            return await cls.fetch_where(guildid=guildid, enabled=True)

        @classmethod
        @log_wrap(action='fetch_by_channel')
        async def fetch_by_channel(cls, guildid: int, channelid: int):
            rows = await cls.fetch_where(guildid=guildid, channelid=channelid)
            return rows[0] if rows else None

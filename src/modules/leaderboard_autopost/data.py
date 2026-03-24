# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-21
# Purpose: Database models for leaderboard auto-post module
# ============================================================
import json
from psycopg import sql

from data import Registry, RowModel
from data.columns import Integer, String, Timestamp, Bool, Column
from meta.logger import log_wrap


class AutopostData(Registry, name='leaderboard_autopost'):

    class Config(RowModel):
        """
        Schema
        ------
        CREATE TABLE leaderboard_autopost_config (
            configid SERIAL PRIMARY KEY,
            guildid BIGINT NOT NULL REFERENCES guild_config(guildid) ON DELETE CASCADE,
            config_name VARCHAR(64) NOT NULL DEFAULT 'Leaderboard',
            enabled BOOLEAN NOT NULL DEFAULT true,
            ...
            UNIQUE(guildid, config_name)
        );
        """
        _tablename_ = 'leaderboard_autopost_config'

        configid = Integer(primary=True)
        guildid = Integer()
        config_name = String()
        enabled = Bool()

        lb_type = String()
        messages_metric = String()
        frequency = String()
        seasonal_mode = String()
        week_starts_on = String()
        top_count = Integer()

        post_channel = Integer()
        post_day = Integer()
        post_hour = Integer()
        post_minute = Integer()

        top1_roles = String()
        topn_roles = String()
        auto_remove_roles = Bool()

        reward_tiers = String()

        announce_content = String()
        embed_title = String()
        embed_description = String()
        embed_footer = String()
        embed_color = Integer()
        embed_url = String()
        embed_author_name = String()
        embed_author_url = String()
        embed_fields = String()
        include_image = Bool()
        mention_winners = Bool()
        pin_post = Bool()
        delete_previous = Bool()
        min_threshold = Integer()

        notify_public_post = Bool()
        notify_dm_winners = Bool()
        dm_scope = String()
        dm_template_title = String()
        dm_template_body = String()
        dm_stagger_seconds = Integer()
        notify_mod_log = Bool()
        mod_log_channel = Integer()

        skip_if_empty = Bool()
        skip_if_same_as_last = Bool()
        continue_on_partial = Bool()
        max_coins_per_user = Integer()

        last_posted_at = Timestamp()
        last_message_id = Integer()
        last_winner_ids = String()
        created_at = Timestamp()

        @property
        def top1_roles_list(self):
            if self.top1_roles and isinstance(self.top1_roles, str):
                return [int(r) for r in json.loads(self.top1_roles)]
            if isinstance(self.top1_roles, list):
                return [int(r) for r in self.top1_roles]
            return []

        @property
        def topn_roles_list(self):
            if self.topn_roles and isinstance(self.topn_roles, str):
                return [int(r) for r in json.loads(self.topn_roles)]
            if isinstance(self.topn_roles, list):
                return [int(r) for r in self.topn_roles]
            return []

        @property
        def reward_tiers_list(self):
            if self.reward_tiers and isinstance(self.reward_tiers, str):
                return json.loads(self.reward_tiers)
            if isinstance(self.reward_tiers, list):
                return self.reward_tiers
            return []

        @property
        def embed_fields_list(self):
            if self.embed_fields and isinstance(self.embed_fields, str):
                return json.loads(self.embed_fields)
            if isinstance(self.embed_fields, list):
                return self.embed_fields
            return []

        @property
        def last_winner_ids_list(self):
            if self.last_winner_ids and isinstance(self.last_winner_ids, str):
                return json.loads(self.last_winner_ids)
            if isinstance(self.last_winner_ids, list):
                return self.last_winner_ids
            return []

        @classmethod
        @log_wrap(action='fetch_enabled_configs')
        async def fetch_enabled(cls):
            return await cls.fetch_where(enabled=True)

        @classmethod
        @log_wrap(action='fetch_guild_configs')
        async def fetch_for_guild(cls, guildid: int):
            return await cls.fetch_where(guildid=guildid)

    class History(RowModel):
        """
        Schema
        ------
        CREATE TABLE leaderboard_autopost_history (
            historyid SERIAL PRIMARY KEY,
            configid INT NOT NULL REFERENCES leaderboard_autopost_config(configid) ON DELETE CASCADE,
            ...
        );
        """
        _tablename_ = 'leaderboard_autopost_history'

        historyid = Integer(primary=True)
        configid = Integer()
        guildid = Integer()
        posted_at = Timestamp()
        top_users = String()
        roles_added = Integer()
        roles_removed = Integer()
        coins_awarded = Integer()
        dms_sent = Integer()
        dms_failed = Integer()
        status = String()
        error_message = String()

    class ActionQueue(RowModel):
        """
        Schema
        ------
        CREATE TABLE leaderboard_autopost_action_queue (
            queueid SERIAL PRIMARY KEY,
            ...
        );
        """
        _tablename_ = 'leaderboard_autopost_action_queue'

        queueid = Integer(primary=True)
        guildid = Integer()
        configid = Integer()
        requested_by = Integer()
        action_type = String()
        payload = String()
        status = String()
        result = String()
        created_at = Timestamp()
        processed_at = Timestamp()

        @classmethod
        @log_wrap(action='claim_pending_action')
        async def claim_pending(cls):
            """Claim the oldest pending action, atomically setting it to processing."""
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        UPDATE leaderboard_autopost_action_queue
                        SET status = 'processing'
                        WHERE queueid = (
                            SELECT queueid FROM leaderboard_autopost_action_queue
                            WHERE status = 'pending'
                            ORDER BY created_at ASC
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        )
                        RETURNING *
                        """,
                    )
                    row = await cursor.fetchone()
                    if row:
                        return cls._make_rows(row)[0]
                    return None

        @classmethod
        @log_wrap(action='expire_stale_actions')
        async def expire_stale(cls, max_age_seconds: int = 300):
            """Expire pending actions older than max_age_seconds."""
            async with cls._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        UPDATE leaderboard_autopost_action_queue
                        SET status = 'expired', processed_at = NOW()
                        WHERE status = 'pending'
                        AND created_at < NOW() - %s * INTERVAL '1 second'
                        """,
                        (max_age_seconds,),
                    )

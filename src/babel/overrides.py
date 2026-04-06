# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-01
# Purpose: Guild text override cache for the Text Branding
#          premium feature. Stores per-guild string overrides
#          keyed by gettext context, with TTL-based caching.
# ============================================================
import logging
import time
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes


class GuildTextOverrideCache:
    """In-memory cache for per-guild text overrides.

    The cache is loaded lazily on first access per guild, then refreshed
    after CACHE_TTL seconds. All reads are synchronous (dict lookups)
    so they can be called from the synchronous ``t()`` method.
    Writes (``load_overrides``, ``load_premium_status``) are async.
    """

    def __init__(self):
        self._cache: dict[int, dict[str, tuple[str, Optional[str]]]] = {}
        self._timestamps: dict[int, float] = {}
        self._premium: dict[int, bool] = {}
        self._premium_ts: dict[int, float] = {}

    def get_override(self, guildid: int, text_key: str) -> Optional[str]:
        guild_overrides = self._cache.get(guildid)
        if guild_overrides is None:
            return None
        if time.time() - self._timestamps.get(guildid, 0) > CACHE_TTL:
            return None
        entry = guild_overrides.get(text_key)
        return entry[0] if entry else None

    def get_plural_override(self, guildid: int, text_key: str) -> tuple[Optional[str], Optional[str]]:
        guild_overrides = self._cache.get(guildid)
        if guild_overrides is None:
            return None, None
        if time.time() - self._timestamps.get(guildid, 0) > CACHE_TTL:
            return None, None
        entry = guild_overrides.get(text_key)
        return entry if entry else (None, None)

    def is_premium(self, guildid: int) -> bool:
        if guildid not in self._premium:
            return False
        if time.time() - self._premium_ts.get(guildid, 0) > CACHE_TTL:
            return False
        return self._premium[guildid]

    def needs_load(self, guildid: int) -> bool:
        return (
            guildid not in self._cache
            or time.time() - self._timestamps.get(guildid, 0) > CACHE_TTL
        )

    def needs_premium_check(self, guildid: int) -> bool:
        return (
            guildid not in self._premium
            or time.time() - self._premium_ts.get(guildid, 0) > CACHE_TTL
        )

    async def load_overrides(self, bot, guildid: int):
        try:
            async with bot.db.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT text_key, custom_text, custom_text_plural "
                        "FROM guild_text_overrides WHERE guildid = %s",
                        [guildid]
                    )
                    rows = await cur.fetchall()
            self._cache[guildid] = {
                row['text_key']: (row['custom_text'], row.get('custom_text_plural'))
                for row in rows
            }
            self._timestamps[guildid] = time.time()
        except Exception:
            logger.debug("Failed to load text overrides for guild %s", guildid, exc_info=True)
            self._cache[guildid] = {}
            self._timestamps[guildid] = time.time()

    async def load_premium_status(self, bot, guildid: int):
        try:
            async with bot.db.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT premium_until FROM premium_guilds WHERE guildid = %s",
                        [guildid]
                    )
                    row = await cur.fetchone()
            if row and row['premium_until']:
                pu = row['premium_until']
                if pu.tzinfo is None:
                    pu = pu.replace(tzinfo=timezone.utc)
                is_premium = pu > datetime.now(timezone.utc)
            else:
                is_premium = False
            self._premium[guildid] = is_premium
            self._premium_ts[guildid] = time.time()
        except Exception:
            logger.debug("Failed to check premium for guild %s", guildid, exc_info=True)
            self._premium[guildid] = False
            self._premium_ts[guildid] = time.time()

    def invalidate(self, guildid: int):
        self._timestamps.pop(guildid, None)

    def invalidate_premium(self, guildid: int):
        self._premium_ts.pop(guildid, None)


override_cache = GuildTextOverrideCache()

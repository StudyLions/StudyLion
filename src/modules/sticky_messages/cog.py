# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-22
# Purpose: Sticky messages cog -- on_message listener that
#          keeps configured embeds pinned as the last message
#          in a channel. Dashboard-only config (no commands).
# ============================================================
import asyncio
import time as _time
from typing import Optional, Dict

import discord

from meta import LionBot, LionCog
from meta.logger import log_wrap
from utils.lib import utc_now

from . import logger
from .data import StickyData

MAX_STICKIES_PER_GUILD = 5


class StickyMessagesCog(LionCog):

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data: StickyData = bot.db.load_registry(StickyData())

        self._sticky_cache: dict[int, tuple[float, dict[int, object]]] = {}
        self._sticky_cache_ttl = 300

        self._last_repost: dict[int, float] = {}

        self._premium_cache: dict[int, tuple[float, bool]] = {}
        self._premium_cache_ttl = 1800

        self._repost_locks: dict[int, asyncio.Lock] = {}

    async def _get_guild_stickies(self, guildid: int) -> dict[int, object]:
        """Return {channelid: StickyMessage} for a guild, with TTL cache."""
        now = _time.monotonic()
        cached = self._sticky_cache.get(guildid)
        if cached and (now - cached[0]) < self._sticky_cache_ttl:
            return cached[1]

        rows = await self.data.StickyMessage.fetch_enabled_for_guild(guildid)
        mapping = {row.channelid: row for row in rows}
        self._sticky_cache[guildid] = (now, mapping)
        return mapping

    def _invalidate_guild_cache(self, guildid: int):
        self._sticky_cache.pop(guildid, None)

    async def _is_premium_guild(self, guildid: int) -> bool:
        now = _time.monotonic()
        cached = self._premium_cache.get(guildid)
        if cached and (now - cached[0]) < self._premium_cache_ttl:
            return cached[1]

        premcog = self.bot.get_cog('PremiumCog')
        if not premcog:
            self._premium_cache[guildid] = (now, False)
            return False

        try:
            result = await premcog.is_premium_guild(guildid)
        except Exception:
            result = False

        self._premium_cache[guildid] = (now, result)
        return result

    def _build_embed(self, sticky) -> discord.Embed:
        """Build a Discord embed from a sticky message row."""
        embed = discord.Embed(
            description=sticky.content,
            color=sticky.color or 3447003,
        )
        if sticky.title:
            embed.title = sticky.title

        embed.set_author(name="\U0001F4CC Sticky Message")

        if sticky.image_url:
            embed.set_image(url=sticky.image_url)
        if sticky.footer_text:
            embed.set_footer(text=sticky.footer_text)

        return embed

    def _get_lock(self, channelid: int) -> asyncio.Lock:
        lock = self._repost_locks.get(channelid)
        if lock is None:
            lock = asyncio.Lock()
            self._repost_locks[channelid] = lock
        return lock

    @LionCog.listener('on_message')
    async def on_message_sticky(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guildid = message.guild.id
        channelid = message.channel.id

        stickies = await self._get_guild_stickies(guildid)
        sticky = stickies.get(channelid)
        if sticky is None:
            return

        now = _time.monotonic()
        last = self._last_repost.get(channelid, 0)
        if (now - last) < sticky.interval_seconds:
            return

        if message.id == sticky.last_posted_id:
            return

        lock = self._get_lock(channelid)
        if lock.locked():
            return

        async with lock:
            if not await self._is_premium_guild(guildid):
                try:
                    await sticky.update(enabled=False)
                except Exception:
                    pass
                self._invalidate_guild_cache(guildid)
                logger.info(
                    "Disabled sticky %s in guild %s (premium lapsed)",
                    sticky.stickyid, guildid,
                )
                return

            channel = message.channel

            if sticky.last_posted_id:
                try:
                    old_msg = await channel.fetch_message(sticky.last_posted_id)
                    await old_msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

            try:
                embed = self._build_embed(sticky)
                new_msg = await channel.send(embed=embed)
                await sticky.update(last_posted_id=new_msg.id)
                self._last_repost[channelid] = _time.monotonic()

                if guildid in self._sticky_cache:
                    _, mapping = self._sticky_cache[guildid]
                    if channelid in mapping:
                        mapping[channelid] = await self.data.StickyMessage.fetch(sticky.stickyid)

            except discord.Forbidden:
                logger.warning(
                    "Missing permissions to send sticky in channel %s (guild %s)",
                    channelid, guildid,
                )
            except discord.HTTPException as e:
                logger.warning(
                    "Failed to send sticky in channel %s (guild %s): %s",
                    channelid, guildid, e,
                )

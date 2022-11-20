from typing import Optional
from cachetools import LRUCache
import discord

from meta import LionCog, LionBot, LionContext
from settings import InteractiveSetting
from utils.lib import utc_now
from data import WeakCache

from .data import CoreData


class Lion:
    """
    A Lion is a high level representation of a Member in the LionBot paradigm.

    All members interacted with by the application should be available as Lions.
    It primarily provides an interface to the User and Member data.
    Lion also provides centralised access to various Member properties and methods,
    that would normally be served by other cogs.

    Many Lion methods may only be used when the required cogs and extensions are loaded.
    A Lion may exist without a Bot instance or a Member in cache,
    although the functionality available will be more limited.

    There is no guarantee that a corresponding discord Member actually exists.
    """
    __slots__ = ('data', 'user_data', 'guild_data', '_member', '__weakref__')

    def __init__(self, data: CoreData.Member, user_data: CoreData.User, guild_data: CoreData.Guild):
        self.data = data
        self.user_data = user_data
        self.guild_data = guild_data

        self._member: Optional[discord.Member] = None

    # Data properties

    @property
    def key(self):
        return (self.data.guildid, self.data.userid)

    @property
    def guildid(self):
        return self.data.guildid

    @property
    def userid(self):
        return self.data.userid

    @classmethod
    def get(cls, guildid, userid):
        return cls._cache_.get((guildid, userid), None)

    # Setting interfaces
    # Each of these return an initialised member setting

    @property
    def timezone(self):
        pass

    @property
    def locale(self):
        pass

    # Time utilities
    @property
    def now(self):
        """
        Returns current time-zone aware time for the member.
        """
        pass

    # Discord data cache
    async def touch_discord_models(self, member: discord.Member):
        """
        Update the stored discord data from the givem member.
        Intended to be used when we get member data from events that may not be available in cache.
        """
        # Can we do these in one query?
        if member.guild and (self.guild_data.name != member.guild.name):
            await self.guild_data.update(name=member.guild.name)

        avatar_key = member.avatar.key if member.avatar else None
        await self.user_data.update(avatar_hash=avatar_key, name=member.name, last_seen=utc_now())

        if member.display_name != self.data.display_name:
            await self.data.update(display_name=member.display_name)


class Lions(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

        # Full Lions cache
        # Don't expire Lions with strong references
        self._cache_: WeakCache[tuple[int, int], 'Lion'] = WeakCache(LRUCache(5000))

        self._settings_: dict[str, InteractiveSetting] = {}

    async def fetch(self, guildid, userid) -> Lion:
        """
        Fetch or create the given Member.
        If the guild or user row doesn't exist, also creates it.
        Relies on the core cog existing, to retrieve the core data.
        """
        # TODO: Find a way to reduce this to one query, while preserving cache
        lion = self._cache_.get((guildid, userid))
        if lion is None:
            if self.bot.core:
                data = self.bot.core.data
            else:
                raise ValueError("Cannot fetch Lion before core module is attached.")

            guild = await data.Guild.fetch_or_create(guildid)
            user = await data.User.fetch_or_create(userid)
            member = await data.Member.fetch_or_create(guildid, userid)
            lion = Lion(member, user, guild)
            self._cache_[(guildid, userid)] = lion
        return lion

    def add_model_setting(self, setting: InteractiveSetting):
        self._settings_[setting.__class__.__name__] = setting
        return setting

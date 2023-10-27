import logging
from typing import Optional
from collections import defaultdict
from weakref import WeakValueDictionary

import discord
import discord.app_commands as appcmd

from meta import LionBot, LionCog, LionContext
from meta.app import shardname, appname
from meta.logger import log_wrap
from utils.lib import utc_now

from settings.groups import SettingGroup

from .data import CoreData
from .lion import Lions
from .lion_guild import GuildConfig
from .lion_member import MemberConfig
from .lion_user import UserConfig
from .hooks import HookedChannel

logger = logging.getLogger(__name__)


class keydefaultdict(defaultdict):
    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        else:
            ret = self[key] = self.default_factory(key)
            return ret


class CoreCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = CoreData()
        bot.db.load_registry(self.data)
        self.lions = Lions(bot, self.data)

        self.app_config: Optional[CoreData.AppConfig] = None
        self.bot_config: Optional[CoreData.BotConfig] = None
        self.shard_data: Optional[CoreData.Shard] = None

        # Some global setting registries
        # Do not use these for direct setting access
        # Instead, import the setting directly or use the cog API
        self.bot_setting_groups: list[SettingGroup] = []
        self.guild_setting_groups: list[SettingGroup] = []
        self.user_setting_groups: list[SettingGroup] = []

        # Some ModelSetting registries
        # These are for more convenient direct access
        self.guild_config = GuildConfig
        self.user_config = UserConfig
        self.member_config = MemberConfig

        self.app_cmd_cache: list[discord.app_commands.AppCommand] = []
        self.cmd_name_cache: dict[str, discord.app_commands.AppCommand] = {}
        self.mention_cache: dict[str, str] = keydefaultdict(self.mention_cmd)
        self.hook_cache: WeakValueDictionary[int, HookedChannel] = WeakValueDictionary()

    async def cog_load(self):
        # Fetch (and possibly create) core data rows.
        self.app_config = await self.data.AppConfig.fetch_or_create(appname)
        self.bot_config = await self.data.BotConfig.fetch_or_create(appname)
        self.shard_data = await self.data.Shard.fetch_or_create(
            shardname,
            appname=appname,
            shard_id=self.bot.shard_id,
            shard_count=self.bot.shard_count
        )
        self.bot.add_listener(self.shard_update_guilds, name='on_guild_join')
        self.bot.add_listener(self.shard_update_guilds, name='on_guild_remove')

        await self.bot.add_cog(self.lions)

        # Load the app command cache
        await self.reload_appcmd_cache()

    async def reload_appcmd_cache(self):
        for guildid in self.bot.testing_guilds:
            self.app_cmd_cache += await self.bot.tree.fetch_commands(guild=discord.Object(guildid))
        self.app_cmd_cache += await self.bot.tree.fetch_commands()
        self.cmd_name_cache = {cmd.name: cmd for cmd in self.app_cmd_cache}
        self.mention_cache = self._mention_cache_from(self.app_cmd_cache)

    def _mention_cache_from(self, cmds: list[appcmd.AppCommand | appcmd.AppCommandGroup]):
        cache = keydefaultdict(self.mention_cmd)
        for cmd in cmds:
            cache[cmd.qualified_name if isinstance(cmd, appcmd.AppCommandGroup) else cmd.name] = cmd.mention
            subcommands = [option for option in cmd.options if isinstance(option, appcmd.AppCommandGroup)]
            if subcommands:
                subcache = self._mention_cache_from(subcommands)
                cache |= subcache
        return cache

    def mention_cmd(self, name: str):
        """
        Create an application command mention for the given names.

        If not found in cache, creates a 'fake' mention with an invalid id.
        """
        if name in self.mention_cache:
            mention = self.mention_cache[name]
        else:
            mention = f"</{name}:1110834049204891730>"
        return mention

    def hooked_channel(self, channelid: int):
        if (hooked := self.hook_cache.get(channelid, None)) is None:
            hooked = HookedChannel(self.bot, channelid)
            self.hook_cache[channelid] = hooked
        return hooked

    async def cog_unload(self):
        await self.bot.remove_cog(self.lions.qualified_name)
        self.bot.remove_listener(self.shard_update_guilds, name='on_guild_join')
        self.bot.remove_listener(self.shard_update_guilds, name='on_guild_leave')
        self.bot.core = None

    @LionCog.listener('on_ready')
    @log_wrap(action='Touch shard data')
    async def touch_shard_data(self):
        # Update the last login and guild count for this shard
        await self.shard_data.update(last_login=utc_now(), guild_count=len(self.bot.guilds))

    @log_wrap(action='Update shard guilds')
    async def shard_update_guilds(self, guild):
        await self.shard_data.update(guild_count=len(self.bot.guilds))

    @LionCog.listener('on_ping')
    async def handle_ping(self, *args, **kwargs):
        logger.info(f"Received ping with args {args}, kwargs {kwargs}")

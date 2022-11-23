from typing import Optional

import discord

from meta import LionBot, LionCog, LionContext
from meta.app import shardname, appname
from meta.logger import log_wrap
from utils.lib import utc_now

from settings.groups import SettingGroup

from .data import CoreData
from .lion import Lions
from .guild_settings import GuildSettings
from .user_settings import UserSettings


class CoreCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = CoreData()
        bot.db.load_registry(self.data)
        self.lions = Lions(bot)

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
        self.guild_settings = GuildSettings
        self.user_settings = UserSettings

        self.app_cmd_cache: list[discord.app_commands.AppCommand] = []
        self.cmd_name_cache: dict[str, discord.app_commands.AppCommand] = {}

    async def bot_check_once(self, ctx: LionContext):  # type: ignore
        lion = await self.lions.fetch(ctx.guild.id if ctx.guild else 0, ctx.author.id)
        if ctx.guild:
            await lion.touch_discord_models(ctx.author)  # type: ignore  # Type checker doesn't recognise guard
        ctx.alion = lion
        return True

    async def cog_load(self):
        # Fetch (and possibly create) core data rows.
        conn = await self.bot.db.get_connection()
        async with conn.transaction():
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

        self.bot.core = self
        await self.bot.add_cog(self.lions)

        # Load the app command cache
        for guildid in self.bot.testing_guilds:
            self.app_cmd_cache += await self.bot.tree.fetch_commands(guild=discord.Object(guildid))
        self.app_cmd_cache += await self.bot.tree.fetch_commands()
        self.cmd_name_cache = {cmd.name: cmd for cmd in self.app_cmd_cache}

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

from typing import List, Optional, Dict

import discord
from discord.ext import commands
from aiohttp import ClientSession

from data import Database

from .config import Conf


class LionBot(commands.Bot):
    def __init__(
        self,
        *args,
        appname: str,
        db: Database,
        config: Conf,
        initial_extensions: List[str],
        web_client: ClientSession,
        app_ipc,
        testing_guilds: List[int] = [],
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.web_client = web_client
        self.testing_guilds = testing_guilds
        self.initial_extensions = initial_extensions
        self.db = db
        self.appname = appname
#        self.appdata = appdata
        self.config = config
        self.app_ipc = app_ipc

    async def setup_hook(self) -> None:
        await self.app_ipc.connect()

        for extension in self.initial_extensions:
            await self.load_extension(extension)

        for guildid in self.testing_guilds:
            guild = discord.Object(guildid)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

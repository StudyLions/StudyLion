import discord
from discord import app_commands as appcmds
from discord.ext import commands as cmds

from meta import LionBot, LionContext, LionCog

from . import babel

_p = babel._p


class ConfigCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

    async def cog_load(self):
        ...

    async def cog_unload(self):
        ...

    @cmds.hybrid_group(
        name=_p('group:configure', "configure"),
    )
    @appcmds.guild_only
    async def configure_group(self, ctx: LionContext):
        """
        Bare command group, has no function.
        """
        return

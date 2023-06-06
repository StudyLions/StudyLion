from discord import app_commands as appcmds
from discord.ext import commands as cmds

from meta import LionBot, LionContext, LionCog
from babel.translator import LocalBabel

babel = LocalBabel('core_config')

_p = babel._p


class ConfigCog(LionCog):
    """
    Core guild config cog.

    Primarily used to expose the `configure` base command group at a high level.
    """
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
    @appcmds.default_permissions(manage_guild=True)
    async def configure_group(self, ctx: LionContext):
        """
        Bare command group, has no function.
        """
        return

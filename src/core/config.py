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
        name=_p('group:config', "config"),
        description=_p('group:config|desc', "View and adjust moderation-level configuration."),
    )
    @appcmds.guild_only
    @appcmds.default_permissions(manage_guild=True)
    async def config_group(self, ctx: LionContext):
        """
        Bare command group, has no function.
        """
        return

    @cmds.hybrid_group(
        name=_p('group:admin', "admin"),
        description=_p('group:admin|desc', "Administrative commands."),
    )
    @appcmds.guild_only
    @appcmds.default_permissions(administrator=True)
    async def admin_group(self, ctx: LionContext):
        """
        Bare command group, has no function.
        """
        return

    @admin_group.group(
        name=_p('group:admin_config', "config"),
        description=_p('group:admin_config|desc', "View and adjust admin-level configuration."),
    )
    @appcmds.guild_only
    async def admin_config_group(self, ctx: LionContext):
        """
        Bare command group, has no function.
        """
        return

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
    # --- AI-MODIFIED (2026-06-01) ---
    # Removed the Discord-level default_permissions(manage_guild=True) on the /config group.
    # Discord enforces default_permissions BEFORE the interaction reaches the bot, so a guild
    # whose configured mod_role lacks Discord's "Manage Server" permission could not see or use
    # /config at all -- even though this group is moderation-level config and its subcommands are
    # gated by low_management_ward (which DOES honor the configured mod_role). This was the cause
    # of support bug #0106 (Medecins de Demain: mod role could not use mod commands).
    # The per-subcommand low_management_ward / high_management_ward remains the real gate.
    # Trade-off: the /config group is now visible to all members; non-mods that try a subcommand
    # get a clear "you need the mod role / Manage Server" ward error instead of the command being
    # silently hidden.
    # Original line (commented out for rollback):
    # @appcmds.default_permissions(manage_guild=True)
    # --- END AI-MODIFIED ---
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

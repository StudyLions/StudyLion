import discord
from discord import app_commands as appcmds
from discord.ext import commands as cmds

from meta import LionBot, LionContext, LionCog
from wards import low_management_ward

from . import babel
from .dashboard import GuildDashboard
from .settings import GeneralSettings
from .settingui import GeneralSettingUI

_p = babel._p


class GuildConfigCog(LionCog):
    depends = {'CoreCog'}

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.settings = GeneralSettings()

    async def cog_load(self):
        self.bot.core.guild_config.register_model_setting(GeneralSettings.Timezone)
        self.bot.core.guild_config.register_model_setting(GeneralSettings.Eventlog)

        configcog = self.bot.get_cog('ConfigCog')
        if configcog is None:
            raise ValueError("Cannot load GuildConfigCog without ConfigCog")
        self.crossload_group(self.configure_group, configcog.configure_group)

    @cmds.hybrid_command(
        name="dashboard",
        description="At-a-glance view of the server's configuration."
    )
    @appcmds.guild_only
    @appcmds.default_permissions(manage_guild=True)
    async def dashboard_cmd(self, ctx: LionContext):
        ui = GuildDashboard(self.bot, ctx.guild, ctx.author.id, ctx.channel.id)
        await ui.run(ctx.interaction)
        await ui.wait()

    @cmds.hybrid_group("configure", with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        # Placeholder configure group command.
        ...

    @configure_group.command(
        name=_p('cmd:configure_general', "general"),
        description=_p('cmd:configure_general|desc', "General configuration panel")
    )
    @appcmds.rename(
        timezone=GeneralSettings.Timezone._display_name,
        event_log=GeneralSettings.EventLog._display_name,
    )
    @appcmds.describe(
        timezone=GeneralSettings.Timezone._desc,
        event_log=GeneralSettings.EventLog._display_name,
    )
    @appcmds.guild_only()
    @appcmds.default_permissions(manage_guild=True)
    @low_management_ward
    async def cmd_configure_general(self, ctx: LionContext,
                                    timezone: Optional[str] = None,
                                    event_log: Optional[discord.TextChannel] = None,
                                    ):
        t = self.bot.translator.t

        # Typechecker guards because they don't understand the check ward
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        await ctx.interaction.response.defer(thinking=True)

    # ----- Configuration -----
    @LionCog.placeholder_group
    @cmds.hybrid_group("configure", with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        # Placeholder configure group command.
        ...

    @configure_group.command(
        name=_p('cmd:configure_general', "general"),
        description=_p('cmd:configure_general|desc', "General configuration panel")
    )
    @appcmds.rename(
        timezone=GeneralSettings.Timezone._display_name,
        event_log=GeneralSettings.EventLog._display_name,
    )
    @appcmds.describe(
        timezone=GeneralSettings.Timezone._desc,
        event_log=GeneralSettings.EventLog._display_name,
    )
    @appcmds.guild_only()
    @appcmds.default_permissions(manage_guild=True)
    @low_management_ward
    async def cmd_configure_general(self, ctx: LionContext,
                                    timezone: Optional[str] = None,
                                    event_log: Optional[discord.TextChannel] = None,
                                    ):
        t = self.bot.translator.t

        # Typechecker guards because they don't understand the check ward
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        await ctx.interaction.response.defer(thinking=True)
        # TODO

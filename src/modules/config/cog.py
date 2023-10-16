from typing import Optional

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
        self.bot.core.guild_config.register_model_setting(GeneralSettings.EventLog)

        configcog = self.bot.get_cog('ConfigCog')
        if configcog is None:
            raise ValueError("Cannot load GuildConfigCog without ConfigCog")
        self.crossload_group(self.configure_group, configcog.config_group)

    @cmds.hybrid_command(
        name="dashboard",
        description="At-a-glance view of the server's configuration."
    )
    @appcmds.guild_only
    @low_management_ward
    async def dashboard_cmd(self, ctx: LionContext):
        if not ctx.guild or not ctx.interaction:
            return

        ui = GuildDashboard(self.bot, ctx.guild, ctx.author.id, ctx.channel.id)
        await ui.run(ctx.interaction)
        await ui.wait()

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
        event_log=GeneralSettings.EventLog._desc,
    )
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

        modified = []

        if timezone is not None:
            setting = self.settings.Timezone
            instance = await setting.from_string(ctx.guild.id, timezone)
            modified.append(instance)

        if event_log is not None:
            setting = self.settings.EventLog
            instance = await setting.from_value(ctx.guild.id, event_log)
            modified.append(instance)

        if modified:
            ack_lines = []
            for instance in modified:
                await instance.write()
                ack_lines.append(instance.update_message)

            tick = self.bot.config.emojis.tick
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description='\n'.join(f"{tick} {line}" for line in ack_lines)
            )
            await ctx.reply(embed=embed)

        if ctx.channel.id not in GeneralSettingUI._listening or not modified:
            ui = GeneralSettingUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()


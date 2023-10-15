"""
Lion Module providing the "General" guild settings.

Also provides a placeholder place to put guild settings before migrating to their correct modules.
"""
from typing import Optional
import datetime as dt

import pytz
import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from meta import LionBot, LionCog, LionContext, ctx_bot
from meta.errors import UserInputError
from wards import low_management_ward
from settings import ModelData
from settings.setting_types import TimezoneSetting
from settings.groups import SettingGroup

from core.data import CoreData
from babel.translator import ctx_translator

from . import babel

_p = babel._p


class GeneralSettingsCog(LionCog):
    depends = {'CoreCog'}

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.settings = GeneralSettings()

    async def cog_load(self):
        self.bot.core.guild_config.register_model_setting(GeneralSettings.Timezone)

        configcog = self.bot.get_cog('ConfigCog')
        if configcog is None:
            # TODO: Critical logging error
            ...
        self.crossload_group(self.configure_group, configcog.configure_group)

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

        updated = []  # Possibly empty list of setting instances which were updated, with new data stored
        error_embed = None

        if timezone is not None:
            try:
                timezone_setting = await self.settings.Timezone.from_string(ctx.guild.id, timezone)
                updated.append(timezone_setting)
            except UserInputError as err:
                error_embed = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'cmd:configure_general|parse_failure:timezone',
                        "Could not set the timezone!"
                    )),
                    description=err.msg
                )

        if error_embed is not None:
            # User requested configuration updated, but we couldn't parse input
            await ctx.reply(embed=error_embed)
        elif updated:
            # Save requested configuration updates
            results = []  # List of "success" update responses for each updated setting
            for to_update in updated:
                # TODO: Again need a better way of batch writing
                # Especially since most of these are on one model...
                await to_update.write()
                results.append(to_update.update_message)
            # Post aggregated success message
            success_embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'cmd:configure_general|success',
                    "Settings Updated!"
                )),
            description='\n'.join(
                f"{self.bot.config.emojis.tick} {line}" for line in results
            )
        )
        await ctx.reply(embed=success_embed)
        # TODO: Trigger configuration panel update if listening UI.
    else:
        # Show general configuration panel UI
        # TODO Interactive UI
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=t(_p(
                'cmd:configure_general|panel|title',
                "General Configuration Panel"
            ))
        )
        embed.add_field(
            **ctx.lguild.config.timezone.embed_field
        )
        await ctx.reply(embed=embed)

    cmd_configure_general.autocomplete('timezone')(TimezoneSetting.parse_acmpl)

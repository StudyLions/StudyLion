from typing import Optional
import datetime as dt

import pytz
import discord
from discord import app_commands as appcmds
from discord.ext import commands as cmds

from settings.data import ModelData
from settings.groups import SettingGroup
from settings.setting_types import TimezoneSetting

from meta import LionBot, LionContext, LionCog
from meta.errors import UserInputError
from babel.translator import ctx_translator

from core.data import CoreData

from . import babel, logger

_p = babel._p


class UserConfigSettings(SettingGroup):
    class Timezone(ModelData, TimezoneSetting):
        """
        User timezone configuration.

        Exposed via `/set timezone` (for now).
        When set, this setting controls the display timezone for all personal statistics,
        and several other components such as reminder times.
        """
        setting_id = 'timezone'

        _display_name = _p('userset:timezone', "timezone")
        _desc = _p(
            'userset:timezone|desc',
            "Timezone in which to display statistics."
        )
        _long_desc = _p(
            'userset:timezone|long_desc',
            "All personal time-related features of StudyLion will use this timezone for you, "
            "including personal statistics. "
            "Note that leaderboards will still be shown in the server's own timezone."
        )
        _default = 'UTC'

        _model = CoreData.User
        _column = CoreData.User.timezone.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            return t(_p(
                'userset:timezone|response',
                "Your personal timezone has been set to `{timezone}`."
            )).format(timezone=self.data)


class UserConfigCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.settings = UserConfigSettings()

    async def cog_load(self):
        self.bot.core.user_config.register_model_setting(self.settings.Timezone)

    async def cog_unload(self):
        ...

    @cmds.hybrid_command(
        name=_p('cmd:set', "set"),
        description=_p('cmd:set|desc', "Your personal settings. Configure how I interact with you.")
    )
    @appcmds.rename(
        timezone=UserConfigSettings.Timezone._display_name
    )
    @appcmds.describe(
        timezone=UserConfigSettings.Timezone._desc
    )
    async def set_cmd(self, ctx: LionContext, timezone: Optional[str] = None):
        """
        Configuration interface for the user's timezone.
        """
        # TODO: Cohesive configuration panel for set
        t = self.bot.translator.t

        if not ctx.interaction:
            return
        await ctx.interaction.response.defer(thinking=True)

        updated = []
        error_embed = None

        if timezone is not None:
            # TODO: Add None/unsetting support to timezone
            try:
                timezone_setting = await self.settings.Timezone.from_string(ctx.author.id, timezone)
                updated.append(timezone_setting)
            except UserInputError as err:
                # Handle UserInputError from timezone parsing
                error_embed = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'cmd:set|parse_failure:timezone',
                        "Could not set your timezone!"
                    )),
                    description=err.msg
                )

        if error_embed is not None:
            # Could not parse requested configuration update
            await ctx.reply(embed=error_embed)
        elif updated:
            # Update requested configuration
            lines = []
            for to_update in updated:
                await to_update.write()
                response = to_update.update_message
                lines.append(f"{self.bot.config.emojis.tick} {response}")
            success_embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description='\n'.join(lines)
            )
            await ctx.reply(embed=success_embed)
            # TODO update listening panel UI
        else:
            # Show the user's configuration panel
            # TODO: Interactive UI panel
            panel_embed = discord.Embed(
                colour=discord.Colour.orange(),
                title=t(_p(
                    'cmd:set|embed:panel|title',
                    "Your StudyLion settings"
                ))
            )
            panel_embed.add_field(**ctx.luser.config.timezone.embed_field)
            await ctx.reply(embed=panel_embed)

    @set_cmd.autocomplete('timezone')
    async def set_cmd_acmpl_timezone(self, interaction: discord.Interaction, partial: str):
        """
        Autocomplete timezone options.

        Each option is formatted as timezone (current time).
        Partial text is matched directly by case-insensitive substring.
        """
        # TODO: To be refactored to Timezone setting
        t = self.bot.translator.t

        timezones = pytz.all_timezones
        matching = [tz for tz in timezones if partial.strip().lower() in tz.lower()][:25]
        if not matching:
            choices = [
                appcmds.Choice(
                    name=t(_p(
                        'cmd:set|acmpl:timezone|no_matching',
                        "No timezones matching '{input}'!"
                    )).format(input=partial),
                    value=partial
                )
            ]
        else:
            choices = []
            for tz in matching:
                timezone = pytz.timezone(tz)
                now = dt.datetime.now(timezone)
                nowstr = now.strftime("%H:%M")
                name = t(_p(
                    'cmd:set|acmpl:timezone|choice',
                    "{tz} (Currently {now})"
                )).format(tz=tz, now=nowstr)
                choice = appcmds.Choice(
                    name=name,
                    value=tz
                )
                choices.append(choice)
        return choices

    @cmds.hybrid_group(
        name=_p('cmd:userconfig', "my"),
        description=_p('cmd:userconfig|desc', "User configuration commands.")
    )
    async def userconfig_group(self, ctx: LionContext):
        # Group base command, no function.
        pass

from typing import Optional
import datetime as dt

import pytz
import discord
from discord import app_commands as appcmds
from discord.ext import commands as cmds
from discord.ui.button import ButtonStyle

from settings.data import ModelData
from settings.groups import SettingGroup
from settings.setting_types import TimezoneSetting

from meta import LionBot, LionContext, LionCog
from meta.errors import UserInputError
from utils.ui import AButton, AsComponents
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
        _set_cmd = 'my timezone'

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
        _default = None

        _model = CoreData.User
        _column = CoreData.User.timezone.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self._data:
                return t(_p(
                    'userset:timezone|response:set',
                    "Your personal timezone has been set to `{timezone}`."
                )).format(timezone=self.data)
            else:
                return t(_p(
                    'userset:timezone|response:unset',
                    "You have unset your timezone. Statistics will be displayed in the server timezone."
                ))


class UserConfigCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.settings = UserConfigSettings()

    async def cog_load(self):
        self.bot.core.user_config.register_model_setting(self.settings.Timezone)

    async def cog_unload(self):
        ...

    @cmds.hybrid_group(
        name=_p('cmd:userconfig', "my"),
        description=_p('cmd:userconfig|desc', "User configuration commands.")
    )
    async def userconfig_group(self, ctx: LionContext):
        # Group base command, no function.
        pass

    @userconfig_group.command(
        name=_p('cmd:userconfig_timezone', "timezone"),
        description=_p(
            'cmd:userconfig_timezone|desc',
            "Set your personal timezone, used for displaying stats and setting reminders."
        )
    )
    @appcmds.rename(
        timezone=_p('cmd:userconfig_timezone|param:timezone', "timezone")
    )
    @appcmds.describe(
        timezone=_p(
            'cmd:userconfig_timezone|param:timezone|desc',
            "What timezone are you in? Try typing your country or continent."
        )
    )
    async def userconfig_timezone_cmd(self, ctx: LionContext, timezone: Optional[str] = None):
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        setting = ctx.luser.config.get(UserConfigSettings.Timezone.setting_id)
        if timezone:
            new_data = await setting._parse_string(ctx.author.id, timezone)
            await setting.interactive_set(new_data, ctx.interaction, ephemeral=True)
        else:
            if setting.value:
                desc = t(_p(
                    'cmd:userconfig_timezone|response:set',
                    "Your timezone is currently set to {timezone}"
                )).format(timezone=setting.formatted)

                @AButton(
                    label=t(_p('cmd:userconfig_timezone|button:reset|label', "Reset")),
                    style=ButtonStyle.red
                )
                async def reset_button(_press: discord.Interaction, pressed):
                    await _press.response.defer()
                    await setting.interactive_set(None, ctx.interaction, view=None)

                view = AsComponents(reset_button)
            else:
                guild_tz = ctx.lguild.config.get('timezone').value if ctx.guild else 'UTC'
                desc = t(_p(
                    'cmd:userconfig_timezone|response:unset',
                    "Your timezone is not set. Using the server timezone `{timezone}`."
                )).format(timezone=guild_tz)
                view = None
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                description=desc
            )
            await ctx.reply(embed=embed, ephemeral=True, view=view)

    userconfig_timezone_cmd.autocomplete('timezone')(TimezoneSetting.parse_acmpl)

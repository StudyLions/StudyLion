"""
Babel Cog.

Calculates and sets current locale before command runs (via check_once).
Also defines the relevant guild and user settings for localisation.
"""
from typing import Optional
import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.ui.button import ButtonStyle

from meta import LionBot, LionCog, LionContext
from meta.errors import UserInputError
from utils.ui import AButton, AsComponents
from wards import low_management_ward

from .translator import ctx_locale, ctx_translator, SOURCE_LOCALE
from . import babel
from .enums import locale_names
from .settings import LocaleSettings
from .settingui import LocaleSettingUI

_ = babel._
_p = babel._p


class BabelCog(LionCog):
    depends = {'CoreCog'}

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.settings = LocaleSettings()
        self.t = self.bot.translator.t

    async def cog_load(self):
        if not self.bot.core:
            raise ValueError("CoreCog must be loaded first!")
        self.bot.core.guild_config.register_model_setting(LocaleSettings.ForceLocale)
        self.bot.core.guild_config.register_model_setting(LocaleSettings.GuildLocale)
        self.bot.core.user_config.register_model_setting(LocaleSettings.UserLocale)

        configcog = self.bot.get_cog('ConfigCog')
        self.crossload_group(self.configure_group, configcog.config_group)

        userconfigcog = self.bot.get_cog('UserConfigCog')
        self.crossload_group(self.userconfig_group, userconfigcog.userconfig_group)

    async def cog_unload(self):
        pass

    async def get_user_locale(self, userid):
        """
        Fetch the best locale we can guess for this userid.
        """
        data = await self.bot.core.data.User.fetch(userid)
        if data:
            return data.locale or data.locale_hint or SOURCE_LOCALE
        else:
            return SOURCE_LOCALE

    async def bot_check_once(self, ctx: LionContext):  # type: ignore  # Type checker doesn't understand coro checks
        """
        Calculate and inject the current locale before the command begins.

        Locale resolution is calculated as follows:
            If the guild has force_locale enabled, and a locale set,
            then the guild's locale will be used.

            Otherwise, the priority is
            user_locale -> command_locale -> user_locale_hint -> guild_locale -> default_locale
        """
        locale = None
        if ctx.guild:
            forced = ctx.lguild.config.get('force_locale').value
            guild_locale = ctx.lguild.config.get('guild_locale').value
            if forced:
                locale = guild_locale

        locale = locale or ctx.luser.config.get('user_locale').value
        if ctx.interaction:
            locale = locale or ctx.interaction.locale.value
        if ctx.guild:
            locale = locale or guild_locale

        locale = locale or SOURCE_LOCALE

        ctx_locale.set(locale)
        ctx_translator.set(self.bot.translator)
        return True

    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        # Placeholder group method, not used.
        pass

    @configure_group.command(
        name=_p('cmd:configure_language', "language"),
        description=_p('cmd:configure_language|desc',
                       "Configure the default language I will use in this server.")
    )
    @appcmds.choices(
        force_language=[
            appcmds.Choice(name=LocaleSettings.ForceLocale._outputs[True], value=1),
            appcmds.Choice(name=LocaleSettings.ForceLocale._outputs[False], value=0),
        ]
    )
    @appcmds.describe(
        language=LocaleSettings.GuildLocale._desc,
        force_language=LocaleSettings.ForceLocale._desc
    )
    @appcmds.rename(
        language=LocaleSettings.GuildLocale._display_name,
        force_language=LocaleSettings.ForceLocale._display_name
    )
    @low_management_ward
    async def cmd_configure_language(self, ctx: LionContext,
                                     language: Optional[str] = None,
                                     force_language: Optional[appcmds.Choice[int]] = None):
        if not ctx.interaction:
            # This command is not available as a text command
            return
        if not ctx.guild:
            # This is impossible by decorators, but adding this guard for the type checker
            return
        t = self.t
        # TODO: Setting group, and group setting widget
        # We can attach the command to the setting group as an application command
        # Then load it into the configure command group dynamically

        lang_setting = await self.settings.GuildLocale.get(ctx.guild.id)
        force_setting = await self.settings.ForceLocale.get(ctx.guild.id)

        if language:
            lang_data = await lang_setting._parse_string(ctx.guild.id, language)
        if force_language is not None:
            force_data = bool(force_language.value)

        if force_language is not None and not (lang_data if language is not None else lang_setting.value):
            # Setting force without having a language!
            raise UserInputError(
                t(_p(
                    'cmd:configure_language|error',
                    "You cannot enable `{force_setting}` without having a configured language!"
                )).format(force_setting=t(LocaleSettings.ForceLocale._display_name))
            )
        # TODO: Really need simultaneous model writes, or batched writes
        lines = []
        if language:
            lang_setting.data = lang_data
            await lang_setting.write()
            lines.append(lang_setting.update_message)
        if force_language is not None:
            force_setting.data = force_data
            await force_setting.write()
            lines.append(force_setting.update_message)
        if lines:
            result = '\n'.join(
                f"{self.bot.config.emojis.tick} {line}" for line in lines
            )
            await ctx.reply(
                embed=discord.Embed(
                    colour=discord.Colour.green(),
                    title=t(_p('cmd:configure_language|success', "Language settings updated!")),
                    description=result
                )
            )

        if ctx.channel.id not in LocaleSettingUI._listening or not lines:
            ui = LocaleSettingUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()

    @LionCog.placeholder_group
    @cmds.hybrid_group(name='my')
    async def userconfig_group(self, ctx: LionContext):
        pass

    @userconfig_group.command(
        name=_p('cmd:userconfig_language', "language"),
        description=_p(
            'cmd:userconfig_language|desc',
            "Set your preferred interaction language."
        )
    )
    @appcmds.rename(
        language=_p('cmd:userconfig_language|param:language', "language")
    )
    @appcmds.describe(
        language=_p(
            'cmd:userconfig_language|param:language|desc',
            "Which language do you want me to respond in?"
        )
    )
    async def userconfig_language_cmd(self, ctx: LionContext, language: Optional[str] = None):
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        setting = await self.settings.UserLocale.get(ctx.author.id)
        if language:
            new_data = await setting._parse_string(ctx.author.id, language)
            await setting.interactive_set(new_data, ctx.interaction, ephemeral=True)
        else:
            embed = setting.embed
            if setting.value:
                @AButton(
                    label=t(_p('cmd:userconfig_language|button:reset|label', "Reset")),
                    style=ButtonStyle.red
                )
                async def reset_button(_press: discord.Interaction, pressed):
                    await _press.response.defer()
                    await setting.interactive_set(None, ctx.interaction, view=None)

                view = AsComponents(reset_button)
            else:
                view = None
            await ctx.reply(embed=embed, ephemeral=True, view=view)

    @userconfig_language_cmd.autocomplete('language')
    @cmd_configure_language.autocomplete('language')
    async def acmpl_language(self, interaction: discord.Interaction, partial: str):
        """
        Shared autocomplete for language options.
        """
        t = self.bot.translator.t
        supported = self.bot.translator.supported_locales
        formatted = []
        for locale in supported:
            names = locale_names.get(locale.replace('_', '-'), None)
            if names:
                local_name, native_name = names
                localestr = f"{native_name} ({t(local_name)})"
            else:
                localestr = locale
            formatted.append((locale, localestr))

        matching = {item for item in formatted if partial in item[1] or partial in item[0]}
        if matching:
            choices = [
                appcmds.Choice(name=localestr[:100], value=locale)
                for locale, localestr in matching
            ]
        else:
            choices = [
                appcmds.Choice(
                    name=t(_p(
                        'acmpl:language|no_match',
                        "No supported languages matching {partial}"
                )).format(partial=partial)[:100],
                    value=partial
                )
            ]
        return choices

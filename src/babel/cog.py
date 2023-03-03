"""
Babel Cog.

Calculates and sets current locale before command runs (via check_once).
Also defines the relevant guild and user settings for localisation.
"""
from typing import Optional
import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from meta import LionBot, LionCog, LionContext
from meta.errors import UserInputError

from settings import ModelData
from settings.setting_types import StringSetting, BoolSetting
from settings.groups import SettingGroup

from core.data import CoreData

from .translator import ctx_locale, ctx_translator, LocalBabel, SOURCE_LOCALE
from . import babel

_ = babel._
_p = babel._p


class LocaleSettings(SettingGroup):
    class UserLocale(ModelData, StringSetting):
        """
        User-configured locale.

        Exposed via dedicated setting command.
        """
        setting_id = 'user_locale'

        display_name = _p('userset:locale', 'language')
        desc = _p('userset:locale|desc', "Your preferred language for interacting with me.")

        _model = CoreData.User
        _column = CoreData.User.locale.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data is None:
                return t(_p('userset:locale|response', "You have unset your language."))
            else:
                return t(_p('userset:locale|response', "You have set your language to `{lang}`.")).format(
                    lang=self.data
                )

        @classmethod
        async def _parse_string(cls, parent_id, string, **kwargs):
            translator = ctx_translator.get()
            if string not in translator.supported_locales:
                lang = string[:20]
                raise UserInputError(
                    translator.t(
                        _p('userset:locale|error', "Sorry, we do not support the `{lang}` language at this time!")
                    ).format(lang=lang)
                )
            return string

    class ForceLocale(ModelData, BoolSetting):
        """
        Guild configuration for whether to force usage of the guild locale.

        Exposed via `/configure language` command and standard configuration interface.
        """
        setting_id = 'force_locale'

        display_name = _p('guildset:force_locale', 'force_language')
        desc = _p('guildset:force_locale|desc',
                  "Whether to force all members to use the configured guild language when interacting with me.")
        long_desc = _p(
            'guildset:force_locale|long_desc',
            "When enabled, commands in this guild will always use the configured guild language, "
            "regardless of the member's personally configured language."
        )
        _outputs = {
            True: _p('guildset:force_locale|output', 'Enabled (members will be forced to use the server language)'),
            False: _p('guildset:force_locale|output', 'Disabled (members may set their own language)'),
            None: 'Not Set'  # This should be impossible, since we have a default
        }
        _default = False

        _model = CoreData.Guild
        _column = CoreData.Guild.force_locale.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data:
                return t(_p(
                    'guildset:force_locale|response',
                    "I will always use the set language in this server."
                ))
            else:
                return t(_p(
                    'guildset:force_locale|response',
                    "I will now allow the members to set their own language here."
                ))

    class GuildLocale(ModelData, StringSetting):
        """
        Guild-configured locale.

        Exposed via `/configure language` command, and standard configuration interface.
        """
        setting_id = 'guild_locale'

        display_name = _p('guildset:locale', 'language')
        desc = _p('guildset:locale|desc', "Your preferred language for interacting with me.")

        _model = CoreData.Guild
        _column = CoreData.Guild.locale.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data is None:
                return t(_p('guildset:locale|response', "You have reset the guild language."))
            else:
                return t(_p('guildset:locale|response', "You have set the guild language to `{lang}`.")).format(
                    lang=self.data
                )

        @classmethod
        async def _parse_string(cls, parent_id, string, **kwargs):
            translator = ctx_translator.get()
            if string not in translator.supported_locales:
                lang = string[:20]
                raise UserInputError(
                    translator.t(
                        _p('guildset:locale|error', "Sorry, we do not support the `{lang}` language at this time!")
                    ).format(lang=lang)
                )
            return string


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

    @cmds.hybrid_command(
        name=LocaleSettings.UserLocale.display_name,
        description=LocaleSettings.UserLocale.desc
    )
    async def cmd_language(self, ctx: LionContext, language: str):
        """
        Dedicated user setting command for the `locale` setting.
        """
        if not ctx.interaction:
            # This command is not available as a text command
            return

        setting = await self.settings.UserLocale.get(ctx.author.id)
        new_data = await setting._parse_string(ctx.author.id, language)
        await setting.interactive_set(new_data, ctx.interaction)

    @cmds.hybrid_command(
        name=_p('cmd:configure_language', "configure_language"),
        description=_p('cmd:configure_language|desc',
                       "Configure the default language I will use in this server.")
    )
    @appcmds.choices(
        force_language=[
            appcmds.Choice(name=LocaleSettings.ForceLocale._outputs[True], value=1),
            appcmds.Choice(name=LocaleSettings.ForceLocale._outputs[False], value=0),
        ]
    )
    @appcmds.guild_only()  # Can be removed when attached as a subcommand
    async def cmd_configure_language(
        self, ctx: LionContext, language: Optional[str] = None, force_language: Optional[appcmds.Choice[int]] = None
    ):
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
            force_data = bool(force_language)

        if force_language is not None and not (lang_data if language is not None else lang_setting.value):
            # Setting force without having a language!
            raise UserInputError(
                t(_p(
                    'cmd:configure_language|error',
                    "You cannot enable `{force_setting}` without having a configured language!"
                )).format(force_setting=t(LocaleSettings.ForceLocale.display_name))
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
        result = '\n'.join(
            f"{self.bot.config.emojis.tick} {line}" for line in lines
        )
        # TODO: Setting group widget
        await ctx.reply(
            embed=discord.Embed(
                colour=discord.Colour.green(),
                title=t(_p('cmd:configure_language|success', "Language settings updated!")),
                description=result
            )
        )

    @cmd_configure_language.autocomplete('language')
    async def cmd_configure_language_acmpl_language(self, interaction: discord.Interaction, partial: str):
        # TODO: More friendly language names
        supported = self.bot.translator.supported_locales
        matching = [lang for lang in supported if partial.lower() in lang]
        t = self.t
        if not matching:
            return [
                appcmds.Choice(
                    name=t(_p(
                        'cmd:configure_language|acmpl:language',
                        "No supported languages matching {partial}"
                    )).format(partial=partial),
                    value='None'
                )
            ]
        else:
            return [
                appcmds.Choice(name=lang, value=lang)
                for lang in matching
            ]

from typing import Optional

from settings import ModelData
from settings.setting_types import StringSetting, BoolSetting
from settings.groups import SettingGroup

from meta.errors import UserInputError
from meta.context import ctx_bot
from core.data import CoreData
from wards import low_management_iward

from .translator import ctx_translator
from . import babel
from .enums import locale_names

_p = babel._p


class LocaleSetting(StringSetting):
    """
    Base class describing a LocaleSetting.
    """
    _accepts = _p(
        'settype:locale|accepts',
        "Enter a supported language (e.g. 'en-GB')."
    )

    def _desc_table(self, show_value: Optional[str] = None) -> list[tuple[str, str]]:
        translator = ctx_translator.get()
        t = translator.t

        lines = super()._desc_table(show_value=show_value)
        lines.append((
            t(_p(
                'settype:locale|summary_table|field:supported|key',
                "Supported"
            )),
            ', '.join(f"`{locale}`" for locale in translator.supported_locales)
        ))
        return lines

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        t = ctx_translator.get().t
        if data is None:
            formatted = t(_p('settype:locale|formatted:unset', "Unset"))
        else:
            if data in locale_names:
                local_name, native_name = locale_names[data]
                formatted = f"`{native_name} ({t(local_name)})`"
            else:
                formatted = f"`{data}`"
        return formatted

    @classmethod
    async def _parse_string(cls, parent_id, string, **kwargs):
        translator = ctx_translator.get()
        if string not in translator.supported_locales:
            lang = string[:20]
            raise UserInputError(
                translator.t(
                    _p('settype:locale|error', "Sorry, we do not support the language `{lang}` at this time!")
                ).format(lang=lang)
            )
        return string


class LocaleSettings(SettingGroup):
    class UserLocale(ModelData, LocaleSetting):
        """
        User-configured locale.

        Exposed via dedicated setting command.
        """
        setting_id = 'user_locale'

        _display_name = _p('userset:locale', 'language')
        _desc = _p('userset:locale|desc', "Your preferred language for interacting with me.")
        _long_desc = _p(
            'userset:locale|long_desc',
            "The language you would prefer me to respond to commands and interactions in. "
            "Servers may be configured to override this with their own language."
        )

        _model = CoreData.User
        _column = CoreData.User.locale.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data is None:
                return t(_p('userset:locale|response', "You have unset your language."))
            else:
                return t(_p('userset:locale|response', "You have set your language to {lang}.")).format(
                    lang=self.formatted
                )

        @property
        def set_str(self):
            bot = ctx_bot.get()
            if bot:
                return bot.core.mention_cmd('my language')

    class ForceLocale(ModelData, BoolSetting):
        """
        Guild configuration for whether to force usage of the guild locale.

        Exposed via `/config language` command and standard configuration interface.
        """
        setting_id = 'force_locale'
        _write_ward = low_management_iward

        _display_name = _p('guildset:force_locale', 'force_language')
        _desc = _p('guildset:force_locale|desc',
                   "Whether to force all members to use the configured guild language when interacting with me.")
        _long_desc = _p(
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

        @property
        def set_str(self):
            bot = ctx_bot.get()
            if bot:
                return bot.core.mention_cmd('config language')

    class GuildLocale(ModelData, LocaleSetting):
        """
        Guild-configured locale.

        Exposed via `/config language` command, and standard configuration interface.
        """
        setting_id = 'guild_locale'
        _write_ward = low_management_iward

        _display_name = _p('guildset:locale', 'language')
        _desc = _p('guildset:locale|desc', "Your preferred language for interacting with me.")
        _long_desc = _p(
            'guildset:locale|long_desc',
            "The default language to use for responses and interactions in this server. "
            "Member's own configured language will override this for their commands "
            "unless `force_language` is enabled."
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.locale.name

        @property
        def update_message(self):
            t = ctx_translator.get().t
            if self.data is None:
                return t(_p('guildset:locale|response', "You have unset the guild language."))
            else:
                return t(_p('guildset:locale|response', "You have set the guild language to {lang}.")).format(
                    lang=self.formatted
                )

        @property
        def set_str(self):
            bot = ctx_bot.get()
            if bot:
                return bot.core.mention_cmd('config language')

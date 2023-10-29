from meta.errors import UserInputError
from settings.data import ModelData
from settings.setting_types import StringSetting
from settings.groups import SettingGroup

from wards import sys_admin_iward
from core.data import CoreData
from gui.base import AppSkin
from babel.translator import ctx_translator

from . import babel

_p = babel._p


class GlobalSkinSettings(SettingGroup):
    class DefaultSkin(ModelData, StringSetting):
        setting_id = 'default_app_skin'
        _event = 'botset_skin'
        _write_ward = sys_admin_iward

        _display_name = _p(
            'botset:default_app_skin', "default_skin"
        )
        _desc = _p(
            'botset:default_app_skin|desc',
            "The skin name of the app skin to use as the global default."
        )
        _long_desc = _p(
            'botset:default_app_skin|long_desc',
            "The skin name, as given in the `skins.json` file,"
            " of the client default interface skin."
            " Guilds and users will be able to apply this skin"
            "regardless of whether it is set as visible in the skin configuration."
        )
        _accepts = _p(
            'botset:default_app_skin|accepts',
            "A valid skin name as given in skins.json"
        )

        _model = CoreData.BotConfig
        _column = CoreData.BotConfig.default_skin.name

        @classmethod
        async def _parse_string(cls, parent_id, string, **kwargs):
            t = ctx_translator.get().t
            if string and not AppSkin.get_skin_path(string):
                raise UserInputError(
                    t(_p(
                        'botset:default_app_skin|parse|error:invalid',
                        "Provided `{string}` is not a valid skin id!"
                    )).format(string=string)
                )
            return string or None


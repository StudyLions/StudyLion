from settings import ModelData
from settings.groups import SettingGroup, ModelConfig, SettingDotDict
from settings.setting_types import (
    RoleSetting, BoolSetting, StringSetting, DurationSetting
)
from core.setting_types import CoinSetting

from .data import RoleMenuData
from . import babel

_p = babel._p


class RoleMenuRoleConfig(ModelConfig):
    settings = SettingDotDict()
    _model_settings = set()
    model = RoleMenuData.RoleMenuRole

    @property
    def role(self):
        return self.get(RoleMenuRoleOptions.Role.setting_id)

    @property
    def label(self):
        return self.get(RoleMenuRoleOptions.Label.setting_id)

    @property
    def emoji(self):
        return self.get(RoleMenuRoleOptions.Emoji.setting_id)

    @property
    def description(self):
        return self.get(RoleMenuRoleOptions.Description.setting_id)

    @property
    def price(self):
        return self.get(RoleMenuRoleOptions.Price.setting_id)

    @property
    def duration(self):
        return self.get(RoleMenuRoleOptions.Duration.setting_id)


class RoleMenuRoleOptions(SettingGroup):
    @RoleMenuRoleConfig.register_model_setting
    class Role(ModelData, RoleSetting):
        setting_id = 'role'

        _display_name = _p('roleset:role', "role")
        _desc = _p(
            'roleset:role|desc',
            "The role associated to this menu item."
        )
        _long_desc = _p(
            'roleset:role|long_desc',
            "The role given when this menu item is selected in the role menu."
        )

        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.roleid.name

    @RoleMenuRoleConfig.register_model_setting
    class Label(ModelData, StringSetting):
        setting_id = 'role'

        _display_name = _p('roleset:label', "label")
        _desc = _p(
            'roleset:label|desc',
            "A short button label for this role."
        )
        _long_desc = _p(
            'roleset:label|long_desc',
            "A short name for this role, to be displayed in button labels, dropdown titles, and some menu layouts. "
            "By default uses the Discord role name."
        )

        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.label.name

    @RoleMenuRoleConfig.register_model_setting
    class Emoji(ModelData, StringSetting):
        setting_id = 'emoji'

        _display_name = _p('roleset:emoji', "emoji")
        _desc = _p(
            'roleset:emoji|desc',
            "The emoji associated with this role."
        )
        _long_desc = _p(
            'roleset:emoji|long_desc',
            "The role emoji is used for the reaction (in reaction role menus), "
            "and otherwise appears next to the role label in the button and dropdown styles. "
            "The emoji is also displayed next to the role in most menu templates."
        )

        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.emoji.name

    @RoleMenuRoleConfig.register_model_setting
    class Description(ModelData, StringSetting):
        setting_id = 'description'

        _display_name = _p('roleset:description', "description")
        _desc = _p(
            'roleset:description|desc',
            "A longer description of this role."
        )
        _long_desc = _p(
            'roleset:description|long_desc',
            "The description is displayed under the role label in dropdown style menus. "
            "It may also be used as a substitution key in custom role selection responses."
        )

        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.description.name

    @RoleMenuRoleConfig.register_model_setting
    class Price(ModelData, CoinSetting):
        setting_id = 'price'

        _display_name = _p('roleset:price', "price")
        _desc = _p(
            'roleset:price|desc',
            "Price of the role, in LionCoins."
        )
        _long_desc = _p(
            'roleset:price|long_desc',
            "How much the role costs when selected, in LionCoins."
        )
        _default = 0
        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.price.name

    @RoleMenuRoleConfig.register_model_setting
    class Duration(ModelData, DurationSetting):
        setting_id = 'duration'

        _display_name = _p('roleset:duration', "duration")
        _desc = _p(
            'roleset:duration|desc',
            "Lifetime of the role after selection"
        )
        _long_desc = _p(
            'roleset:duration|long_desc',
            "Allows creation of 'temporary roles' which expire a given time after being equipped. "
            "Refunds will not be given upon expiry."
        )
        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.duration.name

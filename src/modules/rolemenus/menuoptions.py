from typing import Optional

import discord

from meta.errors import UserInputError
from babel.translator import ctx_translator
from settings import ModelData
from settings.groups import SettingGroup, ModelConfig, SettingDotDict
from settings.setting_types import (
    RoleSetting, BoolSetting, StringSetting, IntegerSetting, DurationSetting
)

from .data import RoleMenuData
from . import babel

_p = babel._p


# TODO: Write some custom accepts fields
# TODO: The *name* might be an important setting!


class RoleMenuConfig(ModelConfig):
    settings = SettingDotDict()
    _model_settings = set()
    model = RoleMenuData.RoleMenu

    @property
    def name(self):
        return self.get(RoleMenuOptions.Name.setting_id)

    @property
    def required_role(self):
        return self.get(RoleMenuOptions.RequiredRole.setting_id)

    @property
    def sticky(self):
        return self.get(RoleMenuOptions.Sticky.setting_id)

    @property
    def refunds(self):
        return self.get(RoleMenuOptions.Refunds.setting_id)

    @property
    def obtainable(self):
        return self.get(RoleMenuOptions.Obtainable.setting_id)


class RoleMenuOptions(SettingGroup):
    @RoleMenuConfig.register_model_setting
    class Name(ModelData, StringSetting):
        setting_id = 'name'

        _display_name = _p('menuset:name', "name")
        _desc = _p(
            'menuset:name|desc',
            "Brief name for this role menu."
        )
        _long_desc = _p(
            'menuset:name|long_desc',
            "The role menu name is displayed when selecting the menu in commands, "
            "and as the title of most default menu layouts."
        )
        _default = 'Untitled'

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.name.name

    @RoleMenuConfig.register_model_setting
    class Sticky(ModelData, BoolSetting):
        setting_id = 'sticky'

        _display_name = _p('menuset:sticky', "sticky_roles")
        _desc = _p(
            'menuset:sticky|desc',
            "Whether the menu can be used to unequip roles."
        )
        _long_desc = _p(
            'menuset:sticky|long_desc',
            "When enabled, members will not be able to remove equipped roles by selecting them in this menu. "
            "Note that when disabled, "
            "members will be able to unequip the menu roles even if they were not obtained from the menu."
        )
        _default = False

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.sticky.name

    @RoleMenuConfig.register_model_setting
    class Refunds(ModelData, BoolSetting):
        setting_id = 'refunds'

        _display_name = _p('menuset:refunds', "refunds")
        _desc = _p(
            'menuset:refunds|desc',
            "Whether removing a role will refund the purchase price for that role."
        )
        _long_desc = _p(
            'menuset:refunds|long_desc',
            "When enabled, members who *purchased a role through this role menu* will obtain a full refund "
            "when they remove the role through the menu.\n"
            "**Refunds will only be given for roles purchased through the same menu.**\n"
            "**The `sticky` option must be disabled to allow members to remove roles.**"
        )
        _default = True

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.refunds.name

    @RoleMenuConfig.register_model_setting
    class Obtainable(ModelData, IntegerSetting):
        setting_id = 'obtainable'

        _display_name = _p('menuset:obtainable', "obtainable")
        _desc = _p(
            'menuset:obtainable|desc',
            "The maximum number of roles equippable from this menu."
        )
        _long_desc = _p(
            'menus:obtainable|long_desc',
            "Members will not be able to obtain more than this number of roles from this menu. "
            "The counts roles that were not obtained through the rolemenu system."
        )
        _default = None

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.obtainable.name

    @RoleMenuConfig.register_model_setting
    class RequiredRole(ModelData, RoleSetting):
        setting_id = 'required_role'

        _display_name = _p('menuset:required_role', "required_role")
        _desc = _p(
            'menuset:required_role|desc',
            "Initial role required to use this menu."
        )
        _long_desc = _p(
            'menuset:required_role|long_desc',
            "If set, only members who have the `required_role` will be able to obtain or remove roles using this menu."
        )
        _default = None

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.required_roleid.name

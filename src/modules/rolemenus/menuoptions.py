from typing import Optional

import discord

from meta.errors import UserInputError
from babel.translator import ctx_translator
from settings import ModelData
from settings.groups import SettingGroup, ModelConfig, SettingDotDict
from settings.setting_types import (
    RoleSetting, BoolSetting, StringSetting, IntegerSetting, DurationSetting
)

from core.setting_types import MessageSetting

from .data import RoleMenuData
from . import babel

_p = babel._p


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

    @property
    def rawmessage(self):
        return self.get(RoleMenuOptions.Message.setting_id)


class RoleMenuOptions(SettingGroup):
    @RoleMenuConfig.register_model_setting
    class Name(ModelData, StringSetting):
        setting_id = 'name'

        _display_name = _p('menuset:name', "name")
        _desc = _p(
            'menuset:name|desc',
            "Brief name for this role menu."
        )
        _accepts = _desc
        _long_desc = _p(
            'menuset:name|long_desc',
            "The role menu name is displayed when selecting the menu in commands, "
            "and as the title of most default menu layouts."
        )
        _default = 'Untitled'

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.name.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            resp = t(_p(
                'menuset:name|set_response',
                "This role menu will now be called **{new_name}**."
            )).format(new_name=value)
            return resp

    @RoleMenuConfig.register_model_setting
    class Sticky(ModelData, BoolSetting):
        setting_id = 'sticky'

        _display_name = _p('menuset:sticky', "sticky_roles")
        _desc = _p(
            'menuset:sticky|desc',
            "Whether the menu can be used to unequip roles."
        )
        _accepts = _desc
        _long_desc = _p(
            'menuset:sticky|long_desc',
            "When enabled, members will not be able to remove equipped roles by selecting them in this menu. "
            "Note that when disabled, "
            "members will be able to unequip the menu roles even if they were not obtained from the menu."
        )
        _default = False

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.sticky.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'menuset:sticky|set_response:true',
                    "Members will no longer be able to remove roles with this menu."
                ))
            else:
                resp = t(_p(
                    'menuset:sticky|set_response:false',
                    "Members will now be able to remove roles with this menu."
                ))
            return resp

    @RoleMenuConfig.register_model_setting
    class Refunds(ModelData, BoolSetting):
        setting_id = 'refunds'

        _display_name = _p('menuset:refunds', "refunds")
        _desc = _p(
            'menuset:refunds|desc',
            "Whether removing a role will refund the purchase price for that role."
        )
        _accepts = _desc
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

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'menuset:refunds|set_response:true',
                    "Members will now be refunded when removing a role with this menu."
                ))
            else:
                resp = t(_p(
                    'menuset:refunds|set_response:false',
                    "Members will no longer be refunded when removing a role with this menu."
                ))
            return resp

    @RoleMenuConfig.register_model_setting
    class Obtainable(ModelData, IntegerSetting):
        setting_id = 'obtainable'

        _display_name = _p('menuset:obtainable', "obtainable")
        _desc = _p(
            'menuset:obtainable|desc',
            "The maximum number of roles equippable from this menu."
        )
        _accepts = _desc
        _long_desc = _p(
            'menuset:obtainable|long_desc',
            "Members will not be able to obtain more than this number of roles from this menu. "
            "This counts roles that were not obtained through the rolemenu system."
        )
        _notset_str = _p(
            'menuset:obtainable|notset',
            "Unlimited."
        )
        _default = None

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.obtainable.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'menuset:obtainable|set_response:set',
                    "Members will be able to select a maximum of **{value}** roles from this menu."
                )).format(value=value)
            else:
                resp = t(_p(
                    'menuset:obtainable|set_response:unset',
                    "Members will be able to select any number of roles from this menu."
                ))
            return resp

    @RoleMenuConfig.register_model_setting
    class RequiredRole(ModelData, RoleSetting):
        setting_id = 'required_role'

        _display_name = _p('menuset:required_role', "required_role")
        _desc = _p(
            'menuset:required_role|desc',
            "Initial role required to use this menu."
        )
        _accepts = _desc
        _long_desc = _p(
            'menuset:required_role|long_desc',
            "If set, only members who have the `required_role` will be able to obtain or remove roles using this menu."
        )
        _default = None

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.required_roleid.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'menuset:required_role|set_response:set',
                    "Members will need to have the {role} role to use this menu."
                )).format(role=self.formatted)
            else:
                resp = t(_p(
                    'menuset:required_role|set_response:unset',
                    "Any member who can see the menu may use it."
                ))
            return resp

    @RoleMenuConfig.register_model_setting
    class Message(ModelData, MessageSetting):
        setting_id = 'message'

        _display_name = _p('menuset:message', "custom_message")
        _desc = _p(
            'menuset:message|desc',
            "Custom message data used to display the menu."
        )
        _long_desc = _p(
            'menuset:message|long_desc',
            "This setting determines the body of the menu message, "
            "including the message content and the message embed(s). "
            "While most easily modifiable through the `Edit Message` button, "
            "raw JSON-formatted message data may also be uploaded via command."
        )
        _default = None

        _model = RoleMenuData.RoleMenu
        _column = RoleMenuData.RoleMenu.rawmessage.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'menuset:message|set_response:set',
                    "The role menu message has been set. Edit through the menu editor."
                )).format(value=value.mention)
            else:
                resp = t(_p(
                    'menuset:message|set_response:unset',
                    "The role menu message has been unset. Select a template through the menu editor."
                ))
            return resp

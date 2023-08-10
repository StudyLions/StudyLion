import discord

from settings import ModelData
from settings.groups import SettingGroup, ModelConfig, SettingDotDict
from settings.setting_types import (
    RoleSetting, BoolSetting, StringSetting, DurationSetting, EmojiSetting
)
from core.setting_types import CoinSetting
from utils.ui import AButton, AsComponents
from meta.errors import UserInputError
from babel.translator import ctx_translator

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

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'roleset:role|set_response:set',
                    "This menu item will now give the role {role}."
                )).format(role=self.formatted)
                return resp

    @RoleMenuRoleConfig.register_model_setting
    class Label(ModelData, StringSetting):
        setting_id = 'label'

        _display_name = _p('roleset:label', "label")
        _desc = _p(
            'roleset:label|desc',
            "A short button label for this role."
        )
        _accepts = _desc
        _long_desc = _p(
            'roleset:label|long_desc',
            "A short name for this role, to be displayed in button labels, dropdown titles, and some menu layouts. "
            "By default uses the Discord role name."
        )

        _quote = False

        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.label.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'roleset:role|set_response',
                "This menu role is now called `{value}`."
            )).format(value=self.data)
            return resp

    @RoleMenuRoleConfig.register_model_setting
    class Emoji(ModelData, EmojiSetting):
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

        @property
        def test_button(self):
            if self.data:
                button = AButton(emoji=self.data)
                button.disabled = True

                @button
                async def emoji_test_callback(press, butt):
                    await press.response.defer()
            else:
                button = None
            return button

        @classmethod
        async def _parse_string(cls, parent_id, string: str, interaction: discord.Interaction = None, **kwargs):
            emojistr = await super()._parse_string(parent_id, string, interaction=interaction, **kwargs)
            if emojistr and interaction is not None:
                # Use the interaction to test
                button = AButton(emoji=emojistr)
                button.disabled = True
                view = AsComponents(button)
                try:
                    await interaction.edit_original_response(
                        content=f"Testing Emoji {emojistr}",
                        view=view,
                    )
                except discord.HTTPException:
                    t = interaction.client.translator.t
                    raise UserInputError(t(_p(
                        'roleset:emoji|error:test_emoji',
                        "The selected emoji `{emoji}` is invalid or has been deleted."
                    )).format(emoji=emojistr))
            return emojistr

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'roleset:emoji|set_response:set',
                    "The menu role emoji is now {emoji}."
                )).format(emoji=self.as_partial)
            else:
                resp = t(_p(
                    'roleset:emoji|set_response:unset',
                    "The menu role emoji has been removed."
                ))
            return resp

    @RoleMenuRoleConfig.register_model_setting
    class Description(ModelData, StringSetting):
        setting_id = 'description'

        _display_name = _p('roleset:description', "description")
        _desc = _p(
            'roleset:description|desc',
            "A longer description of this role."
        )
        _accepts = _desc
        _long_desc = _p(
            'roleset:description|long_desc',
            "The description is displayed under the role label in dropdown style menus. "
            "It may also be used as a substitution key in custom role selection responses."
        )

        _quote = False

        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.description.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'roleset:description|set_response:set',
                    "The role description has been set."
                ))
            else:
                resp = t(_p(
                    'roleset:description|set_response:unset',
                    "The role description has been removed."
                ))
            return resp

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
        _accepts = _p(
            'roleset:price|accepts',
            "Amount of coins that the role costs."
        )
        _default = 0
        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.price.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'roleset:price|set_response:set',
                    "This role will now cost {price} to equip."
                )).format(price=self.formatted)
            else:
                resp = t(_p(
                    'roleset:price|set_response:unset',
                    "This role will now be free to equip from this role menu."
                ))
            return resp

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
        _notset_str = _p(
            'roleset:duration|notset',
            "Forever."
        )

        _model = RoleMenuData.RoleMenuRole
        _column = RoleMenuData.RoleMenuRole.duration.name

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value:
                resp = t(_p(
                    'roleset:duration|set_response:set',
                    "This role will now expire after {duration}."
                )).format(duration=self.formatted)
            else:
                resp = t(_p(
                    'roleset:duration|set_response:unset',
                    "This role will no longer expire after being selected."
                ))
            return resp

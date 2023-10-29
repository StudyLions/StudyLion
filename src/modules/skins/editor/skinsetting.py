from typing import Literal, Optional
from enum import Enum

from discord.ui import TextInput

from meta import LionBot
from meta.errors import UserInputError
from babel.translator import LazyStr
from gui.base import Card, FieldDesc, AppSkin

from .. import babel
from ..skinlib import CustomSkin

_p = babel._p


class SettingInputType(Enum):
    SkinInput = -1
    ModalInput = 0
    MenuInput = 1
    ButtonInput = 2


class Setting:
    """
    An abstract base interface for a custom skin 'setting'.

    A skin setting is considered to be some readable and usually writeable
    information extractable from a `CustomSkin`.
    This will usually consist of the value of one or more properties,
    which are themselves associated to fields of GUI Cards.

    The methods in this ABC describe the interface for such a setting.
    Each method accepts a `CustomSkin`,
    and an implementation should describe how to
    get, set, parse, format, or display the setting
    for that given skin.

    This is very similar to how Settings are implemented in the bot,
    except here all settings have a shared external source of state, the CustomSkin.
    Thus, each setting is simply an instance of an appropriate setting class,
    rather than a class itself.
    """
    
    # What type of input method this setting requires for input
    input_type: SettingInputType = SettingInputType.ModalInput

    def __init__(self, *args, display_name, description, **kwargs):
        self.display_name: LazyStr = display_name
        self.description: LazyStr = description

    def default_value_in(self, skin: CustomSkin) -> Optional[str]:
        """
        The default value of this setting in this skin.

        This takes into account base skin data and localisation.
        May be `None` if the setting does not have a default value.
        """
        raise NotImplementedError

    def value_in(self, skin: CustomSkin) -> Optional[str]:
        """
        The current value of this setting from this skin.

        May be None if the setting is not set or does not have a value.
        Usually should not take into account defaults.
        """
        raise NotImplementedError

    def set_in(self, skin: CustomSkin, value: Optional[str]):
        """
        Set this setting to the given value in this skin.
        """
        raise NotImplementedError

    def format_value_in(self, skin: CustomSkin, value: Optional[str]) -> str:
        """
        Format the given setting value for display (typically in a setting table).
        """
        raise NotImplementedError

    async def parse_input(self, skin: CustomSkin, userstr: str) -> Optional[str]:
        """
        Parse a user provided string into a value for this setting.

        Will raise 'UserInputError' with a readable message if parsing fails.
        """
        raise NotImplementedError

    def make_input_field(self, skin: CustomSkin) -> TextInput:
        """
        Create a TextInput field for this setting, using the current value.
        """
        raise NotImplementedError


class PropertySetting(Setting):
    """
    A skin setting corresponding to a single property of a single card.

    Note that this is still abstract,
    as it does not implement any formatting or parsing methods.

    This will usually (but may not always) correspond to a single Field of the card skin.
    """
    def __init__(self, card: type[Card], property_name: str, **kwargs):
        super().__init__(**kwargs)
        self.card = card
        self.property_name = property_name

    @property
    def card_id(self):
        """
        The `card_id` of the Card class this setting belongs to.
        """
        return self.card.card_id

    @property
    def field(self) -> Optional[FieldDesc]:
        """
        The CardSkin field overwrriten by this setting, if it exists.
        """
        return self.card.skin._fields.get(self.property_name, None)

    def default_value_in(self, skin: CustomSkin) -> Optional[str]:
        """
        For a PropertySetting, the default value is determined as follows:
            base skin value from:
                - card base skin
                - custom base skin
                - global app base skin
            fallback (field) value from the CardSkin
        """
        base_skin = skin.get_prop(self.card_id, 'base_skin_id')
        base_skin = base_skin or skin.base_skin_name
        base_skin = base_skin or skin.cog.current_default

        app_skin_args = AppSkin.get(base_skin).for_card(self.card_id)

        if self.property_name in app_skin_args:
            return app_skin_args[self.property_name]
        elif self.field:
            return self.field.default
        else:
            return None

    def value_in(self, skin: CustomSkin) -> Optional[str]:
        return skin.get_prop(self.card_id, self.property_name)

    def set_in(self, skin: CustomSkin, value: Optional[str]):
        skin.set_prop(self.card_id, self.property_name, value)


class _ColourInterface(Setting):
    """
    Skin setting mixin for parsing and formatting colour typed settings.
    """

    def format_value_in(self, skin: CustomSkin, value: Optional[str]) -> str:
        if value:
            formatted = f"`{value}`"
        else:
            formatted = skin.bot.translator.t(_p(
                'skinsettings|colours|format:not_set',
                "Not Set"
            ))
        return formatted

    async def parse_input(self, skin: CustomSkin, userstr: str) -> Optional[str]:
        stripped = userstr.strip('# ').upper()
        if not stripped:
            value = None
        elif len(stripped) not in (6, 8) or any(c not in '0123456789ABCDEF' for c in stripped):
            raise UserInputError(
                skin.bot.translator.t(_p(
                    'skinsettings|colours|parse|error:invalid',
                    "Could not parse `{given}` as a colour!"
                    " Please use RGB/RGBA format (e.g. `#ABABABF0`)."
                )).format(given=userstr)
            )
        else:
            value = f"#{stripped}"
        return value

    def make_input_field(self, skin: CustomSkin) -> TextInput:
        t = skin.bot.translator.t

        value = self.value_in(skin)
        default_value = self.default_value_in(skin)

        label = t(self.display_name)
        default = value
        if default_value:
            placeholder = f"{default_value} ({t(self.description)})"
        else:
            placeholder = t(self.description)

        return TextInput(
            label=label,
            placeholder=placeholder,
            default=default,
            min_length=0,
            max_length=9,
            required=False,
        )


class ColourSetting(_ColourInterface, PropertySetting):
    """
    A Property skin setting representing a single colour field.
    """
    pass


class SkinSetting(PropertySetting):
    """
    A Property setting representing the base skin of a card.
    """
    input_type = SettingInputType.SkinInput

    def format_value_in(self, skin: CustomSkin, value: Optional[str]) -> str:
        if value:
            app_skin = AppSkin.get(value)
            formatted = f"`{app_skin.display_name}`"
        else:
            formatted = skin.bot.translator.t(_p(
                'skinsettings|base_skin|format:not_set',
                "Default"
            ))
        return formatted

    def default_value_in(self, skin: CustomSkin) -> Optional[str]:
        return skin.base_skin_name


class CompoundSetting(Setting):
    """
    A Setting combining several PropertySettings across (potentially) multiple cards.
    """
    NOTSHARED = ''

    def __init__(self, *settings: PropertySetting, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings

    def default_value_in(self, skin: CustomSkin) -> Optional[str]:
        """
        The default value of a CompoundSetting is the shared default of the component settings.

        If the components do not share a default value, returns None.
        """
        value = None
        for setting in self.settings:
            setting_value = setting.default_value_in(skin)
            if setting_value is None:
                value = None
                break
            if value is None:
                value = setting_value
            elif value != setting_value:
                value = None
                break
        return value

    def value_in(self, skin: CustomSkin) -> Optional[str]:
        """
        The value of a compound setting is the shared value of the components.
        """
        value = self.NOTSHARED
        for setting in self.settings:
            setting_value = setting.value_in(skin) or setting.default_value_in(skin)

            if value is self.NOTSHARED:
                value = setting_value
            elif value != setting_value:
                value = self.NOTSHARED
                break
        return value

    def set_in(self, skin: CustomSkin, value: Optional[str]):
        """
        Set all of the components individually.
        """
        for setting in self.settings:
            setting.set_in(skin, value)


class ColoursSetting(_ColourInterface, CompoundSetting):
    """
    Compound setting representing multiple colours.
    """
    def format_value_in(self, skin: CustomSkin, value: Optional[str]) -> str:
        if value is self.NOTSHARED:
            return "Mixed"
        elif value is None:
            return "Not Set"
        else:
            return f"`{value}`"

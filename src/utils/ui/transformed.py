from typing import Any, Type, TYPE_CHECKING
from enum import Enum

import discord
import discord.app_commands as appcmd
from discord.app_commands.transformers import AppCommandOptionType


__all__ = (
    'ChoicedEnum',
    'ChoicedEnumTransformer',
    'Transformed',
)


class ChoicedEnum(Enum):
    @property
    def choice_name(self):
        return self.name

    @property
    def choice_value(self):
        return self.value

    @property
    def choice(self):
        return appcmd.Choice(
            name=self.choice_name, value=self.choice_value
        )

    @classmethod
    def choices(self):
        return [item.choice for item in self]

    @classmethod
    def make_choice_map(cls):
        return {item.choice_value: item for item in cls}

    @classmethod
    async def transform(cls, transformer: 'ChoicedEnumTransformer', interaction: discord.Interaction, value: Any):
        return transformer._choice_map[value]

    @classmethod
    def option_type(cls) -> AppCommandOptionType:
        return AppCommandOptionType.string

    @classmethod
    def transformer(cls, *args) -> appcmd.Transformer:
        return ChoicedEnumTransformer(cls, *args)


class ChoicedEnumTransformer(appcmd.Transformer):
    # __discord_app_commands_is_choice__ = True

    def __init__(self, enum: Type[ChoicedEnum], opt_type) -> None:
        super().__init__()

        self._type = opt_type
        self._enum = enum
        self._choices = enum.choices()
        self._choice_map = enum.make_choice_map()

    @property
    def _error_display_name(self) -> str:
        return self._enum.__name__

    @property
    def type(self) -> AppCommandOptionType:
        return self._type

    @property
    def choices(self):
        return self._choices

    async def transform(self, interaction: discord.Interaction, value: Any, /) -> Any:
        return await self._enum.transform(self, interaction, value)


if TYPE_CHECKING:
    from typing_extensions import Annotated as Transformed
else:

    class Transformed:
        def __class_getitem__(self, items):
            cls = items[0]
            options = items[1:]

            if not hasattr(cls, 'transformer'):
                raise ValueError("Tranformed class must have a transformer classmethod.")
            transformer = cls.transformer(*options)
            return appcmd.Transform[cls, transformer]

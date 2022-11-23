from typing import Optional, Union, TYPE_CHECKING, TypeVar, Generic, Any, TypeAlias, Type
from enum import Enum

import pytz
import discord
import itertools
from discord import ui
from discord.ui.button import button, Button, ButtonStyle

from meta.context import context
from meta.errors import UserInputError
from utils.lib import strfdur, parse_dur
from babel import ctx_translator

from .base import ParentID
from .ui import InteractiveSetting, SettingWidget
from . import babel

_, _p = babel._, babel._p


if TYPE_CHECKING:
    from discord.guild import GuildChannel


# TODO: Localise this file


class StringSetting(InteractiveSetting[ParentID, str, str]):
    """
    Setting type mixin describing an arbitrary string type.

    Options
    -------
    _maxlen: int
        Maximum length of string to accept in `_parse_string`.
        Default: 4000

    _quote: bool
        Whether to display the string with backticks.
        Default: True
    """

    accepts = _p('settype:bool|accepts', "Any text")

    _maxlen: int = 4000
    _quote: bool = True

    @property
    def input_formatted(self) -> str:
        """
        Return the current data string.
        """
        if self._data is not None:
            return str(self._data)
        else:
            return ""

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value, **kwargs):
        """
        Return the provided value string as the data string.
        """
        return value

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        """
        Return the provided data string as the value string.
        """
        return data

    @classmethod
    async def _parse_string(cls, parent_id, string: str, **kwargs):
        """
        Parse the user input `string` into StringSetting data.
        Provides some minor input validation.
        Treats an empty string as a `None` value.
        """
        t = ctx_translator.get().t
        if len(string) > cls._maxlen:
            raise UserInputError(
                t(_p(
                    'settype:bool|error',
                    "Provided string is too long! Maximum length: {maxlen} characters."
                )).format(maxlen=cls._maxlen)
            )
        elif len(string) == 0:
            return None
        else:
            return string

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Optionally (see `_quote`) wrap the data string in backticks.
        """
        if data:
            return "`{}`".format(data) if cls._quote else str(data)
        else:
            return None


CT = TypeVar('CT', 'GuildChannel', 'discord.Object', 'discord.Thread')
MCT = TypeVar('MCT', discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.Object)


class ChannelSetting(Generic[ParentID, CT], InteractiveSetting[ParentID, int, CT]):
    """
    Setting type mixin describing a Guild Channel.

    Options
    -------
    _selector_placeholder: str
        Placeholder to use in the Widget selector.
        Default: "Select a channel"

    channel_types: list[discord.ChannelType]
        List of guild channel types to accept.
        Default: []
    """
    accepts = "Enter a channel name or id"

    _selector_placeholder = "Select a Channel"
    channel_types: list[discord.ChannelType] = []

    @classmethod
    def _data_from_value(cls, parent_id, value, **kwargs):
        """
        Returns the id of the provided channel.
        """
        if value is not None:
            return value.id

    @classmethod
    def _data_to_value(cls, parent_id, data, **kwargs):
        """
        Searches for the provided channel id in the current channel cache.
        If the channel cannot be found, returns a `discord.Object` instead.
        """
        if data is not None:
            ctx = context.get()
            channel = ctx.bot.get_channel(data)
            if channel is None:
                channel = discord.Object(id=data)
        return channel

    @classmethod
    async def _parse_string(cls, parent_id, string: str, **kwargs):
        # TODO: Waiting on seeker utils.
        ...

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Returns a manually formatted channel mention.
        """
        if data:
            return "<#{}>".format(data)
        else:
            return None

    @property
    def input_formatted(self) -> str:
        """
        Returns the channel name if possible, otherwise the id.
        """
        if self._data is not None:
            channel = self.value
            if channel is not None:
                if isinstance(channel, discord.Object):
                    return str(channel.id)
                else:
                    return f"#{channel.name}"
            else:
                return ""
        else:
            return ""

    class Widget(SettingWidget['ChannelSetting']):
        def update_children(self):
            self.update_child(
                self.channel_selector, {
                    'channel_types': self.setting.channel_types,
                    'placeholder': self.setting._selector_placeholder
                }
            )

        def make_exports(self):
            return [self.channel_selector]

        @ui.select(
            cls=ui.ChannelSelect,
            channel_types=[discord.ChannelType.text],
            placeholder="Select a Channel",
            max_values=1,
            min_values=0
        )
        async def channel_selector(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect) -> None:
            await interaction.response.defer(thinking=True, ephemeral=True)
            if select.values:
                channel = select.values[0]
                await self.setting.interactive_set(channel.id, interaction)
            else:
                await self.setting.interactive_set(None, interaction)


class VoiceChannelSetting(ChannelSetting):
    """
    Setting type mixin representing a discord VoiceChannel.
    Implemented as a narrowed `ChannelSetting`.
    See `ChannelSetting` for options.
    """
    channel_types = [discord.ChannelType.voice]


class MessageablelSetting(ChannelSetting):
    """
    Setting type mixin representing a discord Messageable guild channel.
    Implemented as a narrowed `ChannelSetting`.
    See `ChannelSetting` for options.
    """
    channel_types = [discord.ChannelType.text, discord.ChannelType.voice, discord.ChannelType.public_thread]

    @classmethod
    def _data_to_value(cls, parent_id, data, **kwargs):
        """
        Searches for the provided channel id in the current channel cache.
        If the channel cannot be found, returns a `discord.PartialMessageable` instead.
        """
        if data is not None:
            ctx = context.get()
            channel = ctx.bot.get_channel(data)
            if channel is None:
                channel = ctx.bot.get_partial_messageable(data, guild_id=parent_id)
        return channel


class RoleSetting(InteractiveSetting[ParentID, int, Union[discord.Role, discord.Object]]):
    """
    Setting type mixin describing a Guild Role.

    Options
    -------
    _selector_placeholder: str
        Placeholder to use in the Widget selector.
        Default: "Select a Role"
    """
    accepts = "Enter a role name or id"

    _selector_placeholder = "Select a Role"

    @classmethod
    def _get_guildid(cls, parent_id: int, **kwargs) -> int:
        """
        Fetch the current guildid.
        Assumes that the guilid is either passed as a kwarg or is the object id.
        Should be overridden in other cases.
        """
        return kwargs.get('guildid', parent_id)

    @classmethod
    def _data_from_value(cls, parent_id, value, **kwargs):
        """
        Returns the id of the provided role.
        """
        if value is not None:
            return value.id

    @classmethod
    def _data_to_value(cls, parent_id, data, **kwargs):
        """
        Searches for the provided role id in the current channel cache.
        If the channel cannot be found, returns a `discord.Object` instead.
        """
        if data is not None:
            role = None

            guildid = cls._get_guildid(parent_id)
            ctx = context.get()
            guild = ctx.bot.get_guild(guildid)
            if guild is not None:
                role = guild.get_role(data)
            if role is None:
                role = discord.Object(id=data)
        return role

    @classmethod
    async def _parse_string(cls, parent_id, string: str, **kwargs):
        # TODO: Waiting on seeker utils.
        ...

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Returns a manually formatted role mention.
        """
        if data:
            return "<@&{}>".format(data)
        else:
            return None

    @property
    def input_formatted(self) -> str:
        """
        Returns the role name if possible, otherwise the id.
        """
        if self._data is not None:
            role = self.value
            if role is not None:
                if isinstance(role, discord.Object):
                    return str(role.id)
                else:
                    return f"@{role.name}"
            else:
                return ""
        else:
            return ""

    class Widget(SettingWidget['RoleSetting']):
        def update_children(self):
            self.update_child(
                self.role_selector,
                {'placeholder': self.setting._selector_placeholder}
            )

        def make_exports(self):
            return [self.role_selector]

        @ui.select(
            cls=ui.RoleSelect,
            placeholder="Select a Role",
            max_values=1,
            min_values=0
        )
        async def role_selector(self, interaction: discord.Interaction, select: discord.ui.RoleSelect) -> None:
            await interaction.response.defer(thinking=True, ephemeral=True)
            if select.values:
                role = select.values[0]
                await self.setting.interactive_set(role.id, interaction)
            else:
                await self.setting.interactive_set(None, interaction)


class BoolSetting(InteractiveSetting[ParentID, bool, bool]):
    """
    Setting type mixin describing a boolean.

    Options
    -------
    _truthy: Set
        Set of strings that are considered "truthy" in the parser.
        Not case sensitive.
        Default: {"yes", "true", "on", "enable", "enabled"}

    _falsey: Set
        Set of strings that are considered "falsey" in the parser.
        Not case sensitive.
        Default: {"no", "false", "off", "disable", "disabled"}

    _outputs: tuple[str, str, str]
        Strings to represent 'True', 'False', and 'None' values respectively.
        Default: {True: "On", False: "Off", None: "Not Set"}
    """

    accepts = "True/False"

    # Values that are accepted as truthy and falsey by the parser
    _truthy = {"yes", "true", "on", "enable", "enabled"}
    _falsey = {"no", "false", "off", "disable", "disabled"}

    # The user-friendly output strings to use for each value
    _outputs = {True: "On", False: "Off", None: "Not Set"}

    # Button labels
    _true_button_args: dict[str, Any] = {}
    _false_button_args: dict[str, Any] = {}
    _reset_button_args: dict[str, Any] = {}

    @property
    def input_formatted(self) -> str:
        """
        Return the current data string.
        """
        if self._data is not None:
            output = self._outputs[self._data]
            set = (self._falsey, self._truthy)[self._data]

            if output.lower() in set:
                return output
            else:
                return next(iter(set))
        else:
            return ""

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value, **kwargs):
        """
        Directly return provided value bool as data bool.
        """
        return value

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        """
        Directly return provided data bool as value bool.
        """
        return data

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        """
        Looks up the provided string in the truthy and falsey tables.
        """
        _userstr = string.lower()
        if not _userstr or _userstr == "none":
            return None
        if _userstr in cls._truthy:
            return True
        elif _userstr in cls._falsey:
            return False
        else:
            raise UserInputError("Could not parse `{}` as a boolean.".format(string))

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Use provided _outputs dictionary to format data.
        """
        return cls._outputs[data]

    class Widget(SettingWidget['BoolSetting']):
        def update_children(self):
            self.update_child(self.true_button, self.setting._true_button_args)
            self.update_child(self.false_button, self.setting._false_button_args)
            self.update_child(self.reset_button, self.setting._reset_button_args)
            self.order_children(self.true_button, self.false_button, self.reset_button)

        def make_exports(self):
            return [self.true_button, self.false_button, self.reset_button]

        @button(style=ButtonStyle.secondary, label="On", row=4)
        async def true_button(self, interaction: discord.Interaction, button: Button):
            await interaction.response.defer(thinking=True, ephemeral=True)
            await self.setting.interactive_set(True, interaction)

        @button(style=ButtonStyle.secondary, label="Off", row=4)
        async def false_button(self, interaction: discord.Interaction, button: Button):
            await interaction.response.defer(thinking=True, ephemeral=True)
            await self.setting.interactive_set(False, interaction)


class IntegerSetting(InteractiveSetting[ParentID, int, int]):
    """
    Setting type mixin describing a ranged integer.
    As usual, override `_parse_string` to customise error messages.

    Options
    -------
    _min: int
        A minimum integer to accept.
        Default: -2147483647

    _max: int
        A maximum integer to accept.
        Default: 2147483647
    """
    _min = -2147483647
    _max = 2147483647

    accepts = "An integer"

    @property
    def input_formatted(self) -> str:
        """
        Return a string representation of the set integer.
        """
        if self._data is not None:
            return str(self._data)
        else:
            return ""

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value, **kwargs):
        """
        Directly return value integer as data integer.
        """
        return value

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        """
        Directly return data integer as value integer.
        """
        return data

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        """
        Parse the user input into an integer.
        """
        if not string:
            return None
        try:
            num = int(string)
        except Exception:
            raise UserInputError("Couldn't parse provided integer.") from None

        if num > cls._max:
            raise UserInputError("Provided integer was too large!")
        elif num < cls._min:
            raise UserInputError("Provided integer was too small!")

        return num

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Returns the stringified integer in backticks.
        """
        if data is not None:
            return f"`{data}`"


class EmojiSetting(InteractiveSetting[ParentID, str, discord.PartialEmoji]):
    """
    Setting type mixin describing an Emoji string.

    Options
    -------
    None
    """

    accepts = "Unicode or custom emoji"

    @staticmethod
    def _parse_emoji(emojistr):
        """
        Converts a provided string into a PartialEmoji.
        If the string is badly formatted, returns None.
        """
        if ":" in emojistr:
            emojistr = emojistr.strip('<>')
            splits = emojistr.split(":")
            if len(splits) == 3:
                animated, name, id = splits
                animated = bool(animated)
                return discord.PartialEmoji(name=name, animated=animated, id=int(id))
        else:
            # TODO: Check whether this is a valid emoji
            return discord.PartialEmoji(name=emojistr)

    @property
    def input_formatted(self) -> str:
        """
        Return the current data string.
        """
        if self._data is not None:
            return str(self._data)
        else:
            return ""

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value, **kwargs):
        """
        Stringify the value emoji into a consistent data string.
        """
        return str(value) if value is not None else None

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        """
        Convert the stored string into an emoji, through parse_emoji.
        This may return None if the parsing syntax changes.
        """
        return cls._parse_emoji(data) if data is not None else None

    @classmethod
    async def _parse_string(cls, parent_id, string: str, **kwargs):
        """
        Parse the provided string into a PartialEmoji if possible.
        """
        if string:
            emoji = cls._parse_emoji(string)
            if emoji is None:
                raise UserInputError("Could not understand provided emoji!")
            return str(emoji)
        return None

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Emojis are pretty much self-formatting. Just return the data directly.
        """
        return data


class GuildIDSetting(InteractiveSetting[ParentID, int, int]):
    """
    Setting type mixin describing a guildid.
    This acts like a pure integer type, apart from the formatting.

    Options
    -------
    """
    accepts = "Any Snowflake ID"
    # TODO: Consider autocomplete for guilds the user is in

    @property
    def input_formatted(self) -> str:
        """
        Return a string representation of the stored snowflake.
        """
        if self._data is not None:
            return str(self._data)
        else:
            return ""

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value, **kwargs):
        """
        Directly return value integer as data integer.
        """
        return value

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        """
        Directly return data integer as value integer.
        """
        return data

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        """
        Parse the user input into an integer.
        """
        if not string:
            return None
        try:
            num = int(string)
        except Exception:
            raise UserInputError("Couldn't parse provided guildid.") from None
        return num

    @classmethod
    def _format_data(cls, parent_id: ParentID, data, **kwargs):
        """
        Return the stored snowflake as a string.
        If the guild is in cache, attach the name as well.
        """
        if data is not None:
            ctx = context.get()
            guild = ctx.bot.get_guild(data)
            if guild is not None:
                return f"`{data}` ({guild.name})"
            else:
                return f"`{data}`"


TZT: TypeAlias = pytz.BaseTzInfo


class TimezoneSetting(InteractiveSetting[ParentID, str, TZT]):
    """
    Typed Setting ABC representing timezone information.
    """
    # TODO Definitely need autocomplete here
    accepts = "A timezone name."
    _accepts = (
        "A timezone name from [this list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) "
        "(e.g. `Europe/London`)."
    )

    @property
    def input_formatted(self) -> str:
        """
        Return a string representation of the stored timezone.
        """
        if self._data is not None:
            return str(self._data)
        else:
            return ""

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value, **kwargs):
        """
        Use str to transform the pytz timezone into a string.
        """
        if value:
            return str(value)

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        """
        Use pytz to convert the stored timezone string to a timezone.
        """
        if data:
            return pytz.timezone(data)

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        """
        Parse the user input into an integer.
        """
        # TODO: Another selection case.
        if not string:
            return None
        try:
            timezone = pytz.timezone(string)
        except pytz.exceptions.UnknownTimeZoneError:
            timezones = [tz for tz in pytz.all_timezones if string.lower() in tz.lower()]
            if len(timezones) == 1:
                timezone = timezones[0]
            elif timezones:
                raise UserInputError("Multiple matching timezones found!")
                # result = await ctx.selector(
                #     "Multiple matching timezones found, please select one.",
                #     timezones
                # )
                # timezone = timezones[result]
            else:
                raise UserInputError(
                    "Unknown timezone `{}`. "
                    "Please provide a TZ name from "
                    "[this list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)".format(string)
                ) from None
        return timezone

    @classmethod
    def _format_data(cls, parent_id: ParentID, data, **kwargs):
        """
        Return the stored snowflake as a string.
        If the guild is in cache, attach the name as well.
        """
        if data is not None:
            return f"`{data}`"


ET = TypeVar('ET', bound='Enum')


class EnumSetting(InteractiveSetting[ParentID, ET, ET]):
    """
    Typed InteractiveSetting ABC representing a stored Enum.
    The Enum is assumed to be data adapted (e.g. through RegisterEnum).

    The embed of an enum setting should usually be overridden to describe the options.

    The default widget is implemented as a select menu,
    although it may also make sense to implement using colour-changing buttons.

    Options
    -------
    _enum: Enum
        The Enum to act as a setting interface to.
    _outputs: dict[Enum, str]
        A map of enum items to output strings.
        Describes how the enum should be formatted.
    _inputs: dict[Enum, str]
        A map of accepted input strings (not case sensitive) to enum items.
        This should almost always include the strings from `_outputs`.
    """

    _enum: Type[ET]
    _outputs: dict[ET, str]
    _inputs: dict[str, ET]

    accepts = "A valid option."

    @property
    def input_formatted(self) -> str:
        """
        Return the output string for the current data.
        This assumes the output strings are accepted as inputs!
        """
        if self._data is not None:
            return self._outputs[self._data]
        else:
            return ""

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value, **kwargs):
        """
        Return the provided value enum item as the data enum item.
        """
        return value

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        """
        Return the provided data enum item as the value enum item.
        """
        return data

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        """
        Parse the user input into an enum item.
        """
        # TODO: Another selection case.
        if not string:
            return None
        string = string.lower()
        if string not in cls._inputs:
            raise UserInputError("Invalid choice!")
        return cls._inputs[string]

    @classmethod
    def _format_data(cls, parent_id: ParentID, data, **kwargs):
        """
        Format the enum using the provided output map.
        """
        if data is not None:
            if data not in cls._outputs:
                raise ValueError(f"Enum item {data} unmapped.")
            return cls._outputs[data]


class DurationSetting(InteractiveSetting[ParentID, int, int]):
    """
    Typed InteractiveSetting ABC representing a stored duration.
    Stored and retrieved as an integer number of seconds.
    Shown and set as a "duration string", e.g. "24h 10m 20s".

    Options
    -------
    _max: int
        Upper limit on the stored duration, in seconds.
        Default: 60 * 60 * 24 * 365
    _min: Optional[int]
        Lower limit on the stored duration, in seconds.
        The duration can never be negative.
    _default_multiplier: int
        Default multiplier to use to convert the number when it is provided alone.
        E.g. 1 for seconds, or 60 for minutes.
        Default: 1
    allow_zero: bool
        Whether to allow a zero duration.
        The duration parser typically returns 0 when no duration is found,
        so this may be useful for error checking.
        Default: False
    _show_days: bool
        Whether to show days in the formatted output.
        Default: False
    """

    accepts = "A number of days, hours, minutes, and seconds, e.g. `2d 4h 10s`."

    # Set an upper limit on the duration
    _max = 60 * 60 * 24 * 365
    _min = None

    # Default multiplier when the number is provided alone
    # 1 for seconds, 60 from minutes, etc
    _default_multiplier = None

    # Whether to allow empty durations
    # This is particularly useful since the duration parser will return 0 for most non-duration strings
    allow_zero = False

    # Whether to show days on the output
    _show_days = False

    @property
    def input_formatted(self) -> str:
        """
        Return the formatted duration, which is accepted as input.
        """
        if self._data is not None:
            return strfdur(self._data, short=True, show_days=self._show_days)
        else:
            return ""

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value, **kwargs):
        """
        Passthrough the provided duration in seconds.
        """
        return value

    @classmethod
    def _data_to_value(cls, parent_id: ParentID, data, **kwargs):
        """
        Passthrough the provided duration in seconds.
        """
        return data

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        """
        Parse the user input into a duration.
        """
        if not string:
            return None

        if cls._default_multiplier and string.isdigit():
            num = int(string) * cls._default_multiplier
        else:
            num = parse_dur(string)

        if num == 0 and not cls.allow_zero:
            raise UserInputError(
                "The provided duration cannot be `0`! (Please enter in the format `1d 2h 3m 4s`.)"
            )

        if cls._max is not None and num > cls._max:
            raise UserInputError(
                "Duration cannot be longer than `{}`!".format(
                    strfdur(cls._max, short=False, show_days=cls._show_days)
                )
            )
        if cls._min is not None and num < cls._min:
            raise UserInputError(
                "Duration cannot be shorter than `{}`!".format(
                    strfdur(cls._min, short=False, show_days=cls._show_days)
                )
            )

        return num

    @classmethod
    def _format_data(cls, parent_id: ParentID, data, **kwargs):
        """
        Format the enum using the provided output map.
        """
        if data is not None:
            return "`{}`".format(strfdur(data, short=False, show_days=cls._show_days))


class MessageSetting(StringSetting):
    """
    Typed Setting ABC representing a message sent to Discord.

    Placeholder implemented as a StringSetting until Context is built.
    """
    ...


class ListSetting:
    """
    Mixin to implement a setting type representing a list of existing settings.

    Does not implement a Widget,
    since arbitrary combinations of setting widgets are undefined.
    """
    # Base setting type to make the list from
    _setting = None  # type: Type[InteractiveSetting]

    # Whether 'None' values are filtered out of the data when creating values
    _allow_null_values = False  # type: bool

    # Whether duplicate data values should be filtered out
    _force_unique = False

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, values, **kwargs):
        """
        Returns the setting type data for each value in the value list
        """
        if values is None:
            # Special behaviour here, store an empty list instead of None
            return []
        else:
            return [cls._setting._data_from_value(parent_id, value) for value in values]

    @classmethod
    def _data_to_value(cls, parent_id: ParentID, data, **kwargs):
        """
        Returns the setting type value for each entry in the data list
        """
        if data is None:
            return []
        else:
            values = [cls._setting._data_to_value(parent_id, entry) for entry in data]

            # Filter out null values if required
            if not cls._allow_null_values:
                values = [value for value in values if value is not None]
            return values

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        """
        Splits the user string across `,` to break up the list.
        """
        if not string:
            return []
        else:
            data = []
            items = (item.strip() for item in string.split(','))
            items = (item for item in items if item)
            data = [await cls._setting._parse_string(parent_id, item, **kwargs) for item in items]

            if cls._force_unique:
                data = list(set(data))
            return data

    @classmethod
    def _format_data(cls, parent_id: ParentID, data, **kwargs):
        """
        Format the list by adding `,` between each formatted item
        """
        if not data:
            return None
        else:
            formatted_items = []
            for item in data:
                formatted_item = cls._setting._format_data(id, item)
                if formatted_item is not None:
                    formatted_items.append(formatted_item)
            return ", ".join(formatted_items)

    @property
    def input_formatted(self):
        """
        Format the list by adding `,` between each input formatted item.
        """
        if self._data:
            formatted_items = []
            for item in self._data:
                formatted_item = self._setting(self.parent_id, item).input_formatted
                if formatted_item:
                    formatted_items.append(formatted_item)
            return ", ".join(formatted_items)
        else:
            return ""


class ChannelListSetting(ListSetting, InteractiveSetting):
    """
    List of channels
    """
    accepts = (
        "Comma separated list of channel mentions/ids/names. Use `None` to unset. "
        "Write `--add` or `--remove` to add or remove channels."
    )
    _setting = ChannelSetting


class RoleListSetting(InteractiveSetting, ListSetting):
    """
    List of roles
    """
    accepts = (
        "Comma separated list of role mentions/ids/names. Use `None` to unset. "
        "Write `--add` or `--remove` to add or remove roles."
    )
    _setting = RoleSetting

    @property
    def members(self):
        roles = self.value
        return list(set(itertools.chain(*(role.members for role in roles))))


class StringListSetting(InteractiveSetting, ListSetting):
    """
    List of strings
    """
    accepts = (
        "Comma separated list of strings. Use `None` to unset. "
        "Write `--add` or `--remove` to add or remove strings."
    )
    _setting = StringSetting


class GuildIDListSetting(InteractiveSetting, ListSetting):
    """
    List of guildids.
    """
    accepts = (
        "Comma separated list of guild ids. Use `None` to unset. "
        "Write `--add` or `--remove` to add or remove ids. "
        "The provided ids are not verified in any way."
    )

    _setting = GuildIDSetting

from typing import Optional, Union, TYPE_CHECKING, TypeVar, Generic, Any, TypeAlias, Type
from enum import Enum

import pytz
import discord
import discord.app_commands as appcmds

import itertools
import datetime as dt
from discord import ui
from discord.ui.button import button, Button, ButtonStyle
from dateutil.parser import parse, ParserError

from meta.context import ctx_bot
from meta.errors import UserInputError
from utils.lib import strfdur, parse_duration
from babel.translator import ctx_translator, LazyStr

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

    _accepts = _p('settype:string|accepts', "Any Text")

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
                    'settype:string|error',
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


class EmojiSetting(InteractiveSetting[ParentID, str, str]):
    """
    Setting type representing a stored emoji.

    The emoji is stored in a single string field, and at no time is guaranteed to be a valid emoji.
    """
    _accepts = _p('settype:emoji|accepts', "Paste a builtin emoji, custom emoji, or emoji id.")

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
        Parse the given user entered emoji string.

        Accepts unicode (builtin) emojis, custom emojis, and custom emoji ids.
        """
        t = ctx_translator.get().t

        provided = string
        string = string.strip(' :<>')
        if string.startswith('a:'):
            string = string[2:]

        if not string or string.lower() == 'none':
            emojistr = None
        elif string.isdigit():
            # Assume emoji id
            emojistr = f"<a:unknown:{string}>"
        elif ':' in string:
            # Assume custom emoji
            emojistr = provided.strip()
        elif string.isascii():
            # Probably not an emoji
            raise UserInputError(
                t(_p(
                    'settype:emoji|error:parse',
                    "Could not parse `{provided}` as a Discord emoji. "
                    "Supported formats are builtin emojis (e.g. `{builtin}`), "
                    "custom emojis (e.g. {custom}), "
                    "or custom emoji ids (e.g. `{custom_id}`)."
                )).format(
                    provided=provided,
                    builtin="🤔",
                    custom="*`<`*`CuteLeo:942499177135480942`*`>`*",
                    custom_id="942499177135480942",
                )
            )
        else:
            # We don't have a good way of testing for emoji unicode
            # So just assume anything with unicode is an emoji.
            emojistr = string

        return emojistr

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Optionally (see `_quote`) wrap the data string in backticks.
        """
        if data:
            return data
        else:
            return None

    @property
    def as_partial(self) -> Optional[discord.PartialEmoji]:
        return self._parse_emoji(self.data)

    @staticmethod
    def _parse_emoji(emojistr: str):
        """
        Converts a provided string into a PartialEmoji.
        Deos not validate the emoji string.
        """
        if not emojistr:
            return None
        elif ":" in emojistr:
            emojistr = emojistr.strip('<>')
            splits = emojistr.split(":")
            if len(splits) == 3:
                animated, name, id = splits
                animated = bool(animated)
                return discord.PartialEmoji(name=name, animated=animated, id=int(id))
        else:
            return discord.PartialEmoji(name=emojistr)


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
    _accepts = _p('settype:channel|accepts', "A channel name or id")

    _selector_placeholder = "Select a Channel"
    channel_types: list[discord.ChannelType] = []
    _allow_object = False

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
            bot = ctx_bot.get()
            channel = bot.get_channel(data)
            if channel is None and cls._allow_object:
                channel = discord.Object(id=data)
            return channel

    @classmethod
    async def _parse_string(cls, parent_id, string: str, **kwargs):
        if not string or string.lower() == 'none':
            return None

        t = ctx_translator.get().t
        bot = ctx_bot.get()
        channel = None
        guild = bot.get_guild(parent_id)

        if string.isdigit():
            maybe_id = int(string)
            channel = guild.get_channel(maybe_id)
        else:
            channel = next((channel for channel in guild.channels if channel.name.lower() == string.lower()), None)

        if channel is None:
            raise UserInputError(t(_p(
                'settype:channel|parse|error:not_found',
                "Channel `{string}` could not be found in this guild!".format(string=string)
            )))
        return channel.id

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Returns a manually formatted channel mention.
        """
        if data:
            return "<#{}>".format(data)

    @property
    def input_formatted(self) -> str:
        data = self._data
        return str(data) if data else ''

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
            bot = ctx_bot.get()
            channel = bot.get_channel(data)
            if channel is None:
                channel = bot.get_partial_messageable(data, guild_id=parent_id)
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
    _accepts = _p('settype:role|accepts', "A role name or id")

    _selector_placeholder = "Select a Role"
    _allow_object = False

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

            guildid = cls._get_guildid(parent_id, **kwargs)
            bot = ctx_bot.get()
            guild = bot.get_guild(guildid)
            if guild is not None:
                role = guild.get_role(data)
            if role is None and cls._allow_object:
                role = discord.Object(id=data)
            return role

    @classmethod
    async def _parse_string(cls, parent_id, string: str, **kwargs):
        if not string or string.lower() == 'none':
            return None
        guildid = cls._get_guildid(parent_id, **kwargs)

        t = ctx_translator.get().t
        bot = ctx_bot.get()
        role = None
        guild = bot.get_guild(guildid)
        if guild is None:
            raise ValueError("Attempting to parse role string with no guild.")

        if string.isdigit():
            maybe_id = int(string)
            role = guild.get_role(maybe_id)
        else:
            role = next((role for role in guild.roles if role.name.lower() == string.lower()), None)

        if role is None:
            raise UserInputError(t(_p(
                'settype:role|parse|error:not_found',
                "Role `{string}` could not be found in this guild!".format(string=string)
            )))
        return role.id

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
        data = self._data
        return str(data) if data else ''

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

    _accepts = _p('settype:bool|accepts', "Enabled/Disabled")

    # Values that are accepted as truthy and falsey by the parser
    _truthy = _p(
        'settype:bool|parse:truthy_values',
        "enabled|yes|true|on|enable|1"
    )
    _falsey = _p(
        'settype:bool|parse:falsey_values',
        'disabled|no|false|off|disable|0'
    )

    # The user-friendly output strings to use for each value
    _outputs = {
        True: _p('settype:bool|output:true', "On"),
        False: _p('settype:bool|output:false', "Off"),
        None: _p('settype:bool|output:none', "Not Set"),
    }

    # Button labels
    _true_button_args: dict[str, Any] = {}
    _false_button_args: dict[str, Any] = {}
    _reset_button_args: dict[str, Any] = {}

    @classmethod
    def truthy_values(cls) -> set:
        t = ctx_translator.get().t
        return t(cls._truthy).lower().split('|')

    @classmethod
    def falsey_values(cls) -> set:
        t = ctx_translator.get().t
        return t(cls._falsey).lower().split('|')

    @property
    def input_formatted(self) -> str:
        """
        Return the current data string.
        """
        if self._data is not None:
            t = ctx_translator.get().t
            output = t(self._outputs[self._data])
            input_set = self.truthy_values() if self._data else self.falsey_values()

            if output.lower() in input_set:
                return output
            else:
                return next(iter(input_set))
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
        if _userstr in cls.truthy_values():
            return True
        elif _userstr in cls.falsey_values():
            return False
        else:
            raise UserInputError("Could not parse `{}` as a boolean.".format(string))

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Use provided _outputs dictionary to format data.
        """
        t = ctx_translator.get().t
        return t(cls._outputs[data])

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

    _accepts = _p('settype:integer|accepts', "An integer")

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


class PartialEmojiSetting(InteractiveSetting[ParentID, str, discord.PartialEmoji]):
    """
    Setting type mixin describing an Emoji string.

    Options
    -------
    None
    """

    _accepts = _p('settype:emoji|desc', "Unicode or custom emoji")

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
    _accepts = _p('settype:guildid|accepts', "Any Snowflake ID")
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
            bot = ctx_bot.get()
            guild = bot.get_guild(data)
            if guild is not None:
                return f"`{data}` ({guild.name})"
            else:
                return f"`{data}`"


TZT: TypeAlias = pytz.BaseTzInfo


class TimezoneSetting(InteractiveSetting[ParentID, str, TZT]):
    """
    Typed Setting ABC representing timezone information.
    """
    # TODO: Consider configuration UI for timezone by continent and country
    # Do any continents have more than 25 countries?
    # Maybe list e.g. Europe (Austria - Iceland) and Europe (Ireland - Ukraine) separately

    # TODO Definitely need autocomplete here
    _accepts = _p(
        'settype:timezone|accepts',
        "A timezone name from the 'tz database' (e.g. 'Europe/London')"
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
        # TODO: Localise
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
                # TODO: Add a selector-message here instead of dying instantly
                # Maybe only post a selector if there are less than 25 options!

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
        return str(timezone)

    def _desc_table(self) -> list[str]:
        translator = ctx_translator.get()
        t = translator.t

        lines = super()._desc_table()
        lines.append((
            t(_p(
                'settype:timezone|summary_table|field:supported|key',
                "Supported"
            )),
            t(_p(
                'settype:timezone|summary_table|field:supported|value',
                "Any timezone from the [tz database]({link})."
            )).format(link="https://en.wikipedia.org/wiki/List_of_tz_database_time_zones")
        ))
        return lines

    @classmethod
    async def parse_acmpl(cls, interaction: discord.Interaction, partial: str):
        bot = interaction.client
        t = bot.translator.t

        timezones = pytz.all_timezones
        matching = [tz for tz in timezones if partial.strip().lower() in tz.lower()][:25]
        if not matching:
            choices = [
                appcmds.Choice(
                    name=t(_p(
                        'set_type:timezone|acmpl|no_matching',
                        "No timezones matching '{input}'!"
                    )).format(input=partial)[:100],
                    value=partial
                )
            ]
        else:
            choices = []
            for tz in matching:
                timezone = pytz.timezone(tz)
                now = dt.datetime.now(timezone)
                nowstr = now.strftime("%H:%M")
                name = t(_p(
                    'set_type:timezone|acmpl|choice',
                    "{tz} (Currently {now})"
                )).format(tz=tz, now=nowstr)
                choice = appcmds.Choice(
                    name=name[:100],
                    value=tz
                )
                choices.append(choice)
        return choices

    @classmethod
    def _format_data(cls, parent_id: ParentID, data, **kwargs):
        """
        Return the stored snowflake as a string.
        If the guild is in cache, attach the name as well.
        """
        if data is not None:
            return f"`{data}`"


class TimestampSetting(InteractiveSetting[ParentID, str, dt.datetime]):
    """
    Typed Setting ABC representing a fixed point in time.

    Data is assumed to be a timezone aware datetime object.
    Value is the same as data.
    Parsing accepts YYYY-MM-DD [HH:MM] [+TZ]
    Display uses a discord timestamp.
    """
    _accepts = _p(
        'settype:timestamp|accepts',
        "A timestamp in the form YYYY-MM-DD HH:MM"
    )

    @classmethod
    def _data_from_value(cls, parent_id: ParentID, value, **kwargs):
        return value

    @classmethod
    def _data_to_value(cls, parent_id: ParentID, data, **kwargs):
        return data

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        string = string.strip()
        if string.lower() in ('', 'none', '0'):
            ts = None
        else:
            local_tz = await cls._timezone_from_id(parent_id, **kwargs)
            now = dt.datetime.now(tz=local_tz)
            default = now.replace(
                hour=0, minute=0,
                second=0, microsecond=0
            )
            try:
                ts = parse(string, fuzzy=True, default=default)
            except ParserError:
                t = ctx_translator.get().t
                raise UserInputError(t(_p(
                    'settype:timestamp|parse|error:invalid',
                    "Could not parse `{provided}` as a timestamp. Please use `YYYY-MM-DD HH:MM` format."
                )).format(provided=string))
        return ts

    @classmethod
    def _format_data(cls, parent_id: ParentID, data, **kwargs):
        if data is not None:
            return "<t:{}>".format(int(data.timestamp()))

    @classmethod
    async def _timezone_from_id(cls, parent_id: ParentID, **kwargs):
        """
        Extract the parsing timezone from the given parent id.

        Should generally be overriden for interactive settings.
        """
        return pytz.UTC

    @property
    def input_formatted(self) -> str:
        if self._data:
            formatted = self._data.strftime('%Y-%m-%d %H:%M')
        else:
            formatted = ''
        return formatted


class RawSetting(InteractiveSetting[ParentID, Any, Any]):
    """
    Basic implementation of an interactive setting with identical value and data type.
    """
    _accepts = _p('settype:raw|accepts', "Anything")

    @property
    def input_formatted(self) -> str:
        return str(self._data) if self._data is not None else ''

    @classmethod
    def _data_from_value(cls, parent_id, value, **kwargs):
        return value

    @classmethod
    def _data_to_value(cls, parent_id, data, **kwargs):
        return data

    @classmethod
    async def _parse_string(cls, parent_id: ParentID, string: str, **kwargs):
        return string

    @classmethod
    def _format_data(cls, parent_id: ParentID, data, **kwargs):
        return str(data) if data is not None else None


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
    _outputs: dict[ET, LazyStr]
    _input_patterns: dict[ET: LazyStr]
    _input_formatted: dict[ET: LazyStr]

    _accepts = _p('settype:enum|accepts', "A valid option.")

    @property
    def input_formatted(self) -> str:
        """
        Return the output string for the current data.
        This assumes the output strings are accepted as inputs!
        """
        t = ctx_translator.get().t
        if self._data is not None:
            return t(self._input_formatted[self._data])
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
        if not string:
            return None

        string = string.lower()
        t = ctx_translator.get().t

        found = None
        for enumitem, pattern in cls._input_patterns.items():
            item_keys = set(t(pattern).lower().split('|'))
            if string in item_keys:
                found = enumitem
                break

        if not found:
            raise UserInputError(
                t(_p(
                    'settype:enum|parse|error:not_found',
                    "`{provided}` is not a valid option!"
                )).format(provided=string)
            )

        return found

    @classmethod
    def _format_data(cls, parent_id: ParentID, data, **kwargs):
        """
        Format the enum using the provided output map.
        """
        t = ctx_translator.get().t
        if data is not None:
            if data not in cls._outputs:
                raise ValueError(f"Enum item {data} unmapped.")
            return t(cls._outputs[data])


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

    _accepts = _p(
        'settype:duration|accepts',
        "A number of days, hours, minutes, and seconds, e.g. `2d 4h 10s`."
    )

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
            num = parse_duration(string)

        if num is None:
            raise UserInputError("Could not parse the provided duration!")

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
        if data:
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
    _accepts = _p(
        'settype:channel_list|accepts',
        "Comma separated list of channel ids."
    )
    _setting = ChannelSetting


class RoleListSetting(ListSetting, InteractiveSetting):
    """
    List of roles
    """
    _accepts = _p(
        'settype:role_list|accepts',
        'Comma separated list of role ids.'
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
    _accepts = _p(
        'settype:stringlist|accepts',
        'Comma separated strings.'
    )
    _setting = StringSetting


class GuildIDListSetting(ListSetting, InteractiveSetting):
    """
    List of guildids.
    """
    _accepts = _p(
        'settype:guildidlist|accepts',
        'Comma separated list of guild ids.'
    )

    _setting = GuildIDSetting

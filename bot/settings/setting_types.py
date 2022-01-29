import json
import asyncio
import itertools
import traceback
from io import StringIO
from enum import IntEnum
from typing import Any, Optional

import pytz
import discord
from cmdClient.lib import SafeCancellation

from meta import client
from utils.lib import parse_dur, strfdur, prop_tabulate, multiple_replace

from LionContext import LionContext as Context

from .base import UserInputError


preview_emoji = '🔍'


class SettingType:
    """
    Abstract class representing a setting type.
    Intended to be used as a mixin for a Setting,
    with the provided methods implementing converter methods for the setting.
    """
    accepts: str = None  # User readable description of the acceptable values

    # Raw converters
    @classmethod
    def _data_from_value(cls, id: int, value, **kwargs):
        """
        Convert a high-level setting value to internal data.
        """
        raise NotImplementedError

    @classmethod
    def _data_to_value(cls, id: int, data: Any, **kwargs):
        """
        Convert internal data to high-level setting value.
        """
        raise NotImplementedError

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Parse user provided input into internal data.
        """
        raise NotImplementedError

    @classmethod
    def _format_data(cls, id: int, data: Any, **kwargs):
        """
        Convert internal data into a formatted user-readable string.
        """
        raise NotImplementedError


class Boolean(SettingType):
    """
    Boolean type, supporting truthy and falsey user input.
    Configurable to change truthy and falsey values, and the output map.

    Types:
        data: Optional[bool]
            The stored boolean value.
        value: Optional[bool]
            The stored boolean value.
    """
    accepts = "Yes/No, On/Off, True/False, Enabled/Disabled"

    # Values that are accepted as truthy and falsey by the parser
    _truthy = {"yes", "true", "on", "enable", "enabled"}
    _falsey = {"no", "false", "off", "disable", "disabled"}

    # The user-friendly output strings to use for each value
    _outputs = {True: "On", False: "Off", None: "Not Set"}

    @classmethod
    def _data_from_value(cls, id: int, value: Optional[bool], **kwargs):
        """
        Both data and value are of type Optional[bool].
        Directly return the provided value as data.
        """
        return value

    @classmethod
    def _data_to_value(cls, id: int, data: Optional[bool], **kwargs):
        """
        Both data and value are of type Optional[bool].
        Directly return the internal data as the value.
        """
        return data

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Looks up the provided string in the truthy and falsey tables.
        """
        _userstr = userstr.lower()
        if not _userstr or _userstr == "none":
            return None
        if _userstr in cls._truthy:
            return True
        elif _userstr in cls._falsey:
            return False
        else:
            raise UserInputError("Unknown boolean type `{}`".format(userstr))

    @classmethod
    def _format_data(cls, id: int, data: bool, **kwargs):
        """
        Pass the provided value through the outputs map.
        """
        return cls._outputs[data]


class Integer(SettingType):
    """
    Integer type. Storing any integer.

    Types:
        data: Optional[int]
            The stored integer value.
        value: Optional[int]
            The stored integer value.
    """
    accepts = "An integer."

    # Set limits on the possible integers
    _min = -2147483647
    _max = 2147483647

    @classmethod
    def _data_from_value(cls, id: int, value: Optional[bool], **kwargs):
        """
        Both data and value are of type Optional[int].
        Directly return the provided value as data.
        """
        return value

    @classmethod
    def _data_to_value(cls, id: int, data: Optional[bool], **kwargs):
        """
        Both data and value are of type Optional[int].
        Directly return the internal data as the value.
        """
        return data

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Relies on integer casting to convert the user string
        """
        if not userstr or userstr.lower() == "none":
            return None

        try:
            num = int(userstr)
        except Exception:
            raise UserInputError("Couldn't parse provided integer.") from None

        if num > cls._max:
            raise UserInputError("Provided integer was too large!")
        elif num < cls._min:
            raise UserInputError("Provided integer was too small!")

        return num

    @classmethod
    def _format_data(cls, id: int, data: Optional[int], **kwargs):
        """
        Return the string version of the data.
        """
        if data is None:
            return None
        else:
            return str(data)


class String(SettingType):
    """
    String type, storing arbitrary text.
    Configurable to limit text length and restrict input options.

    Types:
        data: Optional[str]
            The stored string.
        value: Optional[str]
            The stored string.
    """
    accepts = "Any text"

    # Maximum length of string to accept
    _maxlen: int = None

    # Set of input options to accept
    _options: set = None

    # Whether to quote the string as code
    _quote: bool = True

    @classmethod
    def _data_from_value(cls, id: int, value: Optional[str], **kwargs):
        """
        Return the provided value string as the data string.
        """
        return value

    @classmethod
    def _data_to_value(cls, id: int, data: Optional[str], **kwargs):
        """
        Return the provided data string as the value string.
        """
        return data

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Check that the user-entered string is of the correct length.
        Accept "None" to unset.
        """
        if not userstr or userstr.lower() == "none":
            # Unsetting case
            return None
        elif cls._maxlen is not None and len(userstr) > cls._maxlen:
            raise UserInputError("Provided string was too long! Maximum length is `{}`".format(cls._maxlen))
        elif cls._options is not None and not userstr.lower() in cls._options:
            raise UserInputError("Invalid option! Valid options are `{}`".format("`, `".join(cls._options)))
        else:
            return userstr

    @classmethod
    def _format_data(cls, id: int, data: str, **kwargs):
        """
        Wrap the string in backtics for formatting.
        Handle the special case where the string is empty.
        """
        if data:
            return "`{}`".format(data) if cls._quote else str(data)
        else:
            return None


class Channel(SettingType):
    """
    Channel type, storing a single `discord.Channel`.

    Types:
        data: Optional[int]
            The id of the stored Channel.
        value: Optional[discord.abc.GuildChannel]
            The stored Channel.
    """
    accepts = "Channel mention/id/name, or 'None' to unset"

    # Type of channel, if any
    _chan_type: discord.ChannelType = None

    @classmethod
    def _data_from_value(cls, id: int, value: Optional[discord.abc.GuildChannel], **kwargs):
        """
        Returns the channel id.
        """
        return value.id if value is not None else None

    @classmethod
    def _data_to_value(cls, id: int, data: Optional[int], **kwargs):
        """
        Uses the client to look up the channel id.
        Returns the Channel if found, otherwise None.
        """
        # Always passthrough None
        if data is None:
            return None

        return client.get_channel(data)

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Pass to the channel seeker utility to find the requested channel.
        Handle `0` and variants of `None` to unset.
        """
        if userstr.lower() in ('', '0', 'none'):
            return None
        else:
            channel = await ctx.find_channel(userstr, interactive=True, chan_type=cls._chan_type)
            if channel is None:
                raise SafeCancellation
            else:
                return channel.id

    @classmethod
    def _format_data(cls, id: int, data: Optional[int], **kwargs):
        """
        Retrieve the channel mention, if the channel still exists.
        If the channel no longer exists, or cannot be seen by the client, returns None.
        """
        if data is None:
            return None
        else:
            channel = client.get_channel(data)
            if channel:
                return channel.mention
            else:
                return None


class VoiceChannel(Channel):
    _chan_type = discord.ChannelType.voice


class TextChannel(Channel):
    _chan_type = discord.ChannelType.text


class Role(SettingType):
    """
    Role type, storing a single `discord.Role`.
    Configurably allows returning roles which don't exist or are not seen by the client
    as `discord.Object`.

    Settings may override `get_guildid` if the setting object `id` is not the guildid.

    Types:
        data: Optional[int]
            The id of the stored Role.
        value: Optional[Union[discord.Role, discord.Object]]
            The stored Role, or, if the role wasn't found and `_strict` is not set,
            a discord Object with the role id set.
    """
    accepts = "Role mention/id/name, or 'None' to unset"

    # Whether to disallow returning roles which don't exist as `discord.Object`s
    _strict = True

    _parse_create = False

    @classmethod
    def _data_from_value(cls, id: int, value: Optional[discord.Role], **kwargs):
        """
        Returns the role id.
        """
        return value.id if value is not None else None

    @classmethod
    def _data_to_value(cls, id: int, data: Optional[int], **kwargs):
        """
        Uses the client to look up the guild and role id.
        Returns the role if found, otherwise returns a `discord.Object` with the id set,
        depending on the `_strict` setting.
        """
        # Always passthrough None
        if data is None:
            return None

        # Fetch guildid
        guildid = cls._get_guildid(id, **kwargs)

        # Search for the role
        role = None
        guild = client.get_guild(guildid)
        if guild is not None:
            role = guild.get_role(data)

        if role is not None:
            return role
        elif not cls._strict:
            return discord.Object(id=data)
        else:
            return None

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Pass to the role seeker utility to find the requested role.
        Handle `0` and variants of `None` to unset.
        """
        if userstr.lower() in ('', '0', 'none'):
            return None
        else:
            role = await ctx.find_role(userstr, create=cls._parse_create, interactive=True)
            if role is None:
                raise SafeCancellation
            else:
                return role.id

    @classmethod
    def _format_data(cls, id: int, data: Optional[int], **kwargs):
        """
        Retrieve the role mention if found, otherwise the role id or None depending on `_strict`.
        """
        role = cls._data_to_value(id, data, **kwargs)
        if role is None:
            return "Not Set"
        elif isinstance(role, discord.Role):
            return role.mention
        else:
            return "`{}`".format(role.id)

    @classmethod
    def _get_guildid(cls, id: int, **kwargs):
        """
        Fetch the current guildid.
        Assumes that the guilid is either passed as a kwarg or is the object id.
        Should be overriden in other cases.
        """
        return kwargs.get('guildid', id)


class Emoji(SettingType):
    """
    Emoji type. Stores both custom and unicode emojis.
    """
    accepts = "Emoji, either built in or custom. Use 'None' to unset."

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
                return discord.PartialEmoji(name, animated=animated, id=int(id))
        else:
            # TODO: Check whether this is a valid emoji
            return discord.PartialEmoji(emojistr)

    @classmethod
    def _data_from_value(cls, id: int, value: Optional[discord.PartialEmoji], **kwargs):
        """
        Both data and value are of type Optional[discord.PartialEmoji].
        Directly return the provided value as data.
        """
        return value

    @classmethod
    def _data_to_value(cls, id: int, data: Optional[discord.PartialEmoji], **kwargs):
        """
        Both data and value are of type Optional[discord.PartialEmoji].
        Directly return the internal data as the value.
        """
        return data

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Pass to the emoji string parser to get the emoji.
        Handle `0` and variants of `None` to unset.
        """
        if userstr.lower() in ('', '0', 'none'):
            return None
        else:
            return cls._parse_emoji(userstr)

    @classmethod
    def _format_data(cls, id: int, data: Optional[discord.PartialEmoji], **kwargs):
        """
        Return a string form of the partial emoji, which generally displays the emoji.
        """
        if data is None:
            return None
        else:
            return str(data)


class Timezone(SettingType):
    """
    Timezone type, storing a valid timezone string.

    Types:
        data: Optional[str]
            The string representing the timezone in POSIX format.
        value: Optional[timezone]
            The pytz timezone.
    """
    accepts = (
        "A timezone name from [this list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) "
        "(e.g. `Europe/London`)."
    )

    @classmethod
    def _data_from_value(cls, id: int, value: Optional[str], **kwargs):
        """
        Return the provided value string as the data string.
        """
        if value is not None:
            return str(value)

    @classmethod
    def _data_to_value(cls, id: int, data: Optional[str], **kwargs):
        """
        Return the provided data string as the value string.
        """
        if data is not None:
            return pytz.timezone(data)

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Check that the user-entered string is of the correct length.
        Accept "None" to unset.
        """
        if not userstr or userstr.lower() == "none":
            # Unsetting case
            return None
        try:
            timezone = pytz.timezone(userstr)
        except pytz.exceptions.UnknownTimeZoneError:
            timezones = [tz for tz in pytz.all_timezones if userstr.lower() in tz.lower()]
            if len(timezones) == 1:
                timezone = timezones[0]
            elif timezones:
                result = await ctx.selector(
                    "Multiple matching timezones found, please select one.",
                    timezones
                )
                timezone = timezones[result]
            else:
                raise UserInputError(
                    "Unknown timezone `{}`. "
                    "Please provide a TZ name from "
                    "[this list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)".format(userstr)
                ) from None

        return str(timezone)

    @classmethod
    def _format_data(cls, id: int, data: str, **kwargs):
        """
        Wrap the string in backtics for formatting.
        Handle the special case where the string is empty.
        """
        if data:
            return "`{}`".format(data)
        else:
            return 'Not Set'


class IntegerEnum(SettingType):
    """
    Integer Enum type, accepting limited strings, storing an integer, and returning an IntEnum value

    Types:
        data: Optional[int]
            The stored integer.
        value: Optional[Any]
            The corresponding Enum member
    """
    accepts = "A valid option."

    # Enum to use for mapping values
    _enum: IntEnum = None

    # Custom map to format the value. If None, uses the enum names.
    _output_map = None

    @classmethod
    def _data_from_value(cls, id: int, value: ..., **kwargs):
        """
        Return the value corresponding to the enum member
        """
        if value is not None:
            return value.value

    @classmethod
    def _data_to_value(cls, id: int, data: ..., **kwargs):
        """
        Return the enum member corresponding to the provided integer
        """
        if data is not None:
            return cls._enum(data)

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Find the corresponding enum member's value to the provided user input.
        Accept "None" to unset.
        """
        userstr = userstr.lower()

        options = {name.lower(): mem.value for name, mem in cls._enum.__members__.items()}

        if not userstr or userstr == "none":
            # Unsetting case
            return None
        elif userstr not in options:
            raise UserInputError("Invalid option!")
        else:
            return options[userstr]

    @classmethod
    def _format_data(cls, id: int, data: int, **kwargs):
        """
        Format the data using either the `_enum` or the provided output map.
        """
        if data is not None:
            value = cls._enum(data)
            if cls._output_map:
                return cls._output_map[value]
            else:
                return "`{}`".format(value.name)


class Duration(SettingType):
    """
    Duration type, stores a time duration in seconds.

    Types:
        data: Optional[int]
            The stored number of seconds.
        value: Optional[int]
            The stored number of seconds.
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

    @classmethod
    def _data_from_value(cls, id: int, value: Optional[bool], **kwargs):
        """
        Both data and value are of type Optional[int].
        Directly return the provided value as data.
        """
        return value

    @classmethod
    def _data_to_value(cls, id: int, data: Optional[bool], **kwargs):
        """
        Both data and value are of type Optional[int].
        Directly return the internal data as the value.
        """
        return data

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Parse the provided duration.
        """
        if not userstr or userstr.lower() == "none":
            return None

        if cls._default_multiplier and userstr.isdigit():
            num = int(userstr) * cls._default_multiplier
        else:
            num = parse_dur(userstr)

        if num == 0 and not cls.allow_zero:
            raise UserInputError(
                "The provided duration cannot be `0`! (Please enter in the format `1d 2h 3m 4s`, or `None` to unset.)"
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
    def _format_data(cls, id: int, data: Optional[int], **kwargs):
        """
        Return the string version of the data.
        """
        if data is None:
            return None
        else:
            return "`{}`".format(strfdur(data, short=False, show_days=cls._show_days))


class Message(SettingType):
    """
    Message type storing json-encoded message arguments.
    Messages without an embed are displayed differently from those with an embed.

    Types:
        data: str
            A json dictionary with the fields `content` and `embed`.
        value: dict
            An argument dictionary suitable for `Message.send` or `Message.edit`.
    """

    _substitution_desc = {
    }

    @classmethod
    def _data_from_value(cls, id, value, **kwargs):
        if value is None:
            return None

        return json.dumps(value)

    @classmethod
    def _data_to_value(cls, id, data, **kwargs):
        if data is None:
            return None

        return json.loads(data)

    @classmethod
    async def parse(cls, id: int, ctx: Context, userstr: str, **kwargs):
        """
        Return a setting instance initialised from a parsed user string.
        """
        if ctx.msg.attachments:
            attachment = ctx.msg.attachments[0]
            if 'text' in attachment.content_type or 'json' in attachment.content_type:
                userstr = (await attachment.read()).decode()
                data = await cls._parse_userstr(ctx, id, userstr, as_json=True, **kwargs)
            else:
                raise UserInputError("Can't read the attached file!")
        else:
            data = await cls._parse_userstr(ctx, id, userstr, **kwargs)
        return cls(id, data, **kwargs)

    @classmethod
    async def _parse_userstr(cls, ctx, id, userstr, as_json=False, **kwargs):
        """
        Parse the provided string as either a content-only string, or json-format arguments.
        Provided string is not trusted, and is parsed in a safe manner.
        """
        if userstr.lower() == 'none':
            return None

        if as_json:
            try:
                args = json.loads(userstr)
                if not isinstance(args, dict) or (not args.get('content', None) and not args.get('embed', None)):
                    raise ValueError("At least one of the 'content' or 'embed' data fields are required.")
                if 'embed' in args:
                    discord.Embed.from_dict(
                        args['embed']
                    )
            except Exception as e:
                only_error = "".join(traceback.TracebackException.from_exception(e).format_exception_only())
                raise UserInputError(
                    "Couldn't parse your message! "
                    "You can test and fix it on the embed builder "
                    "[here](https://glitchii.github.io/embedbuilder/?editor=json).\n"
                    "```{}```".format(only_error)
                )
            if 'embed' in args and 'timestamp' in args['embed']:
                args['embed'].pop('timestamp')
            return json.dumps(args)
        else:
            return json.dumps({'content': userstr})

    @classmethod
    def _format_data(cls, id, data, **kwargs):
        if data is None:
            return "Empty"
        value = cls._data_to_value(id, data, **kwargs)
        if 'embed' not in value and 'content' not in value:
            return "Invalid"
        if 'embed' not in value and len(value['content']) < 100:
            return "`{}`".format(value['content'])
        else:
            return "Too long to display here!"

    def substitution_keys(self, ctx, **kwargs):
        """
        Instances should override this to provide their own substitution implementation.
        """
        return {}

    def args(self, ctx, **kwargs):
        """
        Applies the substitutions with the given context to generate the final message args.
        """
        value = self.value
        substitutions = self.substitution_keys(ctx, **kwargs)
        args = {}
        if value.get('content', None):
            args['content'] = multiple_replace(value['content'], substitutions)
        if value.get('embed', None):
            args['embed'] = discord.Embed.from_dict(
                json.loads(multiple_replace(json.dumps(value['embed']), substitutions))
            )
        return args

    async def widget(self, ctx, **kwargs):
        value = self.value
        args = self.args(ctx, **kwargs)

        if not value or not args:
            return await ctx.reply(embed=self.embed)

        current_str = None
        preview = None
        file_content = None
        if 'embed' in value or len(value['content']) > 1024:
            current_str = "See attached file."
            file_content = json.dumps(value, indent=4)
        elif "`" in value['content']:
            current_str = "```{}```".format(value['content'])
            if len(args['content']) < 1000:
                preview = args['content']
        else:
            current_str = "`{}`".format(value['content'])
            if len(args['content']) < 1000:
                preview = args['content']

        description = "{}\n\n**Current Value**: {}".format(
            self.long_desc.format(self=self, client=self.client),
            current_str
        )

        embed = discord.Embed(
            title="Configuration options for `{}`".format(self.display_name),
            description=description
        )
        if preview:
            embed.add_field(name="Message Preview", value=preview, inline=False)
        embed.add_field(
            name="Setting Guide",
            value=(
                "• For plain text without an embed, use `{prefix}config {setting} <text>`.\n"
                "• To include an embed, build the message [here]({builder}) "
                "and upload the json code as a file with the `{prefix}config {setting}` command.\n"
                "• To reset the message to the default, use `{prefix}config {setting} None`."
            ).format(
                prefix=ctx.best_prefix,
                setting=self.display_name,
                builder="https://glitchii.github.io/embedbuilder/?editor=gui"
            ),
            inline=False
        )
        if self._substitution_desc:
            embed.add_field(
                name="Substitution Keys",
                value=(
                    "*The following keys will be substituted for their current values.*\n{}"
                ).format(
                    prop_tabulate(*zip(*self._substitution_desc.items()), colon=False)
                ),
                inline=False
            )
        embed.set_footer(
            text="React with {} to preview the message.".format(preview_emoji)
        )
        if file_content:
            with StringIO() as message_file:
                message_file.write(file_content)
                message_file.seek(0)
                out_file = discord.File(message_file, filename="{}.json".format(self.display_name))
                out_msg = await ctx.reply(embed=embed, file=out_file)
        else:
            out_msg = await ctx.reply(embed=embed)

        # Add the preview reaction and send the preview when requested
        try:
            await out_msg.add_reaction(preview_emoji)
        except discord.HTTPException:
            return

        try:
            await ctx.client.wait_for(
                'reaction_add',
                check=lambda r, u: r.message.id == out_msg.id and r.emoji == preview_emoji and u == ctx.author,
                timeout=180
            )
        except asyncio.TimeoutError:
            try:
                await out_msg.remove_reaction(preview_emoji, ctx.client.user)
            except discord.HTTPException:
                pass
        else:
            try:
                await ctx.offer_delete(
                    await ctx.reply(**args, allowed_mentions=discord.AllowedMentions.none())
                )
            except discord.HTTPException as e:
                await ctx.reply(
                    embed=discord.Embed(
                        colour=discord.Colour.red(),
                        title="Preview failed! Error below",
                        description="```{}```".format(
                            e
                        )
                    )
                )


class SettingList(SettingType):
    """
    List of a particular type of setting.

    Types:
        data: List[SettingType.data]
            List of data types of the specified SettingType.
            Some of the data may be None.
        value: List[SettingType.value]
            List of the value types of the specified SettingType.
            Some of the values may be None.
    """
    # Base setting type to make the list from
    _setting = None  # type: SettingType

    # Whether 'None' values are filtered out of the data when creating values
    _allow_null_values = False  # type: bool

    # Whether duplicate data values should be filtered out
    _force_unique = False

    @classmethod
    def _data_from_value(cls, id: int, values: ..., **kwargs):
        """
        Returns the setting type data for each value in the value list
        """
        if values is None:
            # Special behaviour here, store an empty list instead of None
            return []
        else:
            return [cls._setting._data_from_value(id, value) for value in values]

    @classmethod
    def _data_to_value(cls, id: int, data: ..., **kwargs):
        """
        Returns the setting type value for each entry in the data list
        """
        if data is None:
            return []
        else:
            values = [cls._setting._data_to_value(id, entry) for entry in data]

            # Filter out null values if required
            if not cls._allow_null_values:
                values = [value for value in values if value is not None]
            return values

    @classmethod
    async def _parse_userstr(cls, ctx: Context, id: int, userstr: str, **kwargs):
        """
        Splits the user string across `,` to break up the list.
        Handle `0` and variants of `None` to unset.
        """
        if userstr.lower() in ('', '0', 'none'):
            return []
        else:
            data = []
            items = (item.strip() for item in userstr.split(','))
            items = (item for item in items if item)
            data = [await cls._setting._parse_userstr(ctx, id, item, **kwargs) for item in items]

            if cls._force_unique:
                data = list(set(data))
            return data

    @classmethod
    def _format_data(cls, id: int, data: ..., **kwargs):
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


class ChannelList(SettingList):
    """
    List of channels
    """
    accepts = (
        "Comma separated list of channel mentions/ids/names. Use `None` to unset. "
        "Write `--add` or `--remove` to add or remove channels."
    )
    _setting = Channel


class RoleList(SettingList):
    """
    List of roles
    """
    accepts = (
        "Comma separated list of role mentions/ids/names. Use `None` to unset. "
        "Write `--add` or `--remove` to add or remove roles."
    )
    _setting = Role

    @property
    def members(self):
        roles = self.value
        return list(set(itertools.chain(*(role.members for role in roles))))


class StringList(SettingList):
    """
    List of strings
    """
    accepts = (
        "Comma separated list of strings. Use `None` to unset. "
        "Write `--add` or `--remove` to add or remove strings."
    )
    _setting = String

from io import StringIO
from typing import NamedTuple, Optional, Sequence, Union, overload, List, Any
import collections
import datetime
import datetime as dt
import iso8601  # type: ignore
import pytz
import re
import json
from contextvars import Context

import discord
from discord.partial_emoji import _EmojiTag
from discord import Embed, File, GuildSticker, StickerItem, AllowedMentions, Message, MessageReference, PartialMessage
from discord.ui import View
from dateutil.parser import parse, ParserError

from babel.translator import ctx_translator
from meta.errors import UserInputError

from . import util_babel

_, _p = util_babel._, util_babel._p


multiselect_regex = re.compile(
    r"^([0-9, -]+)$",
    re.DOTALL | re.IGNORECASE | re.VERBOSE
)
tick = '✅'
cross = '❌'

MISSING = object()


class MessageArgs:
    """
    Utility class for storing message creation and editing arguments.
    """
    # TODO: Overrides for mutually exclusive arguments, see Messageable.send

    @overload
    def __init__(
        self,
        content: Optional[str] = ...,
        *,
        tts: bool = ...,
        embed: Embed = ...,
        file: File = ...,
        stickers: Sequence[Union[GuildSticker, StickerItem]] = ...,
        delete_after: float = ...,
        nonce: Union[str, int] = ...,
        allowed_mentions: AllowedMentions = ...,
        reference: Union[Message, MessageReference, PartialMessage] = ...,
        mention_author: bool = ...,
        view: View = ...,
        suppress_embeds: bool = ...,
    ) -> None:
        ...

    @overload
    def __init__(
        self,
        content: Optional[str] = ...,
        *,
        tts: bool = ...,
        embed: Embed = ...,
        files: Sequence[File] = ...,
        stickers: Sequence[Union[GuildSticker, StickerItem]] = ...,
        delete_after: float = ...,
        nonce: Union[str, int] = ...,
        allowed_mentions: AllowedMentions = ...,
        reference: Union[Message, MessageReference, PartialMessage] = ...,
        mention_author: bool = ...,
        view: View = ...,
        suppress_embeds: bool = ...,
    ) -> None:
        ...

    @overload
    def __init__(
        self,
        content: Optional[str] = ...,
        *,
        tts: bool = ...,
        embeds: Sequence[Embed] = ...,
        file: File = ...,
        stickers: Sequence[Union[GuildSticker, StickerItem]] = ...,
        delete_after: float = ...,
        nonce: Union[str, int] = ...,
        allowed_mentions: AllowedMentions = ...,
        reference: Union[Message, MessageReference, PartialMessage] = ...,
        mention_author: bool = ...,
        view: View = ...,
        suppress_embeds: bool = ...,
    ) -> None:
        ...

    @overload
    def __init__(
        self,
        content: Optional[str] = ...,
        *,
        tts: bool = ...,
        embeds: Sequence[Embed] = ...,
        files: Sequence[File] = ...,
        stickers: Sequence[Union[GuildSticker, StickerItem]] = ...,
        delete_after: float = ...,
        nonce: Union[str, int] = ...,
        allowed_mentions: AllowedMentions = ...,
        reference: Union[Message, MessageReference, PartialMessage] = ...,
        mention_author: bool = ...,
        view: View = ...,
        suppress_embeds: bool = ...,
    ) -> None:
        ...

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @property
    def send_args(self) -> dict:
        if self.kwargs.get('view', MISSING) is None:
            kwargs = self.kwargs.copy()
            kwargs.pop('view')
        else:
            kwargs = self.kwargs

        return kwargs

    @property
    def edit_args(self) -> dict:
        args = {}
        kept = (
            'content', 'embed', 'embeds', 'delete_after', 'allowed_mentions', 'view'
        )
        for k in kept:
            if k in self.kwargs:
                args[k] = self.kwargs[k]

        if 'file' in self.kwargs:
            args['attachments'] = [self.kwargs['file']]

        if 'files' in self.kwargs:
            args['attachments'] = self.kwargs['files']

        if 'suppress_embeds' in self.kwargs:
            args['suppress'] = self.kwargs['suppress_embeds']

        return args


def tabulate(
    *fields: tuple[str, str],
    row_format: str = "`{invis}{key:<{pad}}{colon}`\t{value}",
    sub_format: str = "`{invis:<{pad}}{colon}`\t{value}",
    colon: str = ':',
    invis: str = "​",
    **args
) -> list[str]:
    """
    Turns a list of (property, value) pairs into
    a pretty string with one `prop: value` pair each line,
    padded so that the colons in each line are lined up.
    Use `\\r\\n` in a value to break the line with padding.

    Parameters
    ----------
    fields: List[tuple[str, str]]
        List of (key, value) pairs.
    row_format: str
        The format string used to format each row.
    sub_format: str
        The format string used to format each subline in a row.
    colon: str
        The colon character used.
    invis: str
        The invisible character used (to avoid Discord stripping the string).

    Returns: List[str]
        The list of resulting table rows.
        Each row corresponds to one (key, value) pair from fields.
    """
    max_len = max(len(field[0]) for field in fields)

    rows = []
    for field in fields:
        key = field[0]
        value = field[1]
        lines = value.split('\r\n')

        row_line = row_format.format(
            invis=invis,
            key=key,
            pad=max_len,
            colon=colon,
            value=lines[0],
            field=field,
            **args
        )
        if len(lines) > 1:
            row_lines = [row_line]
            for line in lines[1:]:
                sub_line = sub_format.format(
                    invis=invis,
                    pad=max_len + len(colon),
                    colon=colon,
                    value=line,
                    **args
                )
                row_lines.append(sub_line)
            row_line = '\n'.join(row_lines)
        rows.append(row_line)
    return rows


def paginate_list(item_list: list[str], block_length=20, style="markdown", title=None) -> list[str]:
    """
    Create pretty codeblock pages from a list of strings.

    Parameters
    ----------
    item_list: List[str]
        List of strings to paginate.
    block_length: int
        Maximum number of strings per page.
    style: str
        Codeblock style to use.
        Title formatting assumes the `markdown` style, and numbered lists work well with this.
        However, `markdown` sometimes messes up formatting in the list.
    title: str
        Optional title to add to the top of each page.

    Returns: List[str]
        List of pages, each formatted into a codeblock,
        and containing at most `block_length` of the provided strings.
    """
    lines = ["{0:<5}{1:<5}".format("{}.".format(i + 1), str(line)) for i, line in enumerate(item_list)]
    page_blocks = [lines[i:i + block_length] for i in range(0, len(lines), block_length)]
    pages = []
    for i, block in enumerate(page_blocks):
        pagenum = "Page {}/{}".format(i + 1, len(page_blocks))
        if title:
            header = "{} ({})".format(title, pagenum) if len(page_blocks) > 1 else title
        else:
            header = pagenum
        header_line = "=" * len(header)
        full_header = "{}\n{}\n".format(header, header_line) if len(page_blocks) > 1 or title else ""
        pages.append("```{}\n{}{}```".format(style, full_header, "\n".join(block)))
    return pages


def split_text(text: str, blocksize=2000, code=True, syntax="", maxheight=50) -> list[str]:
    """
    Break the text into blocks of maximum length blocksize
    If possible, break across nearby newlines. Otherwise just break at blocksize chars

    Parameters
    ----------
    text: str
        Text to break into blocks.
    blocksize: int
        Maximum character length for each block.
    code: bool
        Whether to wrap each block in codeblocks (these are counted in the blocksize).
    syntax: str
        The markdown formatting language to use for the codeblocks, if applicable.
    maxheight: int
        The maximum number of lines in each block

    Returns: List[str]
        List of blocks,
        each containing at most `block_size` characters,
        of height at most `maxheight`.
    """
    # Adjust blocksize to account for the codeblocks if required
    blocksize = blocksize - 8 - len(syntax) if code else blocksize

    # Build the blocks
    blocks = []
    while True:
        # If the remaining text is already small enough, append it
        if len(text) <= blocksize:
            blocks.append(text)
            break
        text = text.strip('\n')

        # Find the last newline in the prototype block
        split_on = text[0:blocksize].rfind('\n')
        split_on = blocksize if split_on < blocksize // 5 else split_on

        # Add the block and truncate the text
        blocks.append(text[0:split_on])
        text = text[split_on:]

    # Add the codeblock ticks and the code syntax header, if required
    if code:
        blocks = ["```{}\n{}\n```".format(syntax, block) for block in blocks]

    return blocks


def strfdelta(delta: datetime.timedelta, sec=False, minutes=True, short=False) -> str:
    """
    Convert a datetime.timedelta object into an easily readable duration string.

    Parameters
    ----------
    delta: datetime.timedelta
        The timedelta object to convert into a readable string.
    sec: bool
        Whether to include the seconds from the timedelta object in the string.
    minutes: bool
        Whether to include the minutes from the timedelta object in the string.
    short: bool
        Whether to abbreviate the units of time ("hour" to "h", "minute" to "m", "second" to "s").

    Returns: str
        A string containing a time from the datetime.timedelta object, in a readable format.
        Time units will be abbreviated if short was set to True.
    """
    output = [[delta.days, 'd' if short else ' day'],
              [delta.seconds // 3600, 'h' if short else ' hour']]
    if minutes:
        output.append([delta.seconds // 60 % 60, 'm' if short else ' minute'])
    if sec:
        output.append([delta.seconds % 60, 's' if short else ' second'])
    for i in range(len(output)):
        if output[i][0] != 1 and not short:
            output[i][1] += 's'  # type: ignore
    reply_msg = []
    if output[0][0] != 0:
        reply_msg.append("{}{} ".format(output[0][0], output[0][1]))
    if output[0][0] != 0 or output[1][0] != 0 or len(output) == 2:
        reply_msg.append("{}{} ".format(output[1][0], output[1][1]))
    for i in range(2, len(output) - 1):
        reply_msg.append("{}{} ".format(output[i][0], output[i][1]))
    if not short and reply_msg:
        reply_msg.append("and ")
    reply_msg.append("{}{}".format(output[-1][0], output[-1][1]))
    return "".join(reply_msg)


def _parse_dur(time_str: str) -> int:
    """
    Parses a user provided time duration string into a timedelta object.

    Parameters
    ----------
    time_str: str
        The time string to parse. String can include days, hours, minutes, and seconds.

    Returns: int
        The number of seconds the duration represents.
    """
    funcs = {'d': lambda x: x * 24 * 60 * 60,
             'h': lambda x: x * 60 * 60,
             'm': lambda x: x * 60,
             's': lambda x: x}
    time_str = time_str.strip(" ,")
    found = re.findall(r'(\d+)\s?(\w+?)', time_str)
    seconds = 0
    for bit in found:
        if bit[1] in funcs:
            seconds += funcs[bit[1]](int(bit[0]))
    return seconds


def strfdur(duration: int, short=True, show_days=False) -> str:
    """
    Convert a duration given in seconds to a number of hours, minutes, and seconds.
    """
    days = duration // (3600 * 24) if show_days else 0
    hours = duration // 3600
    if days:
        hours %= 24
    minutes = duration // 60 % 60
    seconds = duration % 60

    parts = []
    if days:
        unit = 'd' if short else (' days' if days != 1 else ' day')
        parts.append('{}{}'.format(days, unit))
    if hours:
        unit = 'h' if short else (' hours' if hours != 1 else ' hour')
        parts.append('{}{}'.format(hours, unit))
    if minutes:
        unit = 'm' if short else (' minutes' if minutes != 1 else ' minute')
        parts.append('{}{}'.format(minutes, unit))
    if seconds or duration == 0:
        unit = 's' if short else (' seconds' if seconds != 1 else ' second')
        parts.append('{}{}'.format(seconds, unit))

    if short:
        return ' '.join(parts)
    else:
        return ', '.join(parts)


def substitute_ranges(ranges_str: str, max_match=20, max_range=1000, separator=',') -> str:
    """
    Substitutes a user provided list of numbers and ranges,
    and replaces the ranges by the corresponding list of numbers.

    Parameters
    ----------
    ranges_str: str
        The string to ranges in.
    max_match: int
        The maximum number of ranges to replace.
        Any ranges exceeding this will be ignored.
    max_range: int
        The maximum length of range to replace.
        Attempting to replace a range longer than this will raise a `ValueError`.
    """
    def _repl(match):
        n1 = int(match.group(1))
        n2 = int(match.group(2))
        if n2 - n1 > max_range:
            # TODO: Upgrade to SafeCancellation
            raise ValueError("Provided range is too large!")
        return separator.join(str(i) for i in range(n1, n2 + 1))

    return re.sub(r'(\d+)\s*-\s*(\d+)', _repl, ranges_str, max_match)


def parse_ranges(ranges_str: str, ignore_errors=False, separator=',', **kwargs) -> list[int]:
    """
    Parses a user provided range string into a list of numbers.
    Extra keyword arguments are transparently passed to the underlying parser `substitute_ranges`.
    """
    substituted = substitute_ranges(ranges_str, separator=separator, **kwargs)
    _numbers = (item.strip() for item in substituted.split(','))
    numbers = [item for item in _numbers if item]
    integers = [int(item) for item in numbers if item.isdigit()]

    if not ignore_errors and len(integers) != len(numbers):
        # TODO: Upgrade to SafeCancellation
        raise ValueError(
            "Couldn't parse the provided selection!\n"
            "Please provide comma separated numbers and ranges, e.g. `1, 5, 6-9`."
        )

    return integers


def msg_string(msg: discord.Message, mask_link=False, line_break=False, tz=None, clean=True) -> str:
    """
    Format a message into a string with various information, such as:
    the timestamp of the message, author, message content, and attachments.

    Parameters
    ----------
    msg: Message
        The message to format.
    mask_link: bool
        Whether to mask the URLs of any attachments.
    line_break: bool
        Whether a line break should be used in the string.
    tz: Timezone
        The timezone to use in the formatted message.
    clean: bool
        Whether to use the clean content of the original message.

    Returns: str
        A formatted string containing various information:
        User timezone, message author, message content, attachments
    """
    timestr = "%I:%M %p, %d/%m/%Y"
    if tz:
        time = iso8601.parse_date(msg.created_at.isoformat()).astimezone(tz).strftime(timestr)
    else:
        time = msg.created_at.strftime(timestr)
    user = str(msg.author)
    attach_list = [attach.proxy_url for attach in msg.attachments if attach.proxy_url]
    if mask_link:
        attach_list = ["[Link]({})".format(url) for url in attach_list]
    attachments = "\nAttachments: {}".format(", ".join(attach_list)) if attach_list else ""
    return "`[{time}]` **{user}:** {line_break}{message} {attachments}".format(
        time=time,
        user=user,
        line_break="\n" if line_break else "",
        message=msg.clean_content if clean else msg.content,
        attachments=attachments
    )


def convdatestring(datestring: str) -> datetime.timedelta:
    """
    Convert a date string into a datetime.timedelta object.

    Parameters
    ----------
    datestring: str
        The string to convert to a datetime.timedelta object.

    Returns: datetime.timedelta
        A datetime.timedelta object formed from the string provided.
    """
    datestring = datestring.strip(' ,')
    datearray = []
    funcs = {'d': lambda x: x * 24 * 60 * 60,
             'h': lambda x: x * 60 * 60,
             'm': lambda x: x * 60,
             's': lambda x: x}
    currentnumber = ''
    for char in datestring:
        if char.isdigit():
            currentnumber += char
        else:
            if currentnumber == '':
                continue
            datearray.append((int(currentnumber), char))
            currentnumber = ''
    seconds = 0
    if currentnumber:
        seconds += int(currentnumber)
    for i in datearray:
        if i[1] in funcs:
            seconds += funcs[i[1]](i[0])
    return datetime.timedelta(seconds=seconds)


class _rawChannel(discord.abc.Messageable):
    """
    Raw messageable class representing an arbitrary channel,
    not necessarially seen by the gateway.
    """
    def __init__(self, state, id):
        self._state = state
        self.id = id

    async def _get_channel(self):
        return discord.Object(self.id)


async def mail(client: discord.Client, channelid: int, **msg_args) -> discord.Message:
    """
    Mails a message to a channelid which may be invisible to the gateway.

    Parameters:
        client: discord.Client
            The client to use for mailing.
            Must at least have static authentication and have a valid `_connection`.
        channelid: int
            The channel id to mail to.
        msg_args: Any
            Message keyword arguments which are passed transparently to `_rawChannel.send(...)`.
    """
    # Create the raw channel
    channel = _rawChannel(client._connection, channelid)
    return await channel.send(**msg_args)


class EmbedField(NamedTuple):
    name: str
    value: str
    inline: Optional[bool] = True


def emb_add_fields(embed: discord.Embed, emb_fields: list[tuple[str, str, bool]]):
    """
    Append embed fields to an embed.
    Parameters
    ----------
    embed: discord.Embed
        The embed to add the field to.
    emb_fields: tuple
        The values to add to a field.
    name: str
        The name of the field.
    value: str
        The value of the field.
    inline: bool
        Whether the embed field should be inline or not.
    """
    for field in emb_fields:
        embed.add_field(name=str(field[0]), value=str(field[1]), inline=bool(field[2]))


def join_list(string: list[str], nfs=False) -> str:
    """
    Join a list together, separated with commas, plus add "and" to the beginning of the last value.
    Parameters
    ----------
    string: list
        The list to join together.
    nfs: bool
        (no fullstops)
        Whether to exclude fullstops/periods from the output messages.
        If not provided, fullstops will be appended to the output.
    """
    # TODO: Probably not useful with localisation
    if len(string) > 1:
        return "{}{} and {}{}".format((", ").join(string[:-1]),
                                      "," if len(string) > 2 else "", string[-1], "" if nfs else ".")
    else:
        return "{}{}".format("".join(string), "" if nfs else ".")


def shard_of(shard_count: int, guildid: int) -> int:
    """
    Calculate the shard number of a given guild.
    """
    return (guildid >> 22) % shard_count if shard_count and shard_count > 0 else 0


def jumpto(guildid: int, channeldid: int, messageid: int) -> str:
    """
    Build a jump link for a message given its location.
    """
    return 'https://discord.com/channels/{}/{}/{}'.format(
        guildid,
        channeldid,
        messageid
    )


def utc_now() -> datetime.datetime:
    """
    Return the current timezone-aware utc timestamp.
    """
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)


def multiple_replace(string: str, rep_dict: dict[str, str]) -> str:
    if rep_dict:
        pattern = re.compile(
            "|".join([re.escape(k) for k in sorted(rep_dict, key=len, reverse=True)]),
            flags=re.DOTALL
        )
        return pattern.sub(lambda x: str(rep_dict[x.group(0)]), string)
    else:
        return string


def recover_context(context: Context):
    for var in context:
        var.set(context[var])


def parse_ids(idstr: str) -> List[int]:
    """
    Parse a provided comma separated string of maybe-mentions, maybe-ids, into a list of integer ids.

    Object agnostic, so all mention tokens are stripped.
    Raises UserInputError if an id is invalid,
    setting `orig` and `item` info fields.
    """
    from meta.errors import UserInputError

    # Extract ids from string
    splititer = (split.strip('<@!#&>, ') for split in idstr.split(','))
    splits = [split for split in splititer if split]

    # Check they are integers
    if (not_id := next((split for split in splits if not split.isdigit()), None)) is not None:
        raise UserInputError("Could not extract an id from `$item`!", {'orig': idstr, 'item': not_id})

    # Cast to integer and return
    return list(map(int, splits))


def error_embed(error, **kwargs) -> discord.Embed:
    embed = discord.Embed(
        colour=discord.Colour.brand_red(),
        description=error,
        timestamp=utc_now()
    )
    return embed


class DotDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


parse_dur_exps = [
    (
        _p(
            'util:parse_dur|regex:day',
            r"(?P<value>\d+)\s*(?:(d)|(day))"
        ),
        60 * 60 * 24
    ),
    (
        _p(
            'util:parse_dur|regex:hour',
            r"(?P<value>\d+)\s*(?:(h)|(hour))"
        ),
        60 * 60
    ),
    (
        _p(
            'util:parse_dur|regex:minute',
            r"(?P<value>\d+)\s*(?:(m)|(min))"
        ),
        60
    ),
    (
        _p(
            'util:parse_dur|regex:second',
            r"(?P<value>\d+)\s*(?:(s)|(sec))"
        ),
        1
    )
]


def parse_duration(string: str) -> Optional[int]:
    translator = ctx_translator.get()
    if translator is None:
        raise ValueError("Cannot parse duration without a translator.")
    t = translator.t

    seconds = 0
    found = False
    for expr, multiplier in parse_dur_exps:
        match = re.search(t(expr), string, flags=re.IGNORECASE)
        if match:
            found = True
            seconds += int(match.group('value')) * multiplier

    return seconds if found else None


class Timezoned:
    """
    ABC mixin for objects with a set timezone.

    Provides several useful localised properties.
    """
    __slots__ = ()

    @property
    def timezone(self) -> pytz.timezone:
        """
        Must be implemented by the deriving class!
        """
        raise NotImplementedError

    @property
    def now(self):
        """
        Return the current time localised to the object's timezone.
        """
        return datetime.datetime.now(tz=self.timezone)

    @property
    def today(self):
        """
        Return the start of the day localised to the object's timezone.
        """
        now = self.now
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    @property
    def week_start(self):
        """
        Return the start of the week in the object's timezone
        """
        today = self.today
        return today - datetime.timedelta(days=today.weekday())

    @property
    def month_start(self):
        """
        Return the start of the current month in the object's timezone
        """
        today = self.today
        return today.replace(day=1)


def replace_multiple(format_string, mapping):
    """
    Subsistutes the keys from the format_dict with their corresponding values.

    Substitution is non-chained, and done in a single pass via regex.
    """
    if not mapping:
        raise ValueError("Empty mapping passed.")

    keys = list(mapping.keys())
    pattern = '|'.join(f"({key})" for key in keys)
    string = re.sub(pattern, lambda match: str(mapping[keys[match.lastindex - 1]]), format_string)
    return string


def emojikey(emoji: discord.Emoji | discord.PartialEmoji | str):
    """
    Produces a distinguishing key for an Emoji or PartialEmoji.

    Equality checks using this key should act as expected.
    """
    if isinstance(emoji, _EmojiTag):
        if emoji.id:
            key = str(emoji.id)
        else:
            key = str(emoji.name)
    else:
        key = str(emoji)

    return key

def recurse_map(func, obj, loc=[]):
    if isinstance(obj, dict):
        for k, v in obj.items():
            loc.append(k)
            obj[k] = recurse_map(func, v, loc)
            loc.pop()
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            loc.append(i)
            obj[i] = recurse_map(func, item)
            loc.pop()
    else:
        obj = func(loc, obj)
    return obj 

async def check_dm(user: discord.User | discord.Member) -> bool:
    """
    Check whether we can direct message the given user.

    Assumes the client is initialised.
    This uses an always-failing HTTP request,
    so we need to be very very very careful that this is not used frequently.
    Optimally only at the explicit behest of the user
    (i.e. during a user instigated interaction).
    """
    try:
        await user.send('')
    except discord.Forbidden:
        return False
    except discord.HTTPException:
        return True


async def command_lengths(tree) -> dict[str, int]:
    cmds = tree.get_commands()
    payloads = [
        await cmd.get_translated_payload(tree.translator)
        for cmd in cmds
    ]
    lens = {}
    for command in payloads:
        name = command['name']
        crumbs = {}
        cmd_len = lens[name] = _recurse_length(command, crumbs, (name,))
        if name == 'configure' or cmd_len > 4000:
            print(f"'{name}' over 4000. Breadcrumb Trail follows:")
            lines = []
            for loc, val in crumbs.items():
                locstr = '.'.join(loc)
                lines.append(f"{locstr}: {val}")
            print('\n'.join(lines))
            print(json.dumps(command, indent=2))
    return lens

def _recurse_length(payload, breadcrumbs={}, header=()) -> int:
    total = 0
    total_header = (*header, '')
    breadcrumbs[total_header] = 0

    if isinstance(payload, dict):
        # Read strings that count towards command length
        # String length is length of longest localisation, including default.
        for key in ('name', 'description', 'value'):
            if key in payload:
                value = payload[key]
                if isinstance(value, str):
                    values = (value, *payload.get(key + '_localizations', {}).values())
                    maxlen = max(map(len, values))
                    total += maxlen
                    breadcrumbs[(*header, key)] = maxlen

        for key, value in payload.items():
            loc = (*header, key)
            total += _recurse_length(value, breadcrumbs, loc)
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            if isinstance(item, dict) and 'name' in item:
                loc = (*header, f"{i}<{item['name']}>")
            else:
                loc = (*header, str(i))
            total += _recurse_length(item, breadcrumbs, loc)

    if total:
        breadcrumbs[total_header] = total
    else:
        breadcrumbs.pop(total_header)

    return total

async def parse_time_static(timestr, timezone):
    timestr = timestr.strip()
    default = dt.datetime.now(tz=timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    if not timestr:
        return default
    try:
        ts = parse(timestr, fuzzy=True, default=default)
    except ParserError:
        t = ctx_translator.get().t
        raise UserInputError(
            t(_p(
                'parse_timestamp|error:parse',
                "Could not parse `{given}` as a valid reminder time. "
                "Try entering the time in the form `HH:MM` or `YYYY-MM-DD HH:MM`."
            )).format(given=timestr)
        )
    return ts

def write_records(records: list[dict[str, Any]], stream: StringIO):
    if records:
        keys = records[0].keys()
        stream.write(','.join(keys))
        stream.write('\n')
        for record in records:
            stream.write(','.join(map(str, record.values())))
            stream.write('\n')

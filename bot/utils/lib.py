import datetime
import iso8601  # type: ignore
import re

import discord

# from cmdClient.lib import SafeCancellation


multiselect_regex = re.compile(
    r"^([0-9, -]+)$",
    re.DOTALL | re.IGNORECASE | re.VERBOSE
)
tick = '✅'
cross = '❌'


def prop_tabulate(prop_list: list[str], value_list: list[str], indent=True, colon=True) -> str:
    """
    Turns a list of properties and corresponding list of values into
    a pretty string with one `prop: value` pair each line,
    padded so that the colons in each line are lined up.
    Handles empty props by using an extra couple of spaces instead of a `:`.

    Parameters
    ----------
    prop_list: List[str]
        List of short names to put on the right side of the list.
        Empty props are considered to be "newlines" for the corresponding value.
    value_list: List[str]
        List of values corresponding to the properties above.
    indent: bool
        Whether to add padding so the properties are right-adjusted.

    Returns: str
    """
    max_len = max(len(prop) for prop in prop_list)
    return "".join(["`{}{}{}`\t{}{}".format("​ " * (max_len - len(prop)) if indent else "",
                                            prop,
                                            (":" if len(prop) else "​ " * 2) if colon else '',
                                            value_list[i],
                                            '' if str(value_list[i]).endswith("```") else '\n')
                    for i, prop in enumerate(prop_list)])


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


def parse_dur(time_str: str) -> int:
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


class DotDict(dict):
    """
    Dict-type allowing dot access to keys.
    """
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


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

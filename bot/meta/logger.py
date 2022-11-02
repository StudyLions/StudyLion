import sys
import logging
import asyncio
from contextvars import ContextVar
from discord import AllowedMentions

from .config import conf
from . import sharding


log_context: ContextVar[str] = ContextVar('logging_context', default='CTX: ROOT CONTEXT')
log_action: ContextVar[str] = ContextVar('logging_action', default='UNKNOWN ACTION')


RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[3%dm"
BOLD_SEQ = "\033[1m"
"]]]"
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

def colour_escape(fmt: str) -> str:
    cmap = {
        '%(black)': COLOR_SEQ % BLACK,
        '%(red)': COLOR_SEQ % RED,
        '%(green)': COLOR_SEQ % GREEN,
        '%(yellow)': COLOR_SEQ % YELLOW,
        '%(blue)': COLOR_SEQ % BLUE,
        '%(magenta)': COLOR_SEQ % MAGENTA,
        '%(cyan)': COLOR_SEQ % CYAN,
        '%(white)': COLOR_SEQ % WHITE,
        '%(reset)': RESET_SEQ,
        '%(bold)': BOLD_SEQ,
    }
    for key, value in cmap.items():
        fmt = fmt.replace(key, value)
    return fmt


log_format = ('[%(green)%(asctime)-19s%(reset)][%(red)%(levelname)-8s%(reset)]' +
              '[%(cyan)SHARD {:02}%(reset)]'.format(sharding.shard_number) +
              '[%(cyan)%(context)-22s%(reset)]' +
              '[%(cyan)%(action)-22s%(reset)]' +
              ' %(bold)%(cyan)%(name)s:%(reset)' +
              ' %(white)%(message)s%(reset)')
log_format = colour_escape(log_format)


# Setup the logger
logger = logging.getLogger()
log_fmt = logging.Formatter(
    fmt=log_format,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger.setLevel(logging.NOTSET)


class LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0


class ContextInjection(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'context'):
            record.context = log_context.get()
        if not hasattr(record, 'action'):
            record.action = log_action.get()
        return True


logging_handler_out = logging.StreamHandler(sys.stdout)
logging_handler_out.setLevel(logging.DEBUG)
logging_handler_out.setFormatter(log_fmt)
logging_handler_out.addFilter(LessThanFilter(logging.WARNING))
logging_handler_out.addFilter(ContextInjection())
logger.addHandler(logging_handler_out)

logging_handler_err = logging.StreamHandler(sys.stderr)
logging_handler_err.setLevel(logging.WARNING)
logging_handler_err.setFormatter(log_fmt)
logging_handler_err.addFilter(ContextInjection())
logger.addHandler(logging_handler_err)

# TODO: Add an async handler for posting
# Subclass this, create a DiscordChannelHandler, taking a Client and a channel as an argument
# Then we can handle error channels etc differently
# The formatting can be handled with a custom handler as well


# Define the context log format and attach it to the command logger as well
def log(message, context="GLOBAL", level=logging.INFO, post=True):
    # Add prefixes to lines for better parsing capability
    lines = message.splitlines()
    if len(lines) > 1:
        lines = [
            '┌ ' * (i == 0) + '│ ' * (0 < i < len(lines) - 1) + '└ ' * (i == len(lines) - 1) + line
            for i, line in enumerate(lines)
        ]
    else:
        lines = ['─ ' + message]

    for line in lines:
        logger.log(level, '\b[{}] {}'.format(
            str(context).center(22, '='),
            line
        ))

    # Fire and forget to the channel logger, if it is set up
    if post and client.is_ready():
        asyncio.ensure_future(live_log(message, context, level))


# Live logger that posts to the logging channels
async def live_log(message, context, level):
    if level >= logging.INFO:
        if level >= logging.WARNING:
            log_chid = conf.bot.getint('error_channel') or conf.bot.getint('log_channel')
        else:
            log_chid = conf.bot.getint('log_channel')

        # Generate the log messages
        if sharding.sharded:
            header = f"[{logging.getLevelName(level)}][SHARD {sharding.shard_number}][{context}]"
        else:
            header = f"[{logging.getLevelName(level)}][{context}]"

        if len(message) > 1900:
            blocks = split_text(message, blocksize=1900, code=False)
        else:
            blocks = [message]

        if len(blocks) > 1:
            blocks = [
                "```md\n{}[{}/{}]\n{}\n```".format(header, i+1, len(blocks), block) for i, block in enumerate(blocks)
            ]
        else:
            blocks = ["```md\n{}\n{}\n```".format(header, blocks[0])]

        # Post the log messages
        if log_chid:
            [await mail(client, log_chid, content=block, allowed_mentions=AllowedMentions.none()) for block in blocks]

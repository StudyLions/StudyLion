import sys
import logging
import asyncio
from logging.handlers import QueueListener, QueueHandler
from queue import SimpleQueue
from contextlib import contextmanager

from contextvars import ContextVar
from discord import AllowedMentions, Webhook
import aiohttp

from .config import conf
from . import sharding
from utils.lib import split_text, utc_now


log_context: ContextVar[str] = ContextVar('logging_context', default='CTX: ROOT CONTEXT')
log_action: ContextVar[str] = ContextVar('logging_action', default='UNKNOWN ACTION')
log_app: ContextVar[str] = ContextVar('logging_shard', default="SHARD {:03}".format(sharding.shard_number))


@contextmanager
def logging_context(context=None, action=None):
    if context is not None:
        context_t = log_context.set(context)
    if action is not None:
        action_t = log_action.set(action)
    try:
        yield
    finally:
        if context is not None:
            log_context.reset(context_t)
        if action is not None:
            log_action.reset(action_t)


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
              '[%(cyan)%(app)-15s%(reset)]' +
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
        record.app = log_app.get()
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


class LocalQueueHandler(QueueHandler):
    def emit(self, record: logging.LogRecord) -> None:
        # Removed the call to self.prepare(), handle task cancellation
        try:
            self.enqueue(record)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.handleError(record)


class WebHookHandler(logging.StreamHandler):
    def __init__(self, webhook_url, batch=False):
        super().__init__(self)
        self.webhook_url = webhook_url
        self.batched = ""
        self.batch = batch
        self.loop = None

    def get_loop(self):
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
        return self.loop

    def emit(self, record):
        self.get_loop().run_until_complete(self.post(record))

    async def post(self, record):
        try:
            timestamp = utc_now().strftime("%d/%m/%Y, %H:%M:%S")
            header = f"[{record.levelname}][{record.app}][{record.context}][{record.action}][{timestamp}]"
            message = record.msg

            # TODO: Maybe send file instead of splitting?
            # TODO: Reformat header a little
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

            # Post the log message(s)
            if self.batch:
                if len(message) > 500:
                    await self._send_batched()
                    await self._send(*blocks)
                elif len(self.batched) + len(blocks[0]) > 500:
                    self.batched += blocks[0]
                    await self._send_batched()
                else:
                    self.batched += blocks[0]
            else:
                await self._send(*blocks)
        except Exception as ex:
            print(ex)

    async def _send_batched(self):
        if self.batched:
            batched = self.batched
            self.batched = ""
            await self._send(batched)

    async def _send(self, *blocks):
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(self.webhook_url, session=session)
            for block in blocks:
                await webhook.send(block)


handlers = []
if webhook := conf.logging['general_log']:
    handler = WebHookHandler(webhook, batch=True)
    handlers.append(handler)

if webhook := conf.logging['error_log']:
    handler = WebHookHandler(webhook, batch=False)
    handler.setLevel(logging.ERROR)
    handlers.append(handler)

if webhook := conf.logging['critical_log']:
    handler = WebHookHandler(webhook, batch=False)
    handler.setLevel(logging.CRITICAL)
    handlers.append(handler)

if handlers:
    queue: SimpleQueue[logging.LogRecord] = SimpleQueue()

    handler = QueueHandler(queue)
    handler.setLevel(logging.INFO)
    handler.addFilter(ContextInjection())
    logger.addHandler(handler)

    listener = QueueListener(
        queue, *handlers, respect_handler_level=True
    )
    listener.start()


# QueueHandler to feed entries to a Queue
# On the other end of the Queue, feed to the webhook

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

import sys
import logging
import asyncio
from typing import List
from logging.handlers import QueueListener, QueueHandler
from queue import SimpleQueue
from contextlib import contextmanager
from io import StringIO

from contextvars import ContextVar
from discord import Webhook, File
import aiohttp

from .config import conf
from . import sharding
from .context import context
from utils.lib import utc_now


log_logger = logging.getLogger(__name__)
log_logger.propagate = False


log_context: ContextVar[str] = ContextVar('logging_context', default='CTX: ROOT CONTEXT')
log_action_stack: ContextVar[List[str]] = ContextVar('logging_action_stack', default=[])
log_app: ContextVar[str] = ContextVar('logging_shard', default="SHARD {:03}".format(sharding.shard_number))


@contextmanager
def logging_context(context=None, action=None, stack=None):
    if context is not None:
        context_t = log_context.set(context)
    if action is not None:
        astack = log_action_stack.get()
        log_action_stack.set(astack + [action])
    if stack is not None:
        actions_t = log_action_stack.set(stack)
    try:
        yield
    finally:
        if context is not None:
            log_context.reset(context_t)
        if stack is not None:
            log_action_stack.reset(actions_t)
        if action is not None:
            log_action_stack.set(astack)


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
              '[%(cyan)%(context)-24s%(reset)]' +
              '[%(cyan)%(actionstr)-22s%(reset)]' +
              ' %(bold)%(cyan)%(name)s:%(reset)' +
              ' %(white)%(message)s%(ctxstr)s%(reset)')
log_format = colour_escape(log_format)


# Setup the logger
logger = logging.getLogger()
log_fmt = logging.Formatter(
    fmt=log_format,
    # datefmt='%Y-%m-%d %H:%M:%S'
)
logger.setLevel(logging.NOTSET)


class LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0


class ThreadFilter(logging.Filter):
    def __init__(self, thread_name):
        super().__init__("")
        self.thread = thread_name

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.threadName == self.thread else 0


class ContextInjection(logging.Filter):
    def filter(self, record):
        # These guards are to allow override through _extra
        # And to ensure the injection is idempotent
        if not hasattr(record, 'context'):
            record.context = log_context.get()

        if not hasattr(record, 'actionstr'):
            action_stack = log_action_stack.get()
            if hasattr(record, 'action'):
                action_stack = (*action_stack, record.action)
            if action_stack:
                record.actionstr = ' ➔ '.join(action_stack)
            else:
                record.actionstr = "Unknown Action"

        if not hasattr(record, 'app'):
            record.app = log_app.get()

        if not hasattr(record, 'ctx'):
            if ctx := context.get():
                record.ctx = repr(ctx)
            else:
                record.ctx = None

        if getattr(record, 'with_ctx', False) and record.ctx:
            record.ctxstr = '\n' + record.ctx
        else:
            record.ctxstr = ""
        return True


logging_handler_out = logging.StreamHandler(sys.stdout)
logging_handler_out.setLevel(logging.DEBUG)
logging_handler_out.setFormatter(log_fmt)
logging_handler_out.addFilter(LessThanFilter(logging.WARNING))
logging_handler_out.addFilter(ContextInjection())
logger.addHandler(logging_handler_out)
log_logger.addHandler(logging_handler_out)

logging_handler_err = logging.StreamHandler(sys.stderr)
logging_handler_err.setLevel(logging.WARNING)
logging_handler_err.setFormatter(log_fmt)
logging_handler_err.addFilter(ContextInjection())
logger.addHandler(logging_handler_err)
log_logger.addHandler(logging_handler_err)


class LocalQueueHandler(QueueHandler):
    def _emit(self, record: logging.LogRecord) -> None:
        # Removed the call to self.prepare(), handle task cancellation
        try:
            self.enqueue(record)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.handleError(record)


class WebHookHandler(logging.StreamHandler):
    def __init__(self, webhook_url, batch=False, loop=None):
        super().__init__()
        self.webhook_url = webhook_url
        self.batched = ""
        self.batch = batch
        self.loop = loop
        self.batch_delay = 10
        self.batch_task = None
        self.last_batched = None
        self.waiting = []

    def get_loop(self):
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        return self.loop

    def emit(self, record):
        self.get_loop().call_soon_threadsafe(self._post, record)

    def _post(self, record):
        asyncio.create_task(self.post(record))

    async def post(self, record):
        log_context.set("Webhook Logger")
        log_action_stack.set(["Logging"])
        log_app.set(record.app)

        try:
            timestamp = utc_now().strftime("%d/%m/%Y, %H:%M:%S")
            header = f"[{record.asctime}][{record.levelname}][{record.app}][{record.actionstr}] <{record.context}>"
            context = f"\n# Context: {record.ctx}" if record.ctx else ""
            message = f"{header}\n{record.msg}{context}"

            if len(message) > 1900:
                as_file = True
            else:
                as_file = False
                message = "```md\n{}\n```".format(message)

            # Post the log message(s)
            if self.batch:
                if len(message) > 1500:
                    await self._send_batched_now()
                    await self._send(message, as_file=as_file)
                else:
                    self.batched += message
                    if len(self.batched) + len(message) > 1500:
                        await self._send_batched_now()
                    else:
                        asyncio.create_task(self._schedule_batched())
            else:
                await self._send(message, as_file=as_file)
        except Exception as ex:
            print(ex)

    async def _schedule_batched(self):
        if self.batch_task is not None and not (self.batch_task.done() or self.batch_task.cancelled()):
            # noop, don't reschedule if it is already scheduled
            return
        try:
            self.batch_task = asyncio.create_task(asyncio.sleep(self.batch_delay))
            await self.batch_task
            await self._send_batched()
        except asyncio.CancelledError:
            return
        except Exception as ex:
            print(ex)

    async def _send_batched_now(self):
        if self.batch_task is not None and not self.batch_task.done():
            self.batch_task.cancel()
        self.last_batched = None
        await self._send_batched()

    async def _send_batched(self):
        if self.batched:
            batched = self.batched
            self.batched = ""
            await self._send(batched)

    async def _send(self, message, as_file=False):
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(self.webhook_url, session=session)
            if as_file or len(message) > 2000:
                with StringIO(message) as fp:
                    fp.seek(0)
                    await webhook.send(
                        file=File(fp, filename="logs.md"),
                        username=log_app.get()
                    )
            else:
                await webhook.send(message, username=log_app.get())


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
    # First create a separate loop to run the handlers on
    import threading

    def run_loop(loop):
        asyncio.set_event_loop(loop)
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=lambda: run_loop(loop))
    loop_thread.daemon = True
    loop_thread.start()

    for handler in handlers:
        handler.loop = loop

    queue: SimpleQueue[logging.LogRecord] = SimpleQueue()

    qhandler = QueueHandler(queue)
    qhandler.setLevel(logging.INFO)
    qhandler.addFilter(ContextInjection())
    # qhandler.addFilter(ThreadFilter('MainThread'))
    logger.addHandler(qhandler)

    listener = QueueListener(
        queue, *handlers, respect_handler_level=True
    )
    listener.start()

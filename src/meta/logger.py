import sys
import logging
import asyncio
from typing import List, Optional
from logging.handlers import QueueListener, QueueHandler
import queue
import multiprocessing
from contextlib import contextmanager
from io import StringIO
from functools import wraps
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
log_action_stack: ContextVar[tuple[str, ...]] = ContextVar('logging_action_stack', default=())
log_app: ContextVar[str] = ContextVar('logging_shard', default="SHARD {:03}".format(sharding.shard_number))

def set_logging_context(
    context: Optional[str] = None,
    action: Optional[str] = None,
    stack: Optional[tuple[str, ...]] = None
):
    """
    Statically set the logging context variables to the given values.

    If `action` is given, pushes it onto the `log_action_stack`.
    """
    if context is not None:
        log_context.set(context)
    if action is not None or stack is not None:
        astack = log_action_stack.get()
        newstack = stack if stack is not None else astack
        if action is not None:
            newstack = (*newstack, action)
        log_action_stack.set(newstack)


@contextmanager
def logging_context(context=None, action=None, stack=None):
    """
    Context manager for executing a block of code in a given logging context.

    This context manager should only be used around synchronous code.
    This is because async code *may* get cancelled or externally garbage collected,
    in which case the finally block will be executed in the wrong context.
    See https://github.com/python/cpython/issues/93740
    This can be refactored nicely if this gets merged:
        https://github.com/python/cpython/pull/99634

    (It will not necessarily break on async code,
     if the async code can be guaranteed to clean up in its own context.)
    """
    if context is not None:
        oldcontext = log_context.get()
        log_context.set(context)
    if action is not None or stack is not None:
        astack = log_action_stack.get()
        newstack = stack if stack is not None else astack
        if action is not None:
            newstack = (*newstack, action)
        log_action_stack.set(newstack)
    try:
        yield
    finally:
        if context is not None:
            log_context.set(oldcontext)
        if stack is not None or action is not None:
            log_action_stack.set(astack)


def with_log_ctx(isolate=True, **kwargs):
    """
    Execute a coroutine inside a given logging context.

    If `isolate` is true, ensures that context does not leak
    outside the coroutine.

    If `isolate` is false, just statically set the context,
    which will leak unless the coroutine is
    called in an externally copied context.
    """
    def decorator(func):
        @wraps(func)
        async def wrapped(*w_args, **w_kwargs):
            if isolate:
                with logging_context(**kwargs):
                    # Task creation will synchronously copy the context
                    # This is gc safe
                    name = kwargs.get('action', f"log-wrapped-{func.__name__}")
                    task = asyncio.create_task(func(*w_args, **w_kwargs), name=name)
                return await task
            else:
                # This will leak context changes
                set_logging_context(**kwargs)
                return await func(*w_args, **w_kwargs)
        return wrapped
    return decorator


# For backwards compatibility
log_wrap = with_log_ctx


def persist_task(task_collection: set):
    """
    Coroutine decorator that ensures the coroutine is scheduled as a task
    and added to the given task_collection for strong reference
    when it is called.

    This is just a hack to handle discord.py events potentially
    being unexpectedly garbage collected.

    Since this also implicitly schedules the coroutine as a task when it is called,
    the coroutine will also be run inside an isolated context.
    """
    def decorator(coro):
        @wraps(coro)
        async def wrapped(*w_args, **w_kwargs):
            name = f"persisted-{coro.__name__}"
            task = asyncio.create_task(coro(*w_args, **w_kwargs), name=name)
            task_collection.add(task)
            task.add_done_callback(lambda f: task_collection.discard(f))
            await task


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


log_format = ('%(green)%(asctime)-19s%(reset)|%(red)%(levelname)-8s%(reset)|' +
              '%(cyan)%(app)-15s%(reset)|' +
              '%(cyan)%(context)-24s%(reset)|' +
              '%(cyan)%(actionstr)-22s%(reset)|' +
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
    def __init__(self, webhook_url, prefix="", batch=False, loop=None):
        super().__init__()
        self.webhook_url = webhook_url
        self.prefix = prefix
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
        self.format(record)
        self.get_loop().call_soon_threadsafe(self._post, record)

    def _post(self, record):
        asyncio.create_task(self.post(record))

    async def post(self, record):
        log_context.set("Webhook Logger")
        log_action_stack.set(("Logging",))
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
            if as_file or len(message) > 1900:
                with StringIO(message) as fp:
                    fp.seek(0)
                    await webhook.send(
                        f"{self.prefix}\n`{message.splitlines()[0]}`",
                        file=File(fp, filename="logs.md"),
                        username=log_app.get()
                    )
            else:
                await webhook.send(self.prefix + '\n' + message, username=log_app.get())


handlers = []
if webhook := conf.logging['general_log']:
    handler = WebHookHandler(webhook, batch=True)
    handlers.append(handler)

if webhook := conf.logging['error_log']:
    handler = WebHookHandler(webhook, prefix=conf.logging['error_prefix'], batch=False)
    handler.setLevel(logging.ERROR)
    handlers.append(handler)

if webhook := conf.logging['critical_log']:
    handler = WebHookHandler(webhook, prefix=conf.logging['critical_prefix'], batch=False)
    handler.setLevel(logging.CRITICAL)
    handlers.append(handler)


def make_queue_handler(queue):
    qhandler = QueueHandler(queue)
    qhandler.setLevel(logging.INFO)
    qhandler.addFilter(ContextInjection())
    return qhandler


def setup_main_logger(multiprocess=False):
    q = multiprocessing.Queue() if multiprocess else queue.SimpleQueue()
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

        qhandler = make_queue_handler(q)
        # qhandler.addFilter(ThreadFilter('MainThread'))
        logger.addHandler(qhandler)

        listener = QueueListener(
            q, *handlers, respect_handler_level=True
        )
        listener.start()
    return q

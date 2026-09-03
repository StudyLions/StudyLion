import sys
import logging
import asyncio
# --- AI-MODIFIED (2026-09-03) ---
# Purpose: monotonic clock for the webhook-logger circuit breaker below
import time
# --- END AI-MODIFIED ---
from typing import List, Optional
from logging.handlers import QueueListener, QueueHandler
import queue
import multiprocessing
from contextlib import contextmanager
from io import StringIO
from functools import wraps
from contextvars import ContextVar

import discord
from discord import Webhook, File
import aiohttp

from .config import conf
from . import sharding
from .context import context
from utils.lib import utc_now
from utils.ratelimits import Bucket, BucketOverFull, BucketFull


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

class ExactLevelFilter(logging.Filter):
    def __init__(self, target_level, name=""):
        super().__init__(name)
        self.target_level = target_level

    def filter(self, record):
        return (record.levelno == self.target_level)


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
    # --- AI-MODIFIED (2026-09-03) ---
    # Purpose: Process-wide circuit breaker for Discord webhook logging.
    # During the 2026-09-03 outage (PostgreSQL was OOM-killed) every event errored,
    # and each webhook handler on all 32 shards kept retrying failed sends. That
    # flood tripped Discord's Cloudflare IP ban ("blocked from accessing our API")
    # and then kept it alive for 90+ minutes. Now, when ANY handler in this process
    # receives a 429, ALL handlers stop sending for a cooldown that doubles per
    # consecutive 429 (5 min -> 10 -> 20 -> 40 -> capped at 60 min). A successful
    # send resets the backoff to 5 min. Dropped sends are counted, not queued.
    # Only 429s WITHOUT a 'Via' header (i.e. from Cloudflare, not Discord's API layer)
    # open the process-wide breaker; an ordinary per-webhook 429 (Via present, already
    # retried 5x inside discord.py) only pauses that one handler for 60s.
    # Sends are serialised per handler (see _send), so at most one send per handler
    # can be in flight when the breaker opens; its 429 is counted as dropped and does
    # NOT escalate the backoff again.
    _circuit_open_until = 0.0
    _circuit_backoff = 300
    _circuit_dropped = 0
    # --- END AI-MODIFIED ---

    def __init__(self, webhook_url, prefix="", batch=True, loop=None):
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

        self.bucket = Bucket(20, 40)
        self.ignored = 0
        # --- AI-MODIFIED (2026-09-03) ---
        # Purpose: per-handler pause used for route-level (Via) 429s, see _send();
        # _send_lock serialises this handler's sends (created lazily on the loop thread)
        self._handler_open_until = 0.0
        self._send_lock = None
        self._send_waiting = 0
        # --- END AI-MODIFIED ---

        self.session = None
        self.webhook = None

    def get_loop(self):
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        return self.loop

    def emit(self, record):
        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Temporary debug tracing for webhook error handler investigation
        # (2026-09-03: disabled - this per-record print multiplied stderr volume during incidents)
        # if record.levelno >= logging.ERROR:
        #     print(f"[WEBHOOK-DEBUG] emit() received ERROR+ record: level={record.levelno} msg={record.msg[:80]!r} handler_level={self.level} webhook_id={self.webhook_url.split('/')[-2] if self.webhook_url else 'N/A'}", file=sys.stderr)
        # --- END AI-MODIFIED ---
        self.format(record)
        self.get_loop().call_soon_threadsafe(self._post, record)

    def _post(self, record):
        if self.session is None:
            self.setup()
        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Temporary debug tracing for webhook error handler investigation
        # (2026-09-03: disabled - this per-record print multiplied stderr volume during incidents)
        # if record.levelno >= logging.ERROR:
        #     print(f"[WEBHOOK-DEBUG] _post() processing ERROR+ record: level={record.levelno} msg={record.msg[:80]!r} batch={self.batch} batched_len={len(self.batched)}", file=sys.stderr)
        # --- END AI-MODIFIED ---
        asyncio.create_task(self.post(record))

    def setup(self):
        # --- AI-REPLACED (2026-09-03) ---
        # Reason: aiohttp's default total timeout is 300s; a hung connection would hold
        #         this handler's send lock (see _send) for five minutes per attempt.
        # What the new code does better: caps each webhook HTTP call at 30s.
        # --- Original code (commented out for rollback) ---
        # self.session = aiohttp.ClientSession()
        # --- End original code ---
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        # --- END AI-REPLACED ---
        self.webhook = Webhook.from_url(self.webhook_url, session=self.session)

    async def post(self, record):
        if record.context == 'Webhook Logger':
            # Don't livelog livelog errors
            # Otherwise we recurse and Cloudflare hates us
            return
        log_context.set("Webhook Logger")
        log_action_stack.set(("Logging",))
        log_app.set(record.app)

        try:
            timestamp = utc_now().strftime("%d/%m/%Y, %H:%M:%S")
            header = f"[{record.asctime}][{record.levelname}][{record.app}][{record.actionstr}] <{record.context}>"
            context = f"\n# Context: {record.ctx}" if record.ctx else ""
            message = f"{header}\n{record.msg}{context}"

            # --- AI-MODIFIED (2026-04-01) ---
            # Purpose: Temporary debug tracing for webhook error handler investigation
            # (2026-09-03: disabled - per-record debug print)
            # if record.levelno >= logging.ERROR:
            #     print(f"[WEBHOOK-DEBUG] post() formatting: msg_len={len(message)} as_file={len(message) > 1900} batch={self.batch}", file=sys.stderr)
            # --- END AI-MODIFIED ---

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
                    # --- AI-MODIFIED (2026-04-01) ---
                    # Purpose: Temporary debug tracing for webhook error handler investigation
                    # (2026-09-03: disabled - per-record debug print)
                    # if record.levelno >= logging.ERROR:
                    #     print(f"[WEBHOOK-DEBUG] post() batched: batched_len={len(self.batched)} check={len(self.batched) + len(message)} > 1500 = {len(self.batched) + len(message) > 1500}", file=sys.stderr)
                    # --- END AI-MODIFIED ---
                    if len(self.batched) + len(message) > 1500:
                        await self._send_batched_now()
                    else:
                        asyncio.create_task(self._schedule_batched())
            else:
                await self._send(message, as_file=as_file)
        except Exception as ex:
            print(f"Unexpected error occurred while logging to webhook: {repr(ex)}", file=sys.stderr)

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
            print(f"Unexpected error occurred while scheduling batched webhook log: {repr(ex)}", file=sys.stderr)

    async def _send_batched_now(self):
        if self.batch_task is not None and not self.batch_task.done():
            self.batch_task.cancel()
        self.last_batched = None
        await self._send_batched()

    async def _send_batched(self):
        if self.batched:
            batched = self.batched
            self.batched = ""
            # --- AI-MODIFIED (2026-04-01) ---
            # Purpose: Temporary debug tracing for webhook error handler investigation
            # (2026-09-03: disabled - per-record debug print)
            # if 'ERROR' in batched[:200]:
            #     print(f"[WEBHOOK-DEBUG] _send_batched() flushing: len={len(batched)}", file=sys.stderr)
            # --- END AI-MODIFIED ---
            await self._send(batched)

    # --- AI-MODIFIED (2026-09-03) ---
    # Purpose: Circuit-breaker gate around the original send logic (now _send_inner).
    # Sends are serialised per handler so that when the send ahead of us gets a 429
    # and opens the breaker, everything queued behind it is dropped instead of still
    # going out one by one through discord.py's per-webhook lock.
    def _breaker_open(self):
        _now = time.monotonic()
        return _now < WebHookHandler._circuit_open_until or _now < self._handler_open_until

    async def _send(self, message, as_file=False):
        if self._breaker_open():
            WebHookHandler._circuit_dropped += 1
            return
        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        # Bound the queue on the lock. Before the lock existed, Bucket(20, 40) capped
        # how many sends could pile up behind a slow webhook call; keep that bound
        # here so a hung/slow send can never accumulate thousands of parked tasks.
        # (_send_waiting counts the holder plus waiters; the lock state itself is not
        #  consulted because locked() is briefly False in the release window.)
        if self._send_waiting >= 20:
            WebHookHandler._circuit_dropped += 1
            return
        self._send_waiting += 1
        try:
            async with self._send_lock:
                # Re-check after waiting for the lock: the send ahead of us may have
                # just opened the breaker or paused this handler.
                if self._breaker_open():
                    WebHookHandler._circuit_dropped += 1
                    return
                await self._send_inner(message, as_file=as_file)
        finally:
            self._send_waiting -= 1
    # --- END AI-MODIFIED ---

    async def _send_inner(self, message, as_file=False):
        # (2026-09-03: this is the original body of _send, unchanged apart from the
        #  except/else block below; it is only ever called under _send_lock.)
        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Temporary debug tracing for webhook error handler investigation
        # (2026-09-03: disabled - per-record debug print)
        # if 'ERROR' in message[:200]:
        #     print(f"[WEBHOOK-DEBUG] _send() called: msg_len={len(message)} as_file={as_file} webhook_id={getattr(self.webhook, 'id', 'N/A')}", file=sys.stderr)
        # --- END AI-MODIFIED ---
        try:
            self.bucket.request()
        except BucketOverFull:
            # Silently ignore
            self.ignored += 1
            # --- AI-MODIFIED (2026-04-01) ---
            # Purpose: Temporary debug tracing for webhook error handler investigation
            # (2026-09-03: disabled - per-record debug print)
            # print(f"[WEBHOOK-DEBUG] _send() BucketOverFull! ignored={self.ignored}", file=sys.stderr)
            # --- END AI-MODIFIED ---
            return
        except BucketFull:
            logger.warning(
                "Can't keep up! "
                f"Ignoring records on live-logger {self.webhook.id}."
            )
            self.ignored += 1
            return
        else:
            if self.ignored > 0:
                logger.warning(
                    "Can't keep up! "
                    f"{self.ignored} live logging records on webhook {self.webhook.id} skipped, continuing."
                )
                self.ignored = 0

        try:
            if as_file or len(message) > 1900:
                with StringIO(message) as fp:
                    fp.seek(0)
                    await self.webhook.send(
                        f"{self.prefix}\n`{message.splitlines()[0]}`",
                        file=File(fp, filename="logs.md"),
                        username=log_app.get()
                    )
            else:
                await self.webhook.send(self.prefix + '\n' + message, username=log_app.get())
        # --- AI-REPLACED (2026-09-03) ---
        # Reason: a 429 (including Discord's Cloudflare IP ban) must open the process-wide
        #         circuit breaker; bucket.fill() alone only paused this one handler for ~2s,
        #         so 32 shards x 3 handlers kept re-triggering the ban on 2026-09-03.
        # What the new code does better: one 429 silences every webhook handler in this
        #         process for 5+ min (doubling per consecutive 429, max 60 min) and prints a
        #         single stderr line instead of a full traceback per attempt. A successful send
        #         resets the backoff. Non-429 HTTP errors keep the original behaviour.
        # --- Original code (commented out for rollback) ---
        # except discord.HTTPException:
        #     logger.exception(
        #         "Live logger errored. Slowing down live logger."
        #     )
        #     self.bucket.fill()
        # --- End original code ---
        except discord.HTTPException as ex:
            self.bucket.fill()
            if ex.status == 429:
                cls = WebHookHandler
                now = time.monotonic()
                try:
                    via = ex.response.headers.get('Via')
                except Exception:
                    via = None
                if via:
                    # Route-level rate limit from Discord itself (discord.py already
                    # slept/retried 5x). Pause only this handler; the process keeps logging.
                    self._handler_open_until = now + 60
                    print(
                        f"[Webhook Logger] webhook {getattr(self.webhook, 'id', '?')} still rate "
                        f"limited after retries; pausing this handler for 60s",
                        file=sys.stderr,
                    )
                elif now >= cls._circuit_open_until:
                    # First IP-level (Cloudflare) 429 of this window: open the breaker.
                    cooldown = cls._circuit_backoff
                    cls._circuit_open_until = now + cooldown
                    cls._circuit_backoff = min(cooldown * 2, 3600)
                    print(
                        f"[Webhook Logger] Discord returned 429 ({(ex.text or '')[:120]!r}); "
                        f"suspending ALL webhook logging in this process for {cooldown}s "
                        f"(sends dropped so far: {cls._circuit_dropped})",
                        file=sys.stderr,
                    )
                else:
                    # Straggler: this send was dispatched before the breaker opened.
                    # The opener already escalated; do not double again.
                    cls._circuit_dropped += 1
            else:
                logger.exception(
                    "Live logger errored. Slowing down live logger."
                )
        else:
            # Successful send while the breaker is closed: reset the backoff floor.
            # (A success arriving while it is open is an in-flight straggler; ignore it
            # so it cannot undo the escalation that just happened.)
            if time.monotonic() >= WebHookHandler._circuit_open_until:
                WebHookHandler._circuit_backoff = 300
        # --- END AI-REPLACED ---


handlers = []
if webhook := conf.logging['general_log']:
    handler = WebHookHandler(webhook, batch=True)
    handlers.append(handler)
    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Temporary debug tracing for webhook error handler investigation
    print(f"[WEBHOOK-DEBUG] Created general_log handler: webhook_id={webhook.split('/')[-2]}", file=sys.stderr)
    # --- END AI-MODIFIED ---

if webhook := conf.logging['warning_log']:
    handler = WebHookHandler(webhook, prefix=conf.logging['warning_prefix'], batch=True)
    handler.addFilter(ExactLevelFilter(logging.WARNING))
    handler.setLevel(logging.WARNING)
    handlers.append(handler)
    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Temporary debug tracing for webhook error handler investigation
    print(f"[WEBHOOK-DEBUG] Created warning_log handler: webhook_id={webhook.split('/')[-2]} level={handler.level}", file=sys.stderr)
    # --- END AI-MODIFIED ---

if webhook := conf.logging['error_log']:
    handler = WebHookHandler(webhook, prefix=conf.logging['error_prefix'], batch=True)
    handler.setLevel(logging.ERROR)
    handlers.append(handler)
    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Temporary debug tracing for webhook error handler investigation
    print(f"[WEBHOOK-DEBUG] Created error_log handler: webhook_id={webhook.split('/')[-2]} level={handler.level} prefix={conf.logging['error_prefix']!r}", file=sys.stderr)
    # --- END AI-MODIFIED ---
else:
    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Temporary debug tracing for webhook error handler investigation
    print(f"[WEBHOOK-DEBUG] ERROR: error_log webhook is EMPTY/FALSY! conf.logging section keys: {list(conf.logging.keys())}", file=sys.stderr)
    # --- END AI-MODIFIED ---

if webhook := conf.logging['critical_log']:
    handler = WebHookHandler(webhook, prefix=conf.logging['critical_prefix'], batch=False)
    handler.setLevel(logging.CRITICAL)
    handlers.append(handler)

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Temporary debug tracing for webhook error handler investigation
print(f"[WEBHOOK-DEBUG] Total handlers created: {len(handlers)}", file=sys.stderr)

import threading
def _delayed_error_test():
    import time
    time.sleep(10)
    test_logger = logging.getLogger('webhook_test')
    test_logger.error("[WEBHOOK-TEST] This is a deliberate ERROR-level test message to verify webhook pipeline")
    test_logger.warning("[WEBHOOK-TEST] This is a deliberate WARNING-level test message to verify webhook pipeline")
    print("[WEBHOOK-DEBUG] Deliberate test messages sent (ERROR + WARNING)", file=sys.stderr)

threading.Thread(target=_delayed_error_test, daemon=True).start()
# --- END AI-MODIFIED ---


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

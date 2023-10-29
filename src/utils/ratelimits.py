import asyncio
import time
import logging

from meta.errors import SafeCancellation

from cachetools import TTLCache

logger = logging.getLogger()



class BucketFull(Exception):
    """
    Throw when a requested Bucket is already full
    """
    pass


class BucketOverFull(BucketFull):
    """
    Throw when a requested Bucket is overfull
    """
    pass


class Bucket:
    __slots__ = ('max_level', 'empty_time', 'leak_rate', '_level', '_last_checked', '_last_full', '_wait_lock')

    def __init__(self, max_level, empty_time):
        self.max_level = max_level
        self.empty_time = empty_time
        self.leak_rate = max_level / empty_time

        self._level = 0
        self._last_checked = time.monotonic()

        self._last_full = False
        self._wait_lock = asyncio.Lock()

    @property
    def full(self) -> bool:
        """
        Return whether the bucket is 'full',
        that is, whether an immediate request against the bucket will raise `BucketFull`.
        """
        self._leak()
        return self._level + 1 > self.max_level

    @property
    def overfull(self):
        self._leak()
        return self._level > self.max_level

    @property
    def delay(self):
        self._leak()
        if self._level + 1 > self.max_level:
            delay = (self._level + 1 - self.max_level) * self.leak_rate
        else:
            delay = 0
        return delay

    def _leak(self):
        if self._level:
            elapsed = time.monotonic() - self._last_checked
            self._level = max(0, self._level - (elapsed * self.leak_rate))

        self._last_checked = time.monotonic()

    def request(self):
        self._leak()
        if self._level > self.max_level:
            raise BucketOverFull
        elif self._level == self.max_level:
            self._level += 1
            if self._last_full:
                raise BucketOverFull
            else:
                self._last_full = True
                raise BucketFull
        else:
            self._last_full = False
            self._level += 1

    def fill(self):
        self._leak()
        self._level = max(self._level, self.max_level + 1)

    async def wait(self):
        """
        Wait until the bucket has room.

        Guarantees that a `request` directly afterwards will not raise `BucketFull`.
        """
        # Wrapped in a lock so that waiters are correctly handled in wait-order
        # Otherwise multiple waiters will have the same delay,
        # and race for the wakeup after sleep.
        # Also avoids short-circuiting in the 0 delay case, which would not correctly handle wait-order
        async with self._wait_lock:
            # We do this in a loop in case asyncio.sleep throws us out early,
            # or a synchronous request overflows the bucket while we are waiting.
            while self.full:
                await asyncio.sleep(self.delay)

    async def wrapped(self, coro):
        await self.wait()
        self.request()
        await coro


class RateLimit:
    def __init__(self, max_level, empty_time, error=None, cache=TTLCache(1000, 60 * 60)):
        self.max_level = max_level
        self.empty_time = empty_time

        self.error = error or "Too many requests, please slow down!"
        self.buckets = cache

    def request_for(self, key):
        if not (bucket := self.buckets.get(key, None)):
            bucket = self.buckets[key] = Bucket(self.max_level, self.empty_time)

        try:
            bucket.request()
        except BucketOverFull:
            raise SafeCancellation(details="Bucket overflow")
        except BucketFull:
            raise SafeCancellation(self.error, details="Bucket full")

    def ward(self, member=True, key=None):
        """
        Command ratelimit decorator.
        """
        key = key or ((lambda ctx: (ctx.guild.id, ctx.author.id)) if member else (lambda ctx: ctx.author.id))

        def decorator(func):
            async def wrapper(ctx, *args, **kwargs):
                self.request_for(key(ctx))
                return await func(ctx, *args, **kwargs)
            return wrapper
        return decorator


async def limit_concurrency(aws, limit):
    """
    Run provided awaitables concurrently,
    ensuring that no more than `limit` are running at once.
    """
    aws = iter(aws)
    aws_ended = False
    pending = set()
    count = 0
    logger.debug("Starting limited concurrency executor")

    while pending or not aws_ended:
        while len(pending) < limit and not aws_ended:
            aw = next(aws, None)
            if aw is None:
                aws_ended = True
            else:
                pending.add(asyncio.create_task(aw))
                count += 1

        if not pending:
            break

        done, pending = await asyncio.wait(
            pending, return_when=asyncio.FIRST_COMPLETED
        )
        while done:
            yield done.pop()
    logger.debug(f"Completed {count} tasks")

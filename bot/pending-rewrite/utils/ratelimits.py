import time
from cmdClient.lib import SafeCancellation

from cachetools import TTLCache


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
    __slots__ = ('max_level', 'empty_time', 'leak_rate', '_level', '_last_checked', '_last_full')

    def __init__(self, max_level, empty_time):
        self.max_level = max_level
        self.empty_time = empty_time
        self.leak_rate = max_level / empty_time

        self._level = 0
        self._last_checked = time.time()

        self._last_full = False

    @property
    def overfull(self):
        self._leak()
        return self._level > self.max_level

    def _leak(self):
        if self._level:
            elapsed = time.time() - self._last_checked
            self._level = max(0, self._level - (elapsed * self.leak_rate))

        self._last_checked = time.time()

    def request(self):
        self._leak()
        if self._level + 1 > self.max_level + 1:
            raise BucketOverFull
        elif self._level + 1 > self.max_level:
            self._level += 1
            if self._last_full:
                raise BucketOverFull
            else:
                self._last_full = True
                raise BucketFull
        else:
            self._last_full = False
            self._level += 1


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

import asyncio
import itertools
import datetime as dt

from utils.ratelimits import Bucket


def time_to_slotid(time: dt.datetime) -> int:
    """
    Return the slotid for the provided time.
    """
    utctime = time.astimezone(dt.timezone.utc)
    hour = utctime.replace(minute=0, second=0, microsecond=0)
    return int(hour.timestamp())


def slotid_to_utc(sessionid: int) -> dt.datetime:
    """
    Convert the given slotid (hour EPOCH) into a utc datetime.
    """
    return dt.datetime.fromtimestamp(sessionid, tz=dt.timezone.utc)


async def batchrun_per_second(awaitables, batchsize):
    """
    Run provided awaitables concurrently,
    ensuring that no more than `batchsize` are running at once,
    and that no more than `batchsize` are spawned per second.

    Returns list of returned results or exceptions.
    """
    bucket = Bucket(batchsize, 1)
    sem = asyncio.Semaphore(batchsize)

    tasks = []
    for awaitable in awaitables:
        await asyncio.gather(bucket.wait(), sem.acquire())
        bucket.request()
        task = asyncio.create_task(awaitable)
        task.add_done_callback(lambda fut: sem.release())
    return await asyncio.gather(*tasks, return_exceptions=True)

import asyncio
import bisect
import logging
from typing import TypeVar, Generic, Optional, Callable, Coroutine, Any

from .lib import utc_now
from .ratelimits import Bucket


logger = logging.getLogger(__name__)

Taskid = TypeVar('Taskid')


class TaskMonitor(Generic[Taskid]):
    """
    Base class for a task monitor.

    Stores tasks as a time-sorted list of taskids.
    Subclasses may override `run_task` to implement an executor.

    Adding or removing a single task has O(n) performance.
    To bulk update tasks, instead use `schedule_tasks`.

    Each taskid must be unique and hashable.
    """

    def __init__(self, executor=None, bucket: Optional[Bucket] = None):
        # Ratelimit bucket to enforce maximum execution rate
        self._bucket = bucket

        self.executor: Optional[Callable[[Taskid], Coroutine[Any, Any, None]]] = executor

        self._wakeup: asyncio.Event = asyncio.Event()
        self._monitor_task: Optional[asyncio.Task] = None

        # Task data
        self._tasklist: list[Taskid] = []
        self._taskmap: dict[Taskid, int] = {}  # taskid -> timestamp

        # Running map ensures we keep a reference to the running task
        # And allows simpler external cancellation if required
        self._running: dict[Taskid, asyncio.Future] = {}

    def __repr__(self):
        return (
            "<"
                f"{self.__class__.__name__}"
                f" tasklist={len(self._tasklist)}"
                f" taskmap={len(self._taskmap)}"
                f" wakeup={self._wakeup.is_set()}"
                f" bucket={self._bucket}"
                f" running={len(self._running)}"
                f" task={self._monitor_task}"
                f">"
        )

    def set_tasks(self, *tasks: tuple[Taskid, int]) -> None:
        """
        Similar to `schedule_tasks`, but wipe and reset the tasklist.
        """
        self._taskmap = {tid: time for tid, time in tasks}
        self._tasklist = list(sorted(self._taskmap.keys(), key=lambda tid: -1 * self._taskmap[tid]))
        self._wakeup.set()

    def schedule_tasks(self, *tasks: tuple[Taskid, int]) -> None:
        """
        Schedule the given tasks.

        Rather than repeatedly inserting tasks,
        where the O(log n) insort is dominated by the O(n) list insertion,
        we build an entirely new list, and always wake up the loop.
        """
        self._taskmap |= {tid: time for tid, time in tasks}
        self._tasklist = list(sorted(self._taskmap.keys(), key=lambda tid: -1 * self._taskmap[tid]))
        self._wakeup.set()

    def schedule_task(self, taskid: Taskid, timestamp: int) -> None:
        """
        Insert the provided task into the tasklist.
        If the new task has a lower timestamp than the next task, wakes up the monitor loop.
        """
        if self._tasklist:
            nextid = self._tasklist[-1]
            wake = self._taskmap[nextid] >= timestamp
            wake = wake or taskid == nextid
        else:
            wake = True
        if taskid in self._taskmap:
            self._tasklist.remove(taskid)
        self._taskmap[taskid] = timestamp
        bisect.insort_left(self._tasklist, taskid, key=lambda t: -1 * self._taskmap[t])
        if wake:
            self._wakeup.set()

    def cancel_tasks(self, *taskids: Taskid) -> None:
        """
        Remove all tasks with the given taskids from the tasklist.
        If the next task has this taskid, wake up the monitor loop.
        """
        taskids = set(taskids)
        wake = (self._tasklist and self._tasklist[-1] in taskids)
        self._tasklist = [tid for tid in self._tasklist if tid not in taskids]
        for tid in taskids:
            self._taskmap.pop(tid, None)
        if wake:
            self._wakeup.set()

    def start(self):
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        # Start the monitor
        self._monitor_task = asyncio.create_task(self.monitor())
        return self._monitor_task

    async def monitor(self):
        """
        Start the monitor.
        Executes the tasks in `self.tasks` at the specified time.

        This will shield task execution from cancellation
        to avoid partial states.
        """
        try:
            while True:
                self._wakeup.clear()
                if not self._tasklist:
                    # No tasks left, just sleep until wakeup
                    await self._wakeup.wait()
                else:
                    # Get the next task, sleep until wakeup or it is ready to run
                    nextid = self._tasklist[-1]
                    nexttime = self._taskmap[nextid]
                    sleep_for = nexttime - utc_now().timestamp()
                    try:
                        await asyncio.wait_for(self._wakeup.wait(), timeout=sleep_for)
                    except asyncio.TimeoutError:
                        # Ready to run the task
                        self._tasklist.pop()
                        self._taskmap.pop(nextid, None)
                        self._running[nextid] = asyncio.ensure_future(self._run(nextid))
                    else:
                        # Wakeup task fired, loop again
                        continue
        except asyncio.CancelledError:
            # Log closure and wait for remaining tasks
            # A second cancellation will also cancel the tasks
            logger.debug(
                f"Task Monitor {self.__class__.__name__} cancelled with {len(self._tasklist)} tasks remaining. "
                f"Waiting for {len(self._running)} running tasks to complete."
            )
            await asyncio.gather(*self._running.values(), return_exceptions=True)

    async def _run(self, taskid: Taskid) -> None:
        # Execute the task, respecting the ratelimit bucket
        if self._bucket is not None:
            # IMPLEMENTATION NOTE:
            # Bucket.wait() should guarantee not more than n tasks/second are run
            # and that a request directly afterwards will _not_ raise BucketFull
            # Make sure that only one waiter is actually waiting on its sleep task
            # The other waiters should be waiting on a lock around the sleep task
            # Waiters are executed in wait-order, so if we only let a single waiter in
            # we shouldn't get collisions.
            # Furthermore, make sure we do _not_ pass back to the event loop after waiting
            # Or we will lose thread-safety for BucketFull
            await self._bucket.wait()
        fut = asyncio.create_task(self.run_task(taskid))
        try:
            await asyncio.shield(fut)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Protect the monitor loop from any other exceptions
            logger.exception(
                f"Ignoring exception in task monitor {self.__class__.__name__} while "
                f"executing <taskid: {taskid}>"
            )
        finally:
            self._running.pop(taskid)

    async def run_task(self, taskid: Taskid):
        """
        Execute the task with the given taskid.

        Default implementation executes `self.executor` if it exists,
        otherwise raises NotImplementedError.
        """
        if self.executor is not None:
            await self.executor(taskid)
        else:
            raise NotImplementedError

from typing import Optional
from weakref import WeakValueDictionary
import re

from meta import LionBot
from meta.errors import UserInputError
from utils.lib import utc_now

from .data import TasklistData


class Tasklist:
    """
    Class representing a single user's tasklist.

    Attributes
    ----------
    bot: LionBot
        Client which controls this tasklist.
    data: TasklistData
        Initialised tasklist data registry.
    userid: int
        The user who owns this tasklist.
    tasklist: dict[int, TasklistData.Task]
        A local cache map of tasks the user owns.
        May or may not contain deleted tasks.
    """
    _cache_ = WeakValueDictionary()

    label_range_re = re.compile(
        r"^(?P<start>(\d+\.)*\d+)\.?((\s*(?P<range>-)\s*)(?P<end>(\d+\.)*\d*\.?))?$"
    )

    def __init__(self, bot: LionBot, data: TasklistData, userid: int):
        self.bot = bot
        self.data = data
        self.userid = userid

        self.tasklist: dict[int, TasklistData.Task] = {}

    @classmethod
    async def fetch(cls, bot: LionBot, data: TasklistData, userid: int) -> 'Tasklist':
        """
        Fetch and initialise a Tasklist, using cache where possible.
        """
        if userid not in cls._cache_:
            cls = cls(bot, data, userid)
            await cls.refresh()
            cls._cache_[userid] = cls
        return cls._cache_[userid]

    def _label(self, task, taskmap, labels, counters) -> tuple[int, ...]:
        tid = task.taskid

        if tid in labels:
            label = labels[tid]
        else:
            pid = task.parentid
            counters[pid] = i = counters.get(pid, 0) + 1
            if pid is not None and (parent := taskmap.get(pid, None)) is not None:
                plabel = self._label(parent, taskmap, labels, counters)
            else:
                plabel = ()
            labels[tid] = label = (*plabel, i)
        return label

    @property
    def labelled(self) -> dict[tuple[int, ...], TasklistData.Task]:
        """
        A sorted map of task string ids to tasks.
        This is the tasklist that is visible to the user.
        """
        taskmap = {
            task.taskid: task
            for task in sorted(self.tasklist.values(), key=lambda t: t.taskid)
            if task.deleted_at is None
        }
        labels = {}
        counters = {}
        for task in taskmap.values():
            self._label(task, taskmap, labels, counters)
        labelmap = {
            label: taskmap[taskid]
            for taskid, label in sorted(labels.items(), key=lambda lt: lt[1])
        }
        return labelmap

    def labelid(self, taskid) -> Optional[tuple[int, ...]]:
        """
        Relatively expensive method to get the label for a given task, if it exists.
        """
        task = self.tasklist.get(taskid, None)
        if task is None:
            return None

        labelled = self.labelled
        mapper = {t.taskid: label for label, t in labelled.items()}
        return mapper[taskid]

    async def refresh(self):
        """
        Update the `tasklist` from data.
        """
        tasks = await self.data.Task.fetch_where(userid=self.userid, deleted_at=None)
        self.tasklist = {task.taskid: task for task in tasks}

    async def _owner_check(self, *taskids: int) -> bool:
        """
        Check whether all of the given tasks are owned by this tasklist user.

        Applies cache where possible.
        """
        missing = [tid for tid in taskids if tid not in self.tasklist]
        if missing:
            missing = [tid for tid in missing if (tid, ) not in self.data.Task._cache_]
            if missing:
                tasks = await self.data.Task.fetch_where(taskid=missing)
                missing = [task.taskid for task in tasks if task.userid != self.userid]

        return not bool(missing)

    async def fetch_tasks(self, *taskids: int) -> list[TasklistData.Task]:
        """
        Fetch the tasks from the tasklist with the given taskids.

        Raises a ValueError if the tasks are not owned by the tasklist user.
        """
        # Check the tasklist user owns all the tasks
        # Also ensures the Row objects are in cache
        if not await self._owner_check(*taskids):
            raise ValueError("The given tasks are not in this tasklist!")
        return [await self.data.Task.fetch(tid) for tid in taskids]

    async def create_task(self, content: str, **kwargs) -> TasklistData.Task:
        """
        Create a new task with the given content.
        """
        task = await self.data.Task.create(userid=self.userid, content=content, **kwargs)
        self.tasklist[task.taskid] = task
        return task

    async def update_tasks(self, *taskids: int, cascade=False, **kwargs):
        """
        Update the given taskids with the provided new values.

        If `cascade` is True, also applies the updates to all children.
        """
        if not taskids:
            raise ValueError("No tasks provided to update.")

        if cascade:
            taskids = self.children_cascade(*taskids)

        # Ensure the taskids exist and belong to this user
        await self.fetch_tasks(*taskids)

        # Update the tasks
        kwargs.setdefault('last_updated_at', utc_now())
        tasks = await self.data.Task.table.update_where(
            userid=self.userid,
            taskid=taskids,
        ).set(**kwargs)

        # Return the updated tasks
        return tasks

    async def update_tasklist(self, **kwargs):
        """
        Update every task in the tasklist, regardless of cache.
        """
        kwargs.setdefault('last_updated_at', utc_now())
        tasks = await self.data.Task.table.update_where(userid=self.userid).set(**kwargs)

        return tasks

    def children_cascade(self, *taskids) -> list[int]:
        """
        Return the provided taskids with all their descendants.
        Only checks the current tasklist cache for descendants.
        """
        taskids = set(taskids)
        added = True
        while added:
            added = False
            for task in self.tasklist.values():
                if task.deleted_at is None and task.taskid not in taskids and task.parentid in taskids:
                    taskids.add(task.taskid)
                    added = True
        return list(taskids)

    def parse_label(self, labelstr: str) -> Optional[int]:
        """
        Parse a provided label string into a taskid, if it can be found.

        Returns None if no matching taskids are found.
        """
        splits = [s for s in labelstr.split('.') if s]
        if all(split.isdigit() for split in splits):
            tasks = self.labelled
            label = tuple(map(int, splits))
            if label in tasks:
                return tasks[label].taskid

    def format_label(self, label: tuple[int, ...]) -> str:
        """
        Format the provided label tuple into the standard number format.
        """
        return '.'.join(map(str, label)) + '.' * (len(label) == 1)

    def parse_labels(self, labelstr: str) -> Optional[list[str]]:
        """
        Parse a comma separated list of labels and label ranges into a list of labels.

        E.g. `1, 2, 3`, `1, 2-5, 7`, `1, 2.1, 3`, `1, 2.1-3`, `1, 2.1-`

        May raise `UserInputError`.
        """
        labelmap = {label: task.taskid for label, task in self.labelled.items()}

        splits = labelstr.split(',')
        splits = [split.strip(' ,.') for split in splits]
        splits = [split for split in splits if split]

        taskids = set()
        for split in splits:
            match = self.label_range_re.match(split)
            if match:
                start = match['start']
                ranged = match['range']
                end = match['end']

                start_label = tuple(map(int, start.split('.')))
                head = start_label[:-1]
                start_tail = start_label[-1]

                if end:
                    end_label = tuple(map(int, end.split('.')))
                    end_tail = end_label[-1]

                    if len(end_label) > 1 and head != end_label[:-1]:
                        # Error: Parents don't match in range ...
                        raise UserInputError("Parents don't match in range `{range}`")

                    for tail in range(max(start_tail, 1), end_tail + 1):
                        label = (*head, tail)
                        if label not in labelmap:
                            break
                        taskids.add(labelmap[label])
                elif ranged:
                    # No end but still ranged
                    for label, taskid in labelmap.items():
                        if (label[:-1] == head) and (label[-1] >= start_tail):
                            taskids.add(taskid)
                elif start_label in labelmap:
                    taskids.add(labelmap[start_label])
            else:
                # Error
                raise UserInputError("Could not parse `{range}` as a task number or range.")
        return list(taskids)

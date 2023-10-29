import logging
import asyncio
from enum import IntEnum
from collections import deque, ChainMap
import datetime as dt

logger = logging.getLogger(__name__)


class StatusLevel(IntEnum):
    ERRORED = -2
    UNSURE = -1
    WAITING = 0
    STARTING = 1
    OKAY = 2

    @property
    def symbol(self):
        return symbols[self]


symbols = {
    StatusLevel.ERRORED: '🟥',
    StatusLevel.UNSURE: '🟧',
    StatusLevel.WAITING: '⬜',
    StatusLevel.STARTING: '🟫',
    StatusLevel.OKAY: '🟩',
}


class ComponentStatus:
    def __init__(self, level: StatusLevel, short_formatstr: str, long_formatstr: str, data: dict = {}):
        self.level = level
        self.short_formatstr = short_formatstr
        self.long_formatstr = long_formatstr
        self.data = data
        self.created_at = dt.datetime.now(tz=dt.timezone.utc)

    def format_args(self):
        extra = {
            'created_at': self.created_at,
            'level': self.level,
            'symbol': self.level.symbol,
        }
        return ChainMap(extra, self.data)

    @property
    def short(self):
        return self.short_formatstr.format(**self.format_args())

    @property
    def long(self):
        return self.long_formatstr.format(**self.format_args())


class ComponentMonitor:
    _name = None

    def __init__(self, name=None, callback=None):
        self._callback = callback
        self.name = name or self._name
        if not self.name:
            raise ValueError("ComponentMonitor must have a name")

    async def _make_status(self, *args, **kwargs):
        if self._callback is not None:
            return await self._callback(*args, **kwargs)
        else:
            raise NotImplementedError

    async def status(self) -> ComponentStatus:
        try:
            status = await self._make_status()
        except Exception as e:
            logger.exception(
                f"Status callback for component '{self.name}' failed. This should not happen."
            )
            status = ComponentStatus(
                level=StatusLevel.UNSURE,
                short_formatstr="Status callback for '{name}' failed with error '{error}'",
                long_formatstr="Status callback for '{name}' failed with error '{error}'",
                data={
                    'name': self.name,
                    'error': repr(e)
                }
            )
        return status


class SystemMonitor:
    def __init__(self):
        self.components = {}
        self.recent = deque(maxlen=10)

    def add_component(self, component: ComponentMonitor):
        self.components[component.name] = component
        return component

    async def request(self):
        """
        Request status from each component.
        """
        tasks = {
            name: asyncio.create_task(comp.status())
            for name, comp in self.components.items()
        }
        await asyncio.gather(*tasks.values())
        status = {
            name: await fut for name, fut in tasks.items()
        }
        self.recent.append(status)
        return status

    async def _format_summary(self, status_dict: dict[str, ComponentStatus]):
        """
        Format a one line summary from a status dict.
        """
        freq = {level: 0 for level in StatusLevel}
        for status in status_dict.values():
            freq[status.level] += 1

        summary = '\t'.join(f"{level.symbol} {count}" for level, count in freq.items() if count)
        return summary

    async def _format_overview(self, status_dict: dict[str, ComponentStatus]):
        """
        Format an overview (one line per component) from a status dict.
        """
        lines = []
        for name, status in status_dict.items():
            lines.append(f"{status.level.symbol} {name}: {status.short}")
        summary = await self._format_summary(status_dict)
        return '\n'.join((summary, *lines))

    async def get_summary(self):
        return await self._format_summary(await self.request())

    async def get_overview(self):
        return await self._format_overview(await self.request())

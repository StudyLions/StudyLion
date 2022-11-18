from typing import Protocol, runtime_checkable, Optional

from psycopg import AsyncConnection

from .connector import Connector, Connectable


@runtime_checkable
class _Attachable(Connectable, Protocol):
    def attach_to(self, registry: 'Registry'):
        raise NotImplementedError


class Registry:
    _attached: list[_Attachable] = []
    _name: Optional[str] = None

    def __init_subclass__(cls, name=None):
        attached = []
        for _, member in cls.__dict__.items():
            if isinstance(member, _Attachable):
                attached.append(member)
        cls._attached = attached
        cls._name = name or cls.__name__

    def __init__(self, name=None):
        self._conn: Optional[Connector] = None
        self.name: str = name if name is not None else self._name
        if self.name is None:
            raise ValueError("A Registry must have a name!")

        self.init_tasks = []

        for member in self._attached:
            member.attach_to(self)

    def bind(self, connector: Connector):
        self._conn = connector
        for child in self._attached:
            child.bind(connector)

    def attach(self, attachable):
        self._attached.append(attachable)
        if self._conn is not None:
            attachable.bind(self._conn)
        return attachable

    def init_task(self, coro):
        """
        Initialisation tasks are run to setup the registry state.
        These tasks will be run in the event loop, after connection to the database.
        These tasks should be idempotent, as they may be run on reload and reconnect.
        """
        self.init_tasks.append(coro)
        return coro

    async def init(self):
        for task in self.init_tasks:
            await task(self)
        return self


class AttachableClass:
    """ABC for a default implementation of an Attachable class."""

    _connector: Optional[Connector] = None
    _registry: Optional[Registry] = None

    @classmethod
    def bind(cls, connector: Connector):
        cls._connector = connector
        connector.connect_hook(cls.on_connect)
        return cls

    @classmethod
    def attach_to(cls, registry: Registry):
        cls._registry = registry
        return cls

    @classmethod
    async def on_connect(cls, connection: AsyncConnection):
        pass


class Attachable:
    """ABC for a default implementation of an Attachable object."""

    def __init__(self, *args, **kwargs):
        self._connector: Optional[Connector] = None
        self._registry: Optional[Registry] = None

    def bind(self, connector: Connector):
        self._connector = connector
        connector.connect_hook(self.on_connect)
        return self

    def attach_to(self, registry: Registry):
        self._registry = registry
        return self

    async def on_connect(self, connection: AsyncConnection):
        pass

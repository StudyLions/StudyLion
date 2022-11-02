# from enum import Enum
from typing import Optional
from psycopg.types.enum import register_enum, EnumInfo
from .registry import Attachable, Registry


class RegisterEnum(Attachable):
    def __init__(self, enum, name: Optional[str] = None, mapper=None):
        super().__init__()
        self.enum = enum
        self.name = name or enum.__name__
        self.mapping = mapper(enum) if mapper is not None else self._mapper()

    def _mapper(self):
        return {m: m.value[0] for m in self.enum}

    def attach_to(self, registry: Registry):
        self._registry = registry
        registry.init_task(self.on_init)
        return self

    async def on_init(self, registry: Registry):
        connection = await registry._conn.get_connection()
        if connection is None:
            raise ValueError("Cannot Init without connection.")
        info = await EnumInfo.fetch(connection, self.name)
        if info is None:
            raise ValueError(f"Enum {self.name} not found in database.")
        register_enum(info, connection, self.enum, mapping=self.mapping)

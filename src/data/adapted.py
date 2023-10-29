# from enum import Enum
from typing import Optional
from psycopg.types.enum import register_enum, EnumInfo
from psycopg import AsyncConnection
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
        connector = registry._conn
        if connector is None:
            raise ValueError("Cannot initialise without connector!")
        connector.connect_hook(self.connection_hook)
        # await connector.refresh_pool()
        # The below may be somewhat dangerous
        # But adaption should never write to the database
        await connector.map_over_pool(self.connection_hook)
        # if conn := connector.conn:
        #     # Ensure the adaption is run in the current context as well
        #    await self.connection_hook(conn)

    async def connection_hook(self, conn: AsyncConnection):
        info = await EnumInfo.fetch(conn, self.name)
        if info is None:
            raise ValueError(f"Enum {self.name} not found in database.")
        register_enum(info, conn, self.enum, mapping=list(self.mapping.items()))

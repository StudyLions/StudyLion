from typing import TypeVar
import logging
from collections import namedtuple

# from .cursor import AsyncLoggingCursor
from .registry import Registry
from .connector import Connector


logger = logging.getLogger(__name__)

Version = namedtuple('Version', ('version', 'time', 'author'))

T = TypeVar('T', bound=Registry)


class Database(Connector):
    # cursor_factory = AsyncLoggingCursor

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.registries: dict[str, Registry] = {}

    def load_registry(self, registry: T) -> T:
        logger.debug(
            f"Loading and binding registry '{registry.name}'.",
            extra={'action': f"Reg {registry.name}"}
        )
        registry.bind(self)
        self.registries[registry.name] = registry
        return registry

    async def version(self) -> Version:
        """
        Return the current schema version as a Version namedtuple.
        """
        async with self.connection() as conn:
            async with conn.cursor() as cursor:
                # Get last entry in version table, compare against desired version
                await cursor.execute("SELECT * FROM VersionHistory ORDER BY time DESC LIMIT 1")
                row = await cursor.fetchone()
                if row:
                    return Version(row['version'], row['time'], row['author'])
                else:
                    # No versions in the database
                    return Version(-1, None, None)

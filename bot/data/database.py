import logging
from collections import namedtuple

# from .cursor import AsyncLoggingCursor
from .registry import Registry
from .connector import Connector


logger = logging.getLogger(__name__)

Version = namedtuple('Version', ('version', 'time', 'author'))


class Database(Connector):
    # cursor_factory = AsyncLoggingCursor

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.registries: dict[str, Registry] = {}

    def load_registry(self, registry: Registry):
        registry.bind(self)
        self.registries[registry.name] = registry

    async def version(self) -> Version:
        """
        Return the current schema version as a Version namedtuple.
        """
        async with self.conn.cursor() as cursor:
            # Get last entry in version table, compare against desired version
            await cursor.execute("SELECT * FROM VersionHistory ORDER BY time DESC LIMIT 1")
            row = await cursor.fetchone()
            if row:
                return Version(row['version'], row['time'], row['author'])
            else:
                # No versions in the database
                return Version(-1, None, None)

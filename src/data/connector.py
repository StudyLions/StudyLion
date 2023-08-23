from typing import Protocol, runtime_checkable, Callable, Awaitable, Optional
import logging

from contextvars import ContextVar
from contextlib import asynccontextmanager
import psycopg as psq
from psycopg_pool import AsyncConnectionPool
from psycopg.pq import TransactionStatus

from .cursor import AsyncLoggingCursor

logger = logging.getLogger(__name__)

row_factory = psq.rows.dict_row

ctx_connection: Optional[ContextVar[psq.AsyncConnection]] = ContextVar('connection', default=None)


class Connector:
    cursor_factory = AsyncLoggingCursor

    def __init__(self, conn_args):
        self._conn_args = conn_args
        self._conn_kwargs = dict(autocommit=True, row_factory=row_factory, cursor_factory=self.cursor_factory)

        self.pool = self.make_pool()

        self.conn_hooks = []

    @property
    def conn(self) -> Optional[psq.AsyncConnection]:
        """
        Convenience property for the current context connection.
        """
        return ctx_connection.get()

    @conn.setter
    def conn(self, conn: psq.AsyncConnection):
        """
        Set the contextual connection in the current context.
        Always do this in an isolated context!
        """
        ctx_connection.set(conn)

    def make_pool(self) -> AsyncConnectionPool:
        logger.info("Initialising connection pool.", extra={'action': "Pool Init"})
        return AsyncConnectionPool(
            self._conn_args,
            open=False,
            min_size=4,
            max_size=8,
            configure=self._setup_connection,
            kwargs=self._conn_kwargs
        )

    async def refresh_pool(self):
        """
        Refresh the pool.

        The point of this is to invalidate any existing connections so that the connection set up is run again.
        Better ways should be sought (a way to 
        """
        logger.info("Pool refresh requested, closing and reopening.")
        old_pool = self.pool
        self.pool = self.make_pool()
        await self.pool.open()
        logger.info(f"Old pool statistics: {self.pool.get_stats()}")
        await old_pool.close()
        logger.info("Pool refresh complete.")

    async def map_over_pool(self, callable):
        """
        Dangerous method to call a method on each connection in the pool.

        Utilises private methods of the AsyncConnectionPool.
        """
        async with self.pool._lock:
            conns = list(self.pool._pool)
        while conns:
            conn = conns.pop()
            try:
                await callable(conn)
            except Exception:
                logger.exception(f"Mapped connection task failed. {callable.__name__}")

    @asynccontextmanager
    async def open(self):
        try:
            logger.info("Opening database pool.")
            await self.pool.open()
            yield
        finally:
            # May be a different pool!
            logger.info(f"Closing database pool. Pool statistics: {self.pool.get_stats()}")
            await self.pool.close()

    @asynccontextmanager
    async def connection(self) -> psq.AsyncConnection:
        """
        Asynchronous context manager to get and manage a connection.

        If the context connection is set, uses this and does not manage the lifetime.
        Otherwise, requests a new connection from the pool and returns it when done.
        """
        logger.debug("Database connection requested.", extra={'action': "Data Connect"})
        if (conn := self.conn):
            yield conn
        else:
            async with self.pool.connection() as conn:
                yield conn

    async def _setup_connection(self, conn: psq.AsyncConnection):
        logger.debug("Initialising new connection.", extra={'action': "Conn Init"})
        for hook in self.conn_hooks:
            try:
                await hook(conn)
            except Exception:
                logger.exception("Exception encountered setting up new connection")
        return conn

    def connect_hook(self, coro: Callable[[psq.AsyncConnection], Awaitable[None]]):
        """
        Minimal decorator to register a coroutine to run on connect or reconnect.

        Note that these are only run on connect and reconnect.
        If a hook is registered after connection, it will not be run.
        """
        self.conn_hooks.append(coro)
        return coro


@runtime_checkable
class Connectable(Protocol):
    def bind(self, connector: Connector):
        raise NotImplementedError

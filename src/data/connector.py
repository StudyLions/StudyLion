from typing import Protocol, runtime_checkable, Callable, Awaitable
import logging

import psycopg as psq
from psycopg.pq import TransactionStatus

from .cursor import AsyncLoggingCursor

logger = logging.getLogger(__name__)

row_factory = psq.rows.dict_row


class Connector:
    cursor_factory = AsyncLoggingCursor

    def __init__(self, conn_args):
        self._conn_args = conn_args
        self.conn: psq.AsyncConnection = None

        self.conn_hooks = []

    async def get_connection(self) -> psq.AsyncConnection:
        """
        Get the current active connection.
        This should never be cached outside of a transaction.
        """
        # TODO: Reconnection logic?
        if not self.conn:
            raise ValueError("Attempting to get connection before initialisation!")
        if self.conn.info.transaction_status is TransactionStatus.INERROR:
            await self.connect()
            logger.error(
                "Database connection transaction failed!! This should not happen. Reconnecting."
            )
        return self.conn

    async def connect(self) -> psq.AsyncConnection:
        logger.info("Establishing connection to database.", extra={'action': "Data Connect"})
        self.conn = await psq.AsyncConnection.connect(
            self._conn_args, autocommit=True, row_factory=row_factory, cursor_factory=self.cursor_factory
        )
        for hook in self.conn_hooks:
            await hook(self.conn)
        return self.conn

    async def reconnect(self) -> psq.AsyncConnection:
        return await self.connect()

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

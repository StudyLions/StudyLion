import asyncio
import datetime
import logging
from collections import namedtuple
from typing import NamedTuple, Optional, Generic, Type, TypeVar

from meta.ipc import AppRoute, AppClient
from meta.logger import logging_context, log_wrap, set_logging_context

from data import RowModel
from .data import AnalyticsData, CommandStatus, VoiceAction, GuildAction


logger = logging.getLogger(__name__)

"""
TODO
Snapshot type? Incremental or manual?
Request snapshot route will require all shards to be online
Update batch size before release, or put it in the config
"""

T = TypeVar('T')


class EventHandler(Generic[T]):
    def __init__(self, route_name: str, model: Type[RowModel], struct: Type[T], batchsize: int = 20):
        self.model = model
        self.struct = struct

        self.batch_size = batchsize

        self.route_name = route_name
        self._route: Optional[AppRoute] = None
        self._client: Optional[AppClient] = None

        self.queue: asyncio.Queue[T] = asyncio.Queue()
        self.batch: list[T] = []
        self._consumer_task: Optional[asyncio.Task] = None

    @property
    def route(self):
        if self._route is None:
            self._route = AppRoute(self.handle_event, name=self.route_name)
        return self._route

    async def handle_event(self, data):
        try:
            await self.queue.put(data)
        except asyncio.QueueFull:
            logger.warning(
                f"Queue on event handler {self.route_name} is full! Discarding event {data}"
            )

    @log_wrap(action='consumer')
    async def consumer(self):
        while True:
            try:
                item = await self.queue.get()
                self.batch.append(item)
                if len(self.batch) > self.batch_size:
                    await self.process_batch()
            except asyncio.CancelledError:
                # Try and process the last batch
                logger.info(
                    f"Event handler {self.route_name} received cancellation signal! "
                    "Trying to process last batch."
                )
                if self.batch:
                    await self.process_batch()
                raise
            except Exception:
                logger.exception(
                    f"Event handler {self.route_name} received unhandled error."
                    " Ignoring and continuing cautiously."
                )
                pass

    @log_wrap(action='batch')
    async def process_batch(self):
        logger.debug("Processing Batch")
        # TODO: copy syntax might be more efficient here
        await self.model.table.insert_many(
            self.struct._fields,
            *map(tuple, self.batch)
        )
        self.batch.clear()

    def bind(self, client: AppClient):
        """
        Bind our route to the given client.
        """
        if self._client:
            raise ValueError("This EventHandler is already attached!")

        self._client = client
        self.route._client = client
        client.routes[self.route_name] = self.route
        return self

    def unbind(self):
        """
        Unbind from the client.
        """
        if not self._client:
            raise ValueError("Not attached, cannot detach!")
        self._client.routes.pop(self.route_name, None)
        self._route = None
        logger.info(
            f"EventHandler {self.route_name} has attached to the ShardTalk client."
        )
        return self

    async def attach(self, client: AppClient):
        """
        Attach to a ShardTalk client and start listening.
        """
        with logging_context(action=self.route_name):
            self.bind(client)
            self._consumer_task = asyncio.create_task(self.consumer())
            logger.info(
                f"EventHandler {self.route_name} is listening for incoming events."
            )
        return self

    async def detach(self):
        """
        Stop listening and detach from client.
        """
        self.unbind()
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            self._consumer_task = None
        logger.info(
            f"EventHandler {self.route_name} has detached."
        )
        return self


class CommandEvent(NamedTuple):
    appname: str
    cmdname: str
    userid: int
    created_at: datetime.datetime
    status: CommandStatus
    execution_time: float
    error: Optional[str] = None
    cogname: Optional[str] = None
    guildid: Optional[int] = None
    ctxid: Optional[int] = None


command_event_handler: EventHandler[CommandEvent] = EventHandler(
    'command_event', AnalyticsData.Commands, CommandEvent, batchsize=1
)


class GuildEvent(NamedTuple):
    appname: str
    guildid: int
    action: GuildAction
    created_at: datetime.datetime


guild_event_handler: EventHandler[GuildEvent] = EventHandler(
    'guild_event', AnalyticsData.Guilds, GuildEvent, batchsize=0
)


class VoiceEvent(NamedTuple):
    appname: str
    guildid: int
    userid: int
    action: VoiceAction
    created_at: datetime.datetime


voice_event_handler: EventHandler[VoiceEvent] = EventHandler(
    'voice_event', AnalyticsData.VoiceSession, VoiceEvent, batchsize=5
)

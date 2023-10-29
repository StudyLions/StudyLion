from typing import Optional, TypeAlias, Any
import asyncio
import logging
import pickle

from ..logger import logging_context, log_wrap, set_logging_context


logger = logging.getLogger(__name__)


Address: TypeAlias = dict[str, Any]


class AppClient:
    routes: dict[str, 'AppRoute'] = {}  # route_name -> Callable[Any, Awaitable[Any]]

    def __init__(self, appid: str, basename: str, client_address: Address, server_address: Address):
        self.appid = appid  # String identifier for this ShardTalk client
        self.basename = basename  # Prefix used to recognise app peers
        self.address = client_address
        self.server_address = server_address

        self.peers = {appid: client_address}  # appid -> address

        self._listener: Optional[asyncio.Server] = None  # Local client server
        self._server = None  # Connection to the registry server
        self._keepalive = None

        self.register_route('new_peer')(self.new_peer)
        self.register_route('drop_peer')(self.drop_peer)
        self.register_route('peer_list')(self.peer_list)

    @property
    def my_peers(self):
        return {peerid: peer for peerid, peer in self.peers.items() if peerid.startswith(self.basename)}

    def register_route(self, name=None):
        def wrapper(coro):
            route = AppRoute(coro, client=self, name=name)
            self.routes[route.name] = route
            return route
        return wrapper

    async def server_connection(self):
        """Establish a connection to the registry server"""
        try:
            reader, writer = await asyncio.open_connection(**self.server_address)

            payload = ('connect', (), {'appid': self.appid, 'address': self.address})
            writer.write(pickle.dumps(payload))
            writer.write(b'\n')
            await writer.drain()

            data = await reader.readline()
            peers = pickle.loads(data)
            self.peers = peers
            self._server = (reader, writer)
        except Exception:
            logger.exception(
                "Could not connect to registry server. Trying again in 30 seconds.",
                extra={'action': 'Connect'}
            )
            await asyncio.sleep(30)
            asyncio.create_task(self.server_connection())
        else:
            logger.debug(
                "Connected to the registry server, launching keepalive.",
                extra={'action': 'Connect'}
            )
            self._keepalive = asyncio.create_task(self._server_keepalive())

    async def _server_keepalive(self):
        with logging_context(action='Keepalive'):
            if self._server is None:
                raise ValueError("Cannot keepalive non-existent server!")
            reader, write = self._server
            try:
                await reader.read()
            except Exception:
                logger.exception("Lost connection to address server. Reconnecting...")
            else:
                # Connection ended or broke
                logger.info("Lost connection to address server. Reconnecting...")
        await asyncio.sleep(30)
        asyncio.create_task(self.server_connection())

    async def new_peer(self, appid, address):
        self.peers[appid] = address

    async def peer_list(self, peers):
        self.peers = peers

    async def drop_peer(self, appid):
        self.peers.pop(appid, None)

    async def close(self):
        # Close connection to the server
        # TODO
        ...

    @log_wrap(action="Req")
    async def request(self, appid, payload: 'AppPayload', wait_for_reply=True):
        set_logging_context(action=appid)
        try:
            if appid not in self.peers:
                raise ValueError(f"Peer '{appid}' not found.")
            logger.debug(f"Sending request to app '{appid}' with payload {payload}")

            address = self.peers[appid]
            reader, writer = await asyncio.open_connection(**address)

            writer.write(payload.encoded())
            await writer.drain()
            writer.write_eof()
            if wait_for_reply:
                result = await reader.read()
                writer.close()
                decoded = payload.route.decode(result)
                return decoded
            else:
                return None
        except Exception:
            logging.exception(f"Failed to send request to {appid}'")
            return None

    @log_wrap(action="Broadcast")
    async def requestall(self, payload, except_self=True, only_my_peers=True):
        peerlist = list((self.my_peers if only_my_peers else self.peers).keys())
        results = await asyncio.gather(
            *(self.request(appid, payload) for appid in peerlist if (appid != self.appid or not except_self)),
            return_exceptions=True
        )
        return dict(zip(peerlist, results))

    async def handle_request(self, reader, writer):
        set_logging_context(action="SERV")
        data = await reader.read()
        loaded = pickle.loads(data)
        route, args, kwargs = loaded

        set_logging_context(action=route)

        logger.debug(f"AppClient {self.appid} handling request on route '{route}' with args {args} and kwargs {kwargs}")

        if route in self.routes:
            try:
                await self.routes[route].run((reader, writer), args, kwargs)
            except Exception:
                logger.exception(f"Fatal exception during route '{route}'. This should never happen!")
        else:
            logger.warning(f"Appclient '{self.appid}' recieved unknown route {route}. Ignoring.")
        writer.write_eof()

    @log_wrap(stack=("ShardTalk",))
    async def connect(self):
        """
        Start the local peer server.
        Connect to the address server.
        """
        # Start the client server
        self._listener = await asyncio.start_server(self.handle_request, **self.address, start_serving=True)

        logger.info(f"Serving on {self.address}")
        await self.server_connection()


class AppPayload:
    __slots__ = ('route', 'args', 'kwargs')

    def __init__(self, route, *args, **kwargs):
        self.route = route
        self.args = args
        self.kwargs = kwargs

    def __await__(self):
        return self.route.execute(*self.args, **self.kwargs).__await__()

    def encoded(self):
        return pickle.dumps((self.route.name, self.args, self.kwargs))

    async def send(self, appid, **kwargs):
        return await self.route._client.request(appid, self, **kwargs)

    async def broadcast(self, **kwargs):
        return await self.route._client.requestall(self, **kwargs)


class AppRoute:
    __slots__ = ('func', 'name', '_client')

    def __init__(self, func, client=None, name=None):
        self.func = func
        self.name = name or func.__name__
        self._client = client

    def __call__(self, *args, **kwargs):
        return AppPayload(self, *args, **kwargs)

    def encode(self, output):
        return pickle.dumps(output)

    def decode(self, encoded):
        # TODO: Handle exceptions here somehow
        if len(encoded) > 0:
            return pickle.loads(encoded)
        else:
            return ''

    def encoder(self, func):
        self.encode = func

    def decoder(self, func):
        self.decode = func

    async def execute(self, *args, **kwargs):
        """
        Execute the underlying function, with the given arguments.
        """
        return await self.func(*args, **kwargs)

    async def run(self, connection, args, kwargs):
        """
        Run the route, with the given arguments, using the given connection.
        """
        # TODO: ContextVar here for logging? Or in handle_request?
        # Get encoded result
        # TODO: handle exceptions in the execution process
        try:
            result = await self.execute(*args, **kwargs)
            payload = self.encode(result)
        except Exception:
            logger.exception(f"Exception occured running route '{self.name}' with args: {args} and kwargs: {kwargs}")
            payload = b''
        _, writer = connection
        writer.write(payload)
        await writer.drain()
        writer.close()

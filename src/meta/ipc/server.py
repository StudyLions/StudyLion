import asyncio
import pickle
import logging
import string
import random

from ..logger import log_context, log_app, setup_main_logger, set_logging_context, log_wrap
from ..config import conf

logger = logging.getLogger(__name__)

for name in conf.config.options('LOGGING_LEVELS', no_defaults=True):
    logging.getLogger(name).setLevel(conf.logging_levels[name])


uuid_alphabet = string.ascii_lowercase + string.digits


def short_uuid():
    return ''.join(random.choices(uuid_alphabet, k=10))


class AppServer:
    routes = {}  # route name -> bound method

    def __init__(self):
        self.clients = {}  # AppID -> (info, connection)

        self.route('ping')(self.route_ping)
        self.route('whereis')(self.route_whereis)
        self.route('peers')(self.route_peers)
        self.route('connect')(self.client_connection)

    @classmethod
    def route(cls, route_name):
        """
        Decorator to add a route to the server.
        """
        def wrapper(coro):
            cls.routes[route_name] = coro
            return coro
        return wrapper

    async def route_ping(self, connection):
        """
        Pong.
        """
        reader, writer = connection
        writer.write(b"Pong")
        writer.write_eof()

    async def route_whereis(self, connection, appid):
        """
        Return an address for the given client appid.
        Returns None if the client does not have a connection.
        """
        reader, writer = connection
        if appid in self.clients:
            writer.write(pickle.dumps(self.clients[appid][0]))
        else:
            writer.write(b'')
        writer.write_eof()

    async def route_peers(self, connection):
        """
        Send back a map of current peers.
        """
        reader, writer = connection
        peers = self.peer_list()
        payload = pickle.dumps(('peer_list', (peers,)))
        writer.write(payload)
        writer.write_eof()

    async def client_connection(self, connection, appid, address):
        """
        Register and hold a new client connection.
        """
        set_logging_context(action=f"CONN {appid}")
        reader, writer = connection
        # Add the new client
        self.clients[appid] = (address, connection)

        # Send the new client a client list
        peers = self.peer_list()
        writer.write(pickle.dumps(peers))
        writer.write(b'\n')
        await writer.drain()

        # Announce the new client to everyone
        await self.broadcast('new_peer', (), {'appid': appid, 'address': address})

        # Keep the connection open until socket closed or EOF (indicating client death)
        try:
            await reader.read()
        finally:
            # Connection ended or it broke
            logger.info(f"Lost client '{appid}'")
            await self.deregister_client(appid)

    async def handle_connection(self, reader, writer):
        data = await reader.readline()
        route, args, kwargs = pickle.loads(data)

        rqid = short_uuid()
        
        set_logging_context(context=f"RQID: {rqid}", action=f"ROUTE {route}")
        logger.info(f"AppServer handling request on route '{route}' with args {args} and kwargs {kwargs}")

        if route in self.routes:
            # Execute route
            try:
                await self.routes[route]((reader, writer), *args, **kwargs)
            except Exception:
                logger.exception(f"AppServer recieved exception during route '{route}'")
        else:
            logger.warning(f"AppServer recieved unknown route '{route}'. Ignoring.")

    def peer_list(self):
        return {appid: address for appid, (address, _) in self.clients.items()}

    async def deregister_client(self, appid):
        self.clients.pop(appid, None)
        await self.broadcast('drop_peer', (), {'appid': appid})

    @log_wrap(action="broadcast")
    async def broadcast(self, route, args, kwargs):
        logger.debug(f"Sending broadcast on route '{route}' with args {args} and kwargs {kwargs}.")
        payload = pickle.dumps((route, args, kwargs))
        if self.clients:
            await asyncio.gather(
                *(self._send(appid, payload) for appid in self.clients),
                return_exceptions=True
            )

    async def message_client(self, appid, route, args, kwargs):
        """
        Send a message to client `appid` along `route` with given arguments.
        """
        set_logging_context(action=f"MSG {appid}")
        logger.debug(f"Sending '{route}' to '{appid}' with args {args} and kwargs {kwargs}.")
        if appid not in self.clients:
            raise ValueError(f"Client '{appid}' is not connected.")

        payload = pickle.dumps((route, args, kwargs))
        return await self._send(appid, payload)

    async def _send(self, appid, payload):
        """
        Send the encoded `payload` to the client `appid`.
        """
        address, _ = self.clients[appid]
        try:
            reader, writer = await asyncio.open_connection(**address)
            writer.write(payload)
            writer.write_eof()
            await writer.drain()
            writer.close()
        except Exception as ex:
            # TODO: Close client if we can't connect?
            logger.exception(f"Failed to send message to '{appid}'")
            raise ex

    async def start(self, address):
        log_app.set("APPSERVER")
        set_logging_context(stack=("SERV",))
        server = await asyncio.start_server(self.handle_connection, **address)
        logger.info(f"Serving on {address}")
        async with server:
            await server.serve_forever()


async def start_server():
    setup_main_logger()
    address = {'host': '127.0.0.1', 'port': '5000'}
    server = AppServer()
    task = asyncio.create_task(server.start(address))
    await task


if __name__ == '__main__':
    asyncio.run(start_server())

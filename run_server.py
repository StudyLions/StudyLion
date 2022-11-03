import sys
import os
import argparse
import asyncio


sys.path.insert(0, os.path.join(os.getcwd(), "bot"))

from bot.meta.ipc.server import AppServer
from bot.meta import conf


async def main():
    address = {'host': conf.appipc['server_host'], 'port': int(conf.appipc['server_port'])}
    server = AppServer()
    await server.start(address)


if __name__ == '__main__':
    asyncio.run(main())

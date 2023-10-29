# !/bin/python3

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.getcwd()))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))


if __name__ == '__main__':
    from meta.ipc.server import AppServer
    from meta import conf
    address = {'host': conf.appipc['server_host'], 'port': int(conf.appipc['server_port'])}
    server = AppServer()
    asyncio.run(server.start(address))

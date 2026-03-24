# !/bin/python3

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.getcwd()))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))


if __name__ == '__main__':
    from analytics.server import AnalyticsServer
    server = AnalyticsServer()
    asyncio.run(server.run())

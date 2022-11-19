import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.getcwd(), "bot"))

from bot.analytics.server import AnalyticsServer


if __name__ == '__main__':
    server = AnalyticsServer()
    asyncio.run(server.run())

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.getcwd(), "bot"))

from bot.analytics.server import main


if __name__ == '__main__':
    asyncio.run(main())

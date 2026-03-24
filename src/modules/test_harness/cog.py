# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: Test harness cog -- starts/stops the aiohttp test
#          server alongside the bot. Follows the same pattern
#          as the topgg webhook server.
# ============================================================
import logging
from typing import Optional

from aiohttp import web

from meta import LionCog, LionBot

from .server import create_app

logger = logging.getLogger(__name__)

DEFAULT_PORT = 7200


class TestHarnessCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self._runner: Optional[web.AppRunner] = None

    async def cog_load(self):
        try:
            port = self.bot.config.test_harness.getint('port', DEFAULT_PORT)
        except Exception:
            port = DEFAULT_PORT

        app = create_app(self.bot)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"Test harness HTTP server started on port {port}")

    async def cog_unload(self):
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            logger.info("Test harness HTTP server stopped")

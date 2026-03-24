# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: Test harness module -- exposes an HTTP API on the
#          test bot for automated command testing. Only loads
#          when [TEST_HARNESS] enabled = true in config.
# ============================================================
import logging

logger = logging.getLogger(__name__)


async def setup(bot):
    try:
        enabled = bot.config.test_harness.getboolean('enabled', False)
    except Exception:
        enabled = False

    if not enabled:
        logger.info("Test harness disabled via config, skipping.")
        return

    from .cog import TestHarnessCog
    await bot.add_cog(TestHarnessCog(bot))
    logger.info("Test harness module loaded.")

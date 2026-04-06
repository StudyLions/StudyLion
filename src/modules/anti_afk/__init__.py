# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-06
# Purpose: Anti AFK System module -- premium feature that
#          periodically checks voice channel users are still
#          active. Website-only configuration.
# ============================================================
import logging

from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('AntiAfk')


async def setup(bot):
    from .cog import AntiAfkCog
    await bot.add_cog(AntiAfkCog(bot))

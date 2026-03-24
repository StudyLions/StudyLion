# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-15
# Purpose: LionGotchi virtual pet module - entry point
# ============================================================
import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('liongotchi')


async def setup(bot):
    from .cog import LionGotchiCog
    await bot.add_cog(LionGotchiCog(bot))

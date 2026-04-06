# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Screen share enforcement module - requires members
#          to share their screen in designated voice channels
# ============================================================
import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('screen')


async def setup(bot):
    from .cog import ScreenCog
    await bot.add_cog(ScreenCog(bot))

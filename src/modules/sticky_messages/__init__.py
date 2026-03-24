# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-22
# Purpose: Sticky messages module -- premium feature that keeps
#          configured embeds as the last message in a channel
# ============================================================
import logging

logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import StickyMessagesCog
    await bot.add_cog(StickyMessagesCog(bot))

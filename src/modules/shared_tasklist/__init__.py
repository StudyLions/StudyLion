# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Shared tasklist (kanban boards) module init
# ============================================================
import logging

logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import SharedTasklistCog
    await bot.add_cog(SharedTasklistCog(bot))

# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Shared tasklist (kanban boards) module init
# ============================================================
import logging

logger = logging.getLogger(__name__)

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
from babel.translator import LocalBabel
babel = LocalBabel('shared_tasklist')
# --- END AI-MODIFIED ---


async def setup(bot):
    from .cog import SharedTasklistCog
    await bot.add_cog(SharedTasklistCog(bot))

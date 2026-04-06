# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-22
# Purpose: Sticky messages module -- premium feature that keeps
#          configured embeds as the last message in a channel
# ============================================================
import logging

logger = logging.getLogger(__name__)

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
from babel.translator import LocalBabel
babel = LocalBabel('sticky_messages')
# --- END AI-MODIFIED ---


async def setup(bot):
    from .cog import StickyMessagesCog
    await bot.add_cog(StickyMessagesCog(bot))

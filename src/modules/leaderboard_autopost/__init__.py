# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-21
# Purpose: Leaderboard auto-post module - automated leaderboard
#          posting with role assignment, coin rewards, and DMs
# ============================================================
import logging

logger = logging.getLogger(__name__)

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
from babel.translator import LocalBabel
babel = LocalBabel('leaderboard_autopost')
# --- END AI-MODIFIED ---


async def setup(bot):
    from .cog import LeaderboardAutopostCog
    await bot.add_cog(LeaderboardAutopostCog(bot))

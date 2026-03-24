# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-21
# Purpose: Leaderboard auto-post module - automated leaderboard
#          posting with role assignment, coin rewards, and DMs
# ============================================================
import logging

logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import LeaderboardAutopostCog
    await bot.add_cog(LeaderboardAutopostCog(bot))

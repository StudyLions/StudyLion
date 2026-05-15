# ============================================================
# AI-GENERATED FILE
# Created: 2026-05-15
# Purpose: Bot-side notification sender. Polls the website's
#          pending_notifications queue (populated by Stripe gift
#          webhooks) and delivers Discord DMs. Shard 0 only so we
#          don't have 32 instances fighting over the same rows.
# ============================================================
import logging
from babel.translator import LocalBabel

babel = LocalBabel('gift_notifications')
logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import GiftNotificationsCog
    await bot.add_cog(GiftNotificationsCog(bot))

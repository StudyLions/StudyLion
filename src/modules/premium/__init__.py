import logging
from babel.translator import LocalBabel

babel = LocalBabel('premium')
logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import PremiumCog
    await bot.add_cog(PremiumCog(bot))

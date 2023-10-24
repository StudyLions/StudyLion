import logging
from babel.translator import LocalBabel

babel = LocalBabel('sponsors')
logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import SponsorCog
    await bot.add_cog(SponsorCog(bot))

import logging
from babel.translator import LocalBabel

babel = LocalBabel('topgg')
logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import TopggCog
    await bot.add_cog(TopggCog(bot))

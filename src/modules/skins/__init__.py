import logging
from babel.translator import LocalBabel

babel = LocalBabel('customskins')
logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import CustomSkinCog
    await bot.add_cog(CustomSkinCog(bot))

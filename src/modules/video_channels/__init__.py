import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('video')


async def setup(bot):
    from .cog import VideoCog
    await bot.add_cog(VideoCog(bot))

import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('economy')


async def setup(bot):
    from .cog import Economy

    await bot.add_cog(Economy(bot))

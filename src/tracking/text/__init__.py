import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('text-tracker')


async def setup(bot):
    from .cog import TextTrackerCog

    await bot.add_cog(TextTrackerCog(bot))

import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('moderation')


async def setup(bot):
    from .cog import ModerationCog
    await bot.add_cog(ModerationCog(bot))

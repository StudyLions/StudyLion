import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('schedule')


async def setup(bot):
    from .cog import ScheduleCog
    await bot.add_cog(ScheduleCog(bot))

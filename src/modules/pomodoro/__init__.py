import logging
from babel.translator import LocalBabel

babel = LocalBabel('Pomodoro')
logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import TimerCog
    await bot.add_cog(TimerCog(bot))

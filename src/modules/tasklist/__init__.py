import logging
from babel.translator import LocalBabel


babel = LocalBabel('tasklist')
logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import TasklistCog
    await bot.add_cog(TasklistCog(bot))

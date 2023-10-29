import logging
from meta import LionBot
from babel.translator import LocalBabel


babel = LocalBabel('ranks')
logger = logging.getLogger(__name__)


async def setup(bot: LionBot):
    from .cog import RankCog
    await bot.add_cog(RankCog(bot))

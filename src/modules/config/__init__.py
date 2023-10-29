import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('config')


async def setup(bot):
    from .cog import GuildConfigCog

    await bot.add_cog(GuildConfigCog(bot))

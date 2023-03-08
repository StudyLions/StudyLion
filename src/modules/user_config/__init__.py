import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('user_config')


async def setup(bot):
    from .cog import UserConfigCog

    await bot.add_cog(UserConfigCog(bot))

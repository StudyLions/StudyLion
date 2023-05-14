import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('config')


async def setup(bot):
    from .general import GeneralSettingsCog
    from .cog import DashCog

    await bot.add_cog(GeneralSettingsCog(bot))
    await bot.add_cog(DashCog(bot))

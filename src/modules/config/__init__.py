import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('config')


async def setup(bot):
    from .general import GeneralSettingsCog

    await bot.add_cog(GeneralSettingsCog(bot))

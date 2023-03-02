from babel.translator import LocalBabel
from meta.LionBot import LionBot

babel = LocalBabel('statistics')


async def setup(bot: LionBot):
    from .cog import StatsCog

    await bot.add_cog(StatsCog(bot))

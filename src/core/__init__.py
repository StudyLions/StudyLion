from babel.translator import LocalBabel


babel = LocalBabel('lion-core')


async def setup(bot):
    from .cog import CoreCog
    from .config import ConfigCog

    await bot.add_cog(CoreCog(bot))
    await bot.add_cog(ConfigCog(bot))

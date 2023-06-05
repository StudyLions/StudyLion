from babel.translator import LocalBabel

babel = LocalBabel('meta')


async def setup(bot):
    from .cog import MetaCog

    await bot.add_cog(MetaCog(bot))

from babel.translator import LocalBabel

util_babel = LocalBabel('utils')


async def setup(bot):
    from .cog import MetaUtils
    await bot.add_cog(MetaUtils(bot))

from .translator import SOURCE_LOCALE, LeoBabel, LocalBabel, LazyStr, ctx_locale, ctx_translator

babel = LocalBabel('babel')


async def setup(bot):
    from .cog import BabelCog
    await bot.add_cog(BabelCog(bot))

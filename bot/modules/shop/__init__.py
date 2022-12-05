from babel import LocalBabel

babel = LocalBabel('shop')


async def setup(bot):
    from .cog import Shopping
    await bot.add_cog(Shopping(bot))

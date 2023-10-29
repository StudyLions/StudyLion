from .cog import Analytics


async def setup(bot):
    await bot.add_cog(Analytics(bot))

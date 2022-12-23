from .cog import CoreCog


async def setup(bot):
    await bot.add_cog(CoreCog(bot))

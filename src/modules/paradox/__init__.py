from .cog import ParaCog


async def setup(bot):
    await bot.add_cog(ParaCog(bot))

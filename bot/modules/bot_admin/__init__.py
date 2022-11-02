from .exec_cog import Exec


async def setup(bot):
    await bot.add_cog(Exec(bot))

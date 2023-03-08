from .cog import CoreCog
from .config import ConfigCog


async def setup(bot):
    await bot.add_cog(CoreCog(bot))
    await bot.add_cog(ConfigCog(bot))

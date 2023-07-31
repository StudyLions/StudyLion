import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('rolemenus')


async def setup(bot):
    from .cog import RoleMenuCog
    await bot.add_cog(RoleMenuCog(bot))

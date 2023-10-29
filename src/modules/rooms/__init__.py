import logging
from babel.translator import LocalBabel

logger = logging.getLogger('Rooms')
babel = LocalBabel('rooms')


async def setup(bot):
    from .cog import RoomCog
    await bot.add_cog(RoomCog(bot))

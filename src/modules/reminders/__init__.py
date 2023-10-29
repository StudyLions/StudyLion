from babel.translator import LocalBabel

babel = LocalBabel('reminders')

import logging
logger = logging.getLogger(__name__)
logger.debug("Loaded reminders")


from .cog import Reminders

async def setup(bot):
    await bot.add_cog(Reminders(bot))

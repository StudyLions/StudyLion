import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('voice-tracker')


async def setup(bot):
    from .cog import VoiceTrackerCog

    await bot.add_cog(VoiceTrackerCog(bot))

# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-30
# Purpose: "Feature Your Server" bot module. Listens on shard 0
#          for HTTP requests from the LionBot website to:
#            (a) create / rotate Discord invites for premium
#                guilds that opt into the public profile feature
#            (b) post a rich Discord embed to the review channel
#                when a server admin submits or edits a listing
#                so Ari can copy-paste an SQL approval command.
# ============================================================
import logging
from babel.translator import LocalBabel

babel = LocalBabel('serverlisting')
logger = logging.getLogger(__name__)


async def setup(bot):
    from .cog import ServerListingCog
    await bot.add_cog(ServerListingCog(bot))

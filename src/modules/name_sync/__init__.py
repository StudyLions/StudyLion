# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-17
# Purpose: NameSync module -- listens to Discord gateway events
#          (on_member_join, on_member_update, on_user_update) and
#          keeps members.display_name + user_config.name/avatar_hash
#          fresh in the database. Pairs with /leo backfill_names for
#          the one-time historical fill of NULL rows.
# ============================================================
import logging

from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('name_sync')


async def setup(bot):
    from .cog import NameSyncCog
    await bot.add_cog(NameSyncCog(bot))

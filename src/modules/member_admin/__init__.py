import logging
from babel.translator import LocalBabel

logger = logging.getLogger(__name__)
babel = LocalBabel('member_admin')


async def setup(bot):
    from .cog import MemberAdminCog
    await bot.add_cog(MemberAdminCog(bot))

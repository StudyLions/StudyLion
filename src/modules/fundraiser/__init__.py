# ============================================================
# AI-GENERATED FILE
# Created: 2026-09-10
# Purpose: Enable the community fundraiser on user-requested bot responses.
# ============================================================
from .responses import FundraiserResponses


async def setup(bot):
    existing = getattr(bot, '_fundraiser_responses', None)
    if existing is None:
        hooks = FundraiserResponses(bot)
        hooks.install()
        bot._fundraiser_responses = hooks


async def teardown(bot):
    hooks = getattr(bot, '_fundraiser_responses', None)
    if hooks is not None:
        hooks.uninstall()
        del bot._fundraiser_responses

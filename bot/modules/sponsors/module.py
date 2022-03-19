import discord

from LionModule import LionModule
from LionContext import LionContext

from meta import client


module = LionModule("Sponsor")


sponsored_commands = {'profile', 'stats', 'weekly', 'monthly'}


@LionContext.reply.add_wrapper
async def sponsor_reply_wrapper(func, ctx: LionContext, *args, **kwargs):
    if ctx.cmd and ctx.cmd.name in sponsored_commands:
        sponsor_hint = discord.Embed(
            description=ctx.client.settings.sponsor_prompt.value,
            colour=discord.Colour.dark_theme()
        )
        if 'embed' not in kwargs:
            kwargs['embed'] = sponsor_hint

    return await func(ctx, *args, **kwargs)

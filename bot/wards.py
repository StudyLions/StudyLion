from meta.LionContext import LionContext


async def sys_admin(ctx: LionContext) -> bool:
    """
    Checks whether the context author is listed in the configuration file as a bot admin.
    """
    admins = ctx.bot.config.bot.getintlist('admins')
    return ctx.author.id in admins

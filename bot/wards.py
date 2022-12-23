from meta.LionContext import LionContext


async def sys_admin(ctx: LionContext) -> bool:
    """
    Checks whether the context author is listed in the configuration file as a bot admin.
    """
    admins = ctx.bot.config.bot.getintlist('admins')
    return ctx.author.id in admins


async def high_management(ctx: LionContext) -> bool:
    if await sys_admin(ctx):
        return True
    if not ctx.guild:
        return False
    return ctx.author.guild_permissions.administrator


async def low_management(ctx: LionContext) -> bool:
    return (await high_management(ctx)) or ctx.author.guild_permissions.manage_guild

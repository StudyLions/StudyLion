from .module import module


@module.cmd(
    name="sponsors",
    group="Meta",
    desc="Check out our wonderful partners!",
)
async def cmd_sponsors(ctx):
    """
    Usage``:
        {prefix}sponsors
    """
    await ctx.reply(**ctx.client.settings.sponsor_message.args(ctx))

from cmdClient.checks import is_owner

from .module import module


@module.cmd(
    name="sponsors",
    group="Meta",
    desc="Check out our wonderful partners!",
    flags=('edit', 'prompt')
)
async def cmd_sponsors(ctx, flags):
    """
    Usage``:
        {prefix}sponsors
    """
    if await is_owner.run(ctx) and any(flags.values()):
        if flags['edit']:
            # Run edit setting command
            await ctx.client.settings.sponsor_message.command(ctx, ctx.client.conf.bot['data_appid'])
        elif flags['prompt']:
            # Run prompt setting command
            await ctx.client.settings.sponsor_prompt.command(ctx, ctx.client.conf.bot['data_appid'])
    else:
        # Display message
        await ctx.reply(**ctx.client.settings.sponsor_message.args(ctx))

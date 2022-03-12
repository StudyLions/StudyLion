from cmdClient.checks import is_owner

from .module import module
from .config import settings


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
            await settings.sponsor_message.command(ctx, 0)
        elif flags['prompt']:
            # Run prompt setting command
            await settings.sponsor_prompt.command(ctx, 0)
    else:
        # Display message
        await ctx.reply(**settings.sponsor_message.args(ctx))

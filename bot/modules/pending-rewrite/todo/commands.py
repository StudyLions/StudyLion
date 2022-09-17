import asyncio
import discord

from cmdClient.checks import in_guild

from .module import module
from .Tasklist import Tasklist


@module.cmd(
    name="todo",
    desc="Display and edit your personal To-Do list.",
    group="Productivity",
    flags=('add==', 'delete==', 'check==', 'uncheck==', 'edit==', 'text')
)
@in_guild()
async def cmd_todo(ctx, flags):
    """
    Usage``:
        {prefix}todo
        {prefix}todo <tasks>
        {prefix}todo add <tasks>
        {prefix}todo delete <taskids>
        {prefix}todo check <taskids>
        {prefix}todo uncheck <taskids>
        {prefix}todo edit <taskid> <new task>
    Description:
        Open your personal interactive TODO list with `{prefix}todo`, \
            and start adding tasks by sending `add your_task_here`. \
            Press ❔ to see more ways to use the interactive list.
        You can also use the commands above to modify your TODOs (see the examples below).

        You may add several tasks at once by writing them on different lines \
        (type Shift-Enter to make a new line on the desktop client).
    Examples::
        {prefix}todo: Open your TODO list.
        {prefix}todo My New task: Add `My New task`.
        {prefix}todo delete 1, 3-5: Delete tasks `1, 3, 4, 5`.
        {prefix}todo check 1, 2: Mark tasks `1` and `2` as done.
        {prefix}todo edit 1 My new task: Edit task `1`.
    """
    tasklist_channels = ctx.guild_settings.tasklist_channels.value
    if tasklist_channels and ctx.ch not in tasklist_channels:
        visible = [channel for channel in tasklist_channels if channel.permissions_for(ctx.author).read_messages]
        if not visible:
            prompt = "The `todo` command may not be used here!"
        elif len(visible) == 1:
            prompt = (
                "The `todo` command may not be used here! "
                "Please go to {}."
            ).format(visible[0].mention)
        else:
            prompt = (
                "The `todo` command may not be used here! "
                "Please go to one of the following.\n{}"
            ).format(' '.join(vis.mention for vis in visible))
        out_msg = await ctx.msg.reply(
            embed=discord.Embed(
                description=prompt,
                colour=discord.Colour.red()
            )
        )
        await asyncio.sleep(60)
        try:
            await out_msg.delete()
            await ctx.msg.delete()
        except discord.HTTPException:
            pass
        return

    # TODO: Custom module, with pre-command hooks
    tasklist = Tasklist.fetch_or_create(ctx, flags, ctx.author, ctx.ch)

    keys = {
        'add': (('add', ), tasklist.parse_add),
        'check': (('check', 'done', 'complete'), tasklist.parse_check),
        'uncheck': (('uncheck', 'uncomplete'), tasklist.parse_uncheck),
        'edit': (('edit',), tasklist.parse_edit),
        'delete': (('delete',), tasklist.parse_delete)
    }

    # Handle subcommands
    cmd = None
    args = ctx.args
    splits = args.split(maxsplit=1)
    if len(splits) > 1:
        maybe_cmd = splits[0].lower()
        for key, (aliases, _) in keys.items():
            if maybe_cmd in aliases:
                cmd = key
                break

    # Default to adding if no command given
    if cmd:
        args = splits[1].strip()
    elif args:
        cmd = 'add'

    async with tasklist.interaction_lock:
        # Run required parsers
        for key, (_, func) in keys.items():
            if flags[key] or cmd == key:
                await func((flags[key] or args).strip())

        if not (any(flags.values()) or args):
            # Force a repost if no flags were provided
            await tasklist.update(repost=True)
        else:
            # Delete if the tasklist already had a message
            if tasklist.message:
                try:
                    await ctx.msg.delete()
                except discord.HTTPException:
                    pass
            await tasklist.update()

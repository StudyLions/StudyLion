import sys
from io import StringIO
import traceback
import asyncio

from cmdClient import cmd, checks

from core import Lion
from LionModule import LionModule

"""
Exec level commands to manage the bot.

Commands provided:
    async:
        Executes provided code in an async executor
    eval:
        Executes code and awaits it if required
"""


@cmd("shutdown",
     desc="Sync data and shutdown.",
     group="Bot Admin",
     aliases=('restart', 'reboot'))
@checks.is_owner()
async def cmd_shutdown(ctx):
    """
    Usage``:
        reboot
    Description:
        Run unload tasks and shutdown/reboot.
    """
    # Run module logout tasks
    for module in ctx.client.modules:
        if isinstance(module, LionModule):
            await module.unload(ctx.client)

    # Reply and logout
    await ctx.reply("All modules synced. Shutting down!")
    await ctx.client.close()


@cmd("async",
     desc="Execute arbitrary code with `async`.",
     group="Bot Admin")
@checks.is_owner()
async def cmd_async(ctx):
    """
    Usage:
        {prefix}async <code>
    Description:
        Runs <code> as an asynchronous coroutine and prints the output or error.
    """
    if ctx.arg_str == "":
        await ctx.error_reply("You must give me something to run!")
        return
    output, error = await _async(ctx)
    await ctx.reply(
        "**Async input:**\
        \n```py\n{}\n```\
        \n**Output {}:** \
        \n```py\n{}\n```".format(ctx.arg_str,
                                 "error" if error else "",
                                 output))


@cmd("eval",
     desc="Execute arbitrary code with `eval`.",
     group="Bot Admin")
@checks.is_owner()
async def cmd_eval(ctx):
    """
    Usage:
        {prefix}eval <code>
    Description:
        Runs <code> in current environment using eval() and prints the output or error.
    """
    if ctx.arg_str == "":
        await ctx.error_reply("You must give me something to run!")
        return
    output, error = await _eval(ctx)
    await ctx.reply(
        "**Eval input:**\
        \n```py\n{}\n```\
        \n**Output {}:** \
        \n```py\n{}\n```".format(ctx.arg_str,
                                 "error" if error else "",
                                 output)
    )


async def _eval(ctx):
    output = None
    try:
        output = eval(ctx.arg_str)
    except Exception:
        return (str(traceback.format_exc()), 1)
    if asyncio.iscoroutine(output):
        output = await output
    return (output, 0)


async def _async(ctx):
    env = {
        'ctx': ctx,
        'client': ctx.client,
        'message': ctx.msg,
        'arg_str': ctx.arg_str
    }
    env.update(globals())
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    result = None
    exec_string = "async def _temp_exec():\n"
    exec_string += '\n'.join(' ' * 4 + line for line in ctx.arg_str.split('\n'))
    try:
        exec(exec_string, env)
        result = (redirected_output.getvalue(), 0)
    except Exception:
        result = (str(traceback.format_exc()), 1)
        return result
    _temp_exec = env['_temp_exec']
    try:
        returnval = await _temp_exec()
        value = redirected_output.getvalue()
        if returnval is None:
            result = (value, 0)
        else:
            result = (value + '\n' + str(returnval), 0)
    except Exception:
        result = (str(traceback.format_exc()), 1)
    finally:
        sys.stdout = old_stdout
    return result

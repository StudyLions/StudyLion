import sys
from io import StringIO
import traceback
import asyncio

from cmdClient import cmd, checks

"""
Exec level commands to manage the bot.

Commands provided:
    async:
        Executes provided code in an async executor
    exec:
        Executes code using standard python exec
    eval:
        Executes code and awaits it if required
"""


@cmd("reboot")
@checks.is_owner()
async def cmd_reboot(ctx):
    """
    Usage``:
        reboot
    Description:
        Update the timer status save file and reboot the client.
    """
    ctx.client.interface.update_save("reboot")
    ctx.client.interface.shutdown()
    await ctx.reply("Saved state. Rebooting now!")
    await ctx.client.close()


@cmd("async")
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


@cmd("eval")
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

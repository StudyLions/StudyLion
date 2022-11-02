import io
import ast
import sys
import types
import traceback
import builtins
import inspect
import asyncio
import logging

from typing import Callable, Any, Coroutine, List, Optional

from enum import Enum

import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, View
from discord.ui.button import button


logger = logging.getLogger(__name__)


class FastModal(Modal):
    def __init__(self, *items, **kwargs):
        super().__init__(**kwargs)
        for item in items:
            self.add_item(item)
        self._result: asyncio.Future[discord.Interaction] = asyncio.get_event_loop().create_future()
        self._waiters: List[Coroutine[discord.Interaction]] = []

    async def wait_for(self, check=None, timeout=None):
        # Wait for _result or timeout
        # If we timeout, or the view times out, raise TimeoutError
        # Otherwise, return the Interaction
        # This allows multiple listeners and callbacks to wait on
        # TODO: Wait on the timeout as well
        while True:
            result = await asyncio.wait_for(asyncio.shield(self._result), timeout=timeout)
            if check is not None:
                if not check(result):
                    continue
            return result

    def submit_callback(self, timeout=None, check=None, once=False, pass_args=(), pass_kwargs={}):
        def wrapper(coro):
            async def wrapped_callback(interaction):
                if check is not None:
                    if not check(interaction):
                        return
                try:
                    await coro(interaction, *pass_args, **pass_kwargs)
                except Exception:
                    # TODO: Log exception
                    ...
                if once:
                    self._waiters.remove(wrapped_callback)
            self._waiters.append(wrapped_callback)
        return wrapper

    async def on_submit(self, interaction):
        old_result = self._result
        self._result = asyncio.get_event_loop().create_future()
        old_result.set_result(interaction)

        for waiter in self._waiters:
            asyncio.create_task(waiter(interaction))

    async def on_error(self, interaction, error):
        # This should never happen, since on_submit has its own error handling
        # TODO: Logging
        ...


class ExecModal(FastModal, title="Execute"):
    code: TextInput = TextInput(
        label="Code to execute",
        style=discord.TextStyle.long,
        required=True
    )


class ExecStyle(Enum):
    EXEC = 'exec'
    EVAL = 'eval'


class ExecUI(View):
    def __init__(self, ctx, code=None, style=ExecStyle.EXEC, ephemeral=False):
        super().__init__()

        self.ctx: commands.Context = ctx
        self.interaction: Optional[discord.Interaction] = ctx.interaction
        self.code: Optional[str] = code
        self.style: ExecStyle = style
        self.ephemeral: bool = ephemeral

        self._modal: Optional[ExecModal] = None
        self._msg: Optional[discord.Message] = None

    async def run(self):
        if self.code is None:
            if (interaction := self.interaction) is not None:
                self.interaction = None
                await interaction.response.send_modal(self.get_modal())
            else:
                # Complain
                # TODO: error_reply
                await self.ctx.reply("Pls give code.")
        else:
            await self.interaction.response.defer(thinking=True)
            await self.compile()

    @button(label="Recompile")
    async def recompile_button(self, interaction, butt):
        # Interaction response with modal
        await interaction.response.send_modal(self.get_modal())

    def create_modal(self) -> ExecModal:
        modal = ExecModal()

        @modal.submit_callback()
        async def exec_submit(interaction: discord.Interaction):
            if self.interaction is None:
                self.interaction = interaction
                await interaction.response.defer(thinking=True)
            else:
                await interaction.response.defer()

            # Set code
            self.code = modal.code.value

            # Call compile
            await self.compile()

        return modal

    def get_modal(self):
        if self._modal is None:
            # Create modal
            self._modal = self.create_modal()

        self._modal.code.default = self.code
        return self._modal

    async def compile(self):
        # Call _async
        result = await _async(self.ctx, self.code, style=self.style.value)

        # Display output
        await self.show_output(result)

    async def show_output(self, output):
        # Format output
        # If output message exists and not ephemeral, edit
        # Otherwise, send message, add buttons
        # TODO: File output
        # TODO: Check this handles ephemerals properly
        formatted = "```py\n{}```".format(output)
        if self._msg is None:
            if self.interaction is not None:
                msg = await self.interaction.edit_original_response(content=formatted, view=self)
            else:
                # Send new message
                msg = await self.ctx.reply(formatted, ephemeral=self.ephemeral, view=self)

            if not self.ephemeral:
                self._msg = msg
        else:
            if self.interaction is not None:
                await self.interaction.edit_original_response(content=formatted, view=self)
            else:
                # Edit message
                await self._msg.edit(formatted)


def mk_print(fp: io.StringIO) -> Callable[..., None]:
    def _print(*args, file: Any = fp, **kwargs):
        return print(*args, file=file, **kwargs)
    return _print


async def _async(ctx: commands.Context, to_eval, style='exec'):
    output = io.StringIO()
    _print = mk_print(output)

    scope = dict(sys.modules)
    scope['__builtins__'] = builtins
    scope.update(builtins.__dict__)
    scope['ctx'] = ctx
    scope['bot'] = ctx.bot
    scope['print'] = _print  # type: ignore

    try:
        code = compile(to_eval, f"<msg: {ctx.message.id}>", style, ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        func = types.FunctionType(code, scope)

        ret = func()
        if inspect.iscoroutine(ret):
            ret = await ret
        if ret is not None:
            _print(repr(ret))
    except Exception:
        _, exc, tb = sys.exc_info()
        _print("".join(traceback.format_tb(tb)))
        _print(repr(exc))

    result = output.getvalue()
    logger.info(
        f"Exec complete, output:\n{result}",
        extra={'action': "Code Exec"}
    )
    return result


class Exec(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='async')
    async def async_cmd(self, ctx, *, string: str = None):
        await ExecUI(ctx, string, ExecStyle.EXEC).run()

    @commands.hybrid_command(name='eval')
    async def eval_cmd(self, ctx, *, string: str):
        await ExecUI(ctx, string, ExecStyle.EVAL).run()

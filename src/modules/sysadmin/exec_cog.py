import io
import ast
import sys
import types
import asyncio
import traceback
import builtins
import inspect
import logging
from io import StringIO

from typing import Callable, Any, Optional

from enum import Enum

import discord
from discord.ext import commands
from discord.ui import TextInput, View
from discord.ui.button import button
import discord.app_commands as appcmd

from meta.logger import logging_context, log_wrap
from meta.app import shard_talk
from meta import conf
from meta.context import context, ctx_bot
from meta.LionContext import LionContext
from meta.LionCog import LionCog
from meta.LionBot import LionBot

from utils.ui import FastModal, input

from babel.translator import LocalBabel

from wards import sys_admin


logger = logging.getLogger(__name__)

_, _n, _p, _np = LocalBabel('exec').methods


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
    def __init__(self, ctx, code=None, style=ExecStyle.EXEC, ephemeral=True) -> None:
        super().__init__()

        self.ctx: LionContext = ctx
        self.interaction: Optional[discord.Interaction] = ctx.interaction
        self.code: Optional[str] = code
        self.style: ExecStyle = style
        self.ephemeral: bool = ephemeral

        self._modal: Optional[ExecModal] = None
        self._msg: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction):
        """Only allow the original author to use this View"""
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                ("You cannot use this interface!"),
                ephemeral=True
            )
            return False
        else:
            return True

    async def run(self):
        if self.code is None:
            if (interaction := self.interaction) is not None:
                self.interaction = None
                await interaction.response.send_modal(self.get_modal())
                await self.wait()
            else:
                # Complain
                # TODO: error_reply
                await self.ctx.reply("Pls give code.")
        else:
            await self.interaction.response.defer(thinking=True, ephemeral=self.ephemeral)
            await self.compile()
            await self.wait()

    @button(label="Recompile")
    async def recompile_button(self, interaction, butt):
        # Interaction response with modal
        await interaction.response.send_modal(self.get_modal())

    @button(label="Show Source")
    async def source_button(self, interaction, butt):
        if len(self.code) > 1900:
            # Send as file
            with StringIO(self.code) as fp:
                fp.seek(0)
                file = discord.File(fp, filename="source.py")
                await interaction.response.send_message(file=file, ephemeral=True)
        else:
            # Send as message
            await interaction.response.send_message(
                content=f"```py\n{self.code}```",
                ephemeral=True
            )

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
        self._modal = self.create_modal()
        self._modal.code.default = self.code
        return self._modal

    async def compile(self):
        # Call _async
        result = await _async(self.code, style=self.style.value)

        # Display output
        await self.show_output(result)

    async def show_output(self, output):
        # Format output
        # If output message exists and not ephemeral, edit
        # Otherwise, send message, add buttons
        if len(output) > 1900:
            # Send as file
            with StringIO(output) as fp:
                fp.seek(0)
                args = {
                    'content': None,
                    'attachments': [discord.File(fp, filename="output.md")]
                }
        else:
            args = {
                'content': f"```md\n{output}```",
                'attachments': []
            }

        if self._msg is None:
            if self.interaction is not None:
                msg = await self.interaction.edit_original_response(**args, view=self)
            else:
                # Send new message
                if args['content'] is None:
                    args['file'] = args.pop('attachments')[0]
                msg = await self.ctx.reply(**args, ephemeral=self.ephemeral, view=self)

            if not self.ephemeral:
                self._msg = msg
        else:
            if self.interaction is not None:
                await self.interaction.edit_original_response(**args, view=self)
            else:
                # Edit message
                await self._msg.edit(**args)


def mk_print(fp: io.StringIO) -> Callable[..., None]:
    def _print(*args, file: Any = fp, **kwargs):
        return print(*args, file=file, **kwargs)
    return _print


@log_wrap(action="Code Exec")
async def _async(to_eval: str, style='exec'):
    newline = '\n' * ('\n' in to_eval)
    logger.info(
        f"Exec code with {style}: {newline}{to_eval}"
    )

    output = io.StringIO()
    _print = mk_print(output)

    scope: dict[str, Any] = dict(sys.modules)
    scope['__builtins__'] = builtins
    scope.update(builtins.__dict__)
    scope['ctx'] = ctx = context.get()
    scope['bot'] = ctx_bot.get()
    scope['print'] = _print  # type: ignore

    try:
        if ctx and ctx.message:
            source_str = f"<msg: {ctx.message.id}>"
        elif ctx and ctx.interaction:
            source_str = f"<iid: {ctx.interaction.id}>"
        else:
            source_str = "Unknown async"

        code = compile(
            to_eval,
            source_str,
            style,
            ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
        )
        func = types.FunctionType(code, scope)

        ret = func()
        if inspect.iscoroutine(ret):
            ret = await ret
        if ret is not None:
            _print(repr(ret))
    except Exception:
        _, exc, tb = sys.exc_info()
        _print("".join(traceback.format_tb(tb)))
        _print(f"{type(exc).__name__}: {exc}")

    result = output.getvalue().strip()
    newline = '\n' * ('\n' in result)
    logger.info(
        f"Exec complete, output: {newline}{result}"
    )
    return result


class Exec(LionCog):
    guild_ids = conf.bot.getintlist('admin_guilds')

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.t = bot.translator.t

        self.talk_async = shard_talk.register_route('exec')(_async)

    async def cog_check(self, ctx: LionContext) -> bool:  # type: ignore
        return await sys_admin(ctx.bot, ctx.author.id)

    @commands.hybrid_command(
        name=_('async'),
        description=_("Execute arbitrary code with Exec")
    )
    @appcmd.describe(
        string="Code to execute."
    )
    async def async_cmd(self, ctx: LionContext, *, string: Optional[str] = None):
        await ExecUI(ctx, string, ExecStyle.EXEC, ephemeral=False).run()

    @commands.hybrid_command(
        name=_p('command', 'eval'),
        description=_p('command:eval', 'Execute arbitrary code with Eval')
    )
    @appcmd.describe(
        string=_p('command:eval|param:string', "Code to evaluate.")
    )
    @appcmd.guilds(*guild_ids)
    async def eval_cmd(self, ctx: LionContext, *, string: str):
        await ExecUI(ctx, string, ExecStyle.EVAL).run()

    @commands.hybrid_command(
        name=_p('command', 'asyncall'),
        description=_p('command:asyncall|desc', "Execute arbitrary code on all shards.")
    )
    @appcmd.describe(
        string=_p("command:asyncall|param:string", "Cross-shard code to execute. Cannot reference ctx!"),
        target=_p("command:asyncall|param:target", "Target shard app name, see autocomplete for options.")
    )
    @appcmd.guilds(*guild_ids)
    async def asyncall_cmd(self, ctx: LionContext, string: Optional[str] = None, target: Optional[str] = None):
        if string is None and ctx.interaction:
            try:
                ctx.interaction, string = await input(
                    ctx.interaction, "Cross-shard execute", "Code to execute?",
                    style=discord.TextStyle.long
                )
            except asyncio.TimeoutError:
                return
        if ctx.interaction:
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)
        if target is not None:
            if target not in shard_talk.peers:
                embed = discord.Embed(description=f"Unknown peer {target}", colour=discord.Colour.red())
                if ctx.interaction:
                    await ctx.interaction.edit_original_response(embed=embed)
                else:
                    await ctx.reply(embed=embed)
                return
            else:
                result = await self.talk_async(string).send(target)
                results = {target: result}
        else:
            results = await self.talk_async(string).broadcast(except_self=False)

        blocks = [f"# {appid}\n{result}" for appid, result in results.items()]
        output = "\n\n".join(blocks)
        if len(output) > 1900:
            # Send as file
            with StringIO(output) as fp:
                fp.seek(0)
                file = discord.File(fp, filename="output.md")  # type: ignore
                await ctx.reply(file=file)
        else:
            # Send as message
            await ctx.reply(f"```md\n{output}```", ephemeral=True)

    @asyncall_cmd.autocomplete('target')
    async def asyncall_target_acmpl(self, interaction: discord.Interaction, partial: str):
        appids = set(shard_talk.peers.keys())
        results = [
            appcmd.Choice(name=appid, value=appid)
            for appid in appids
            if partial.lower() in appid.lower()
        ]
        if not results:
            results = [
                appcmd.Choice(name=f"No peers found matching {partial}", value="None")
            ]
        return results

    @commands.hybrid_command(
        name=_('reload'),
        description=_("Reload a given LionBot extension. Launches an ExecUI.")
    )
    @appcmd.describe(
        extension=_("Name of the extesion to reload. See autocomplete for options.")
    )
    @appcmd.guilds(*guild_ids)
    async def reload_cmd(self, ctx: LionContext, extension: str):
        """
        This is essentially just a friendly wrapper to reload an extension.
        It is equivalent to running "await bot.reload_extension(extension)" in eval,
        with a slightly nicer interface through the autocomplete and error handling.
        """
        if extension not in self.bot.extensions:
            embed = discord.Embed(description=f"Unknown extension {extension}", colour=discord.Colour.red())
            await ctx.reply(embed=embed)
        else:
            # Uses an ExecUI to simplify error handling and re-execution
            string = f"await bot.reload_extension('{extension}')"
            await ExecUI(ctx, string, ExecStyle.EVAL).run()

    @reload_cmd.autocomplete('extension')
    async def reload_extension_acmpl(self, interaction: discord.Interaction, partial: str):
        keys = set(self.bot.extensions.keys())
        results = [
            appcmd.Choice(name=key, value=key)
            for key in keys
            if partial.lower() in key.lower()
        ]
        if not results:
            results = [
                appcmd.Choice(name=f"No extensions found matching {partial}", value="None")
            ]
        return results

    @commands.hybrid_command(
        name=_('shutdown'),
        description=_("Shutdown (or restart) the client.")
    )
    @appcmd.guilds(*guild_ids)
    async def shutdown_cmd(self, ctx: LionContext):
        """
        Shutdown the client.
        Maybe do something friendly here?
        """
        logger.info("Shutting down on admin request.")
        await ctx.reply(
            embed=discord.Embed(
                description=f"Understood {ctx.author.mention}, cleaning up and shutting down!",
                colour=discord.Colour.orange()
            )
        )
        await self.bot.close()

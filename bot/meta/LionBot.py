from typing import List, Optional, TYPE_CHECKING
import logging
import asyncio

import discord
from discord.utils import MISSING
from discord.ext.commands import Bot, Cog, HybridCommand, HybridCommandError
from discord.ext.commands.errors import CommandInvokeError, CheckFailure
from discord.app_commands.errors import CommandInvokeError as appCommandInvokeError
from aiohttp import ClientSession

from data import Database

from .config import Conf
from .logger import logging_context, log_context, log_action_stack
from .context import context
from .LionContext import LionContext
from .LionTree import LionTree
from .errors import HandledException, SafeCancellation

if TYPE_CHECKING:
    from core import CoreCog

logger = logging.getLogger(__name__)


class LionBot(Bot):
    def __init__(
        self, *args, appname: str, shardname: str, db: Database, config: Conf,
        initial_extensions: List[str], web_client: ClientSession, app_ipc,
        testing_guilds: List[int] = [], translator=None, **kwargs
    ):
        kwargs.setdefault('tree_cls', LionTree)
        super().__init__(*args, **kwargs)
        self.web_client = web_client
        self.testing_guilds = testing_guilds
        self.initial_extensions = initial_extensions
        self.db = db
        self.appname = appname
        self.shardname = shardname
#        self.appdata = appdata
        self.config = config
        self.app_ipc = app_ipc
        self.core: Optional['CoreCog'] = None
        self.translator = translator

    async def setup_hook(self) -> None:
        log_context.set(f"APP: {self.application_id}")
        await self.app_ipc.connect()

        if self.translator is not None:
            await self.tree.set_translator(self.translator)

        for extension in self.initial_extensions:
            await self.load_extension(extension)

        for guildid in self.testing_guilds:
            guild = discord.Object(guildid)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    async def add_cog(self, cog: Cog, **kwargs):
        with logging_context(action=f"Attach {cog.__cog_name__}"):
            logger.info(f"Attaching Cog {cog.__cog_name__}")
            await super().add_cog(cog, **kwargs)
            logger.debug(f"Attached Cog {cog.__cog_name__} with no errors.")

    async def load_extension(self, name, *, package=None, **kwargs):
        with logging_context(action=f"Load {name.strip('.')}"):
            logger.info(f"Loading extension {name} in package {package}.")
            await super().load_extension(name, package=package, **kwargs)
            logger.debug(f"Loaded extension {name} in package {package}.")

    async def start(self, token: str, *, reconnect: bool = True):
        with logging_context(action="Login"):
            await self.login(token)
        with logging_context(stack=["Running"]):
            await self.connect(reconnect=reconnect)

    async def on_ready(self):
        logger.info(
            f"Logged in as {self.application.name}\n"
            f"Application id {self.application.id}\n"
            f"Shard Talk identifier {self.shardname}\n"
            "------------------------------\n"
            f"Enabled Modules: {', '.join(self.extensions.keys())}\n"
            f"Loaded Cogs: {', '.join(self.cogs.keys())}\n"
            f"Registered Data: {', '.join(self.db.registries.keys())}\n"
            f"Listening for {sum(1 for _ in self.walk_commands())} commands\n"
            "------------------------------\n"
            f"Logged in to {len(self.guilds)} guilds on shard {self.shard_id} of {self.shard_count}\n"
            "Ready to take commands!\n",
            extra={'action': 'Ready'}
        )

    async def get_context(self, origin, /, *, cls=MISSING):
        if cls is MISSING:
            cls = LionContext
        ctx = await super().get_context(origin, cls=cls)
        context.set(ctx)
        return ctx

    async def on_command(self, ctx: LionContext):
        logger.info(
            f"Executing command '{ctx.command.qualified_name}' "
            f"(from module '{ctx.cog.qualified_name if ctx.cog else 'None'}') "
            f"with arguments {ctx.args} and kwargs {ctx.kwargs}.",
            extra={'with_ctx': True}
        )

    async def on_command_error(self, ctx, exception):
        # TODO: Some of these could have more user-feedback
        cmd_str = str(ctx.command)
        if isinstance(ctx.command, HybridCommand) and ctx.command.app_command:
            cmd_str = ctx.command.app_command.to_dict()
        try:
            raise exception
        except (HybridCommandError, CommandInvokeError, appCommandInvokeError):
            try:
                if isinstance(exception.original, (HybridCommandError, CommandInvokeError, appCommandInvokeError)):
                    original = exception.original.original
                    raise original
                else:
                    original = exception.original
                    raise original
            except HandledException:
                pass
            except SafeCancellation:
                if original.msg:
                    try:
                        await ctx.error_reply(original.msg)
                    except Exception:
                        pass
                logger.debug(
                    f"Caught a safe cancellation: {original.details}",
                    extra={'action': 'BotError', 'with_ctx': True}
                )
            except discord.Forbidden:
                # Unknown uncaught Forbidden
                try:
                    # Attempt a general error reply
                    await ctx.reply("I don't have enough channel or server permissions to complete that command here!")
                except Exception:
                    # We can't send anything at all. Exit quietly, but log.
                    logger.warning(
                        f"Caught an unhandled 'Forbidden' while executing: {cmd_str}",
                        exc_info=True,
                        extra={'action': 'BotError', 'with_ctx': True}
                    )
            except discord.HTTPException:
                logger.warning(
                    f"Caught an unhandled 'HTTPException' while executing: {cmd_str}",
                    exc_info=True,
                    extra={'action': 'BotError', 'with_ctx': True}
                )
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                pass
            except Exception:
                logger.exception(
                    f"Caught an unknown CommandInvokeError while executing: {cmd_str}",
                    extra={'action': 'BotError', 'with_ctx': True}
                )

                error_embed = discord.Embed(title="Something went wrong!")
                error_embed.description = (
                    "An unexpected error occurred while processing your command!\n"
                    "Our development team has been notified, and the issue should be fixed soon.\n"
                    "If the error persists, please contact our support team and give them the following number: "
                    f"`{ctx.interaction.id}`"
                )

                try:
                    await ctx.error_reply(embed=error_embed)
                except Exception:
                    pass
            finally:
                exception.original = HandledException(exception.original)
        except CheckFailure:
            logger.debug(
                f"Command failed check: {exception}",
                extra={'action': 'BotError', 'with_ctx': True}
            )
            try:
                await ctx.error_rely(exception.message)
            except Exception:
                pass
        except Exception:
            # Completely unknown exception outside of command invocation!
            # Something is very wrong here, don't attempt user interaction.
            logger.exception(
                f"Caught an unknown top-level exception while executing: {cmd_str}",
                extra={'action': 'BotError', 'with_ctx': True}
            )

    def add_command(self, command):
        if hasattr(command, '_placeholder_group_'):
            return
        super().add_command(command)

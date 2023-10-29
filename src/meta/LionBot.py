from typing import List, Literal, LiteralString, Optional, TYPE_CHECKING, overload
import logging
import asyncio
from weakref import WeakValueDictionary

import discord
from discord.utils import MISSING
from discord.ext.commands import Bot, Cog, HybridCommand, HybridCommandError
from discord.ext.commands.errors import CommandInvokeError, CheckFailure
from discord.app_commands.errors import CommandInvokeError as appCommandInvokeError, TransformerError
from aiohttp import ClientSession

from data import Database
from utils.lib import tabulate
from gui.errors import RenderingException
from babel.translator import ctx_locale, LeoBabel

from .config import Conf
from .logger import logging_context, log_context, log_action_stack, log_wrap, set_logging_context
from .context import context
from .LionContext import LionContext
from .LionTree import LionTree
from .errors import HandledException, SafeCancellation
from .monitor import SystemMonitor, ComponentMonitor, StatusLevel, ComponentStatus

if TYPE_CHECKING:
    from core.cog import CoreCog
    from core.config import ConfigCog
    from tracking.voice.cog import VoiceTrackerCog
    from tracking.text.cog import TextTrackerCog
    from modules.config.cog import GuildConfigCog
    from modules.economy.cog import Economy
    from modules.member_admin.cog import MemberAdminCog
    from modules.meta.cog import MetaCog
    from modules.moderation.cog import ModerationCog
    from modules.pomodoro.cog import TimerCog
    from modules.premium.cog import PremiumCog
    from modules.ranks.cog import RankCog
    from modules.reminders.cog import Reminders
    from modules.rooms.cog import RoomCog
    from modules.schedule.cog import ScheduleCog
    from modules.shop.cog import ShopCog
    from modules.skins.cog import CustomSkinCog
    from modules.sponsors.cog import SponsorCog
    from modules.statistics.cog import StatsCog
    from modules.sysadmin.dash import LeoSettings
    from modules.tasklist.cog import TasklistCog
    from modules.topgg.cog import TopggCog
    from modules.user_config.cog import UserConfigCog
    from modules.video_channels.cog import VideoCog

logger = logging.getLogger(__name__)


class LionBot(Bot):
    def __init__(
        self, *args, appname: str, shardname: str, db: Database, config: Conf, translator: LeoBabel,
        initial_extensions: List[str], web_client: ClientSession, app_ipc,
        testing_guilds: List[int] = [], **kwargs
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
        self.translator = translator

        self.system_monitor = SystemMonitor()
        self.monitor = ComponentMonitor('LionBot', self._monitor_status)
        self.system_monitor.add_component(self.monitor)

        self._locks = WeakValueDictionary()
        self._running_events = set()

        self._talk_global_dispatch = app_ipc.register_route('dispatch')(self._handle_global_dispatch)

    @property
    def core(self):
        return self.get_cog('CoreCog')

    async def _handle_global_dispatch(self, event_name: str, *args, **kwargs):
        self.dispatch(event_name, *args, **kwargs)

    async def global_dispatch(self, event_name: str, *args, **kwargs):
        await self._talk_global_dispatch(event_name, *args, **kwargs).broadcast(except_self=False)

    async def _monitor_status(self):
        if self.is_closed():
            level = StatusLevel.ERRORED
            info = "(ERROR) Websocket is closed"
            data = {}
        elif self.is_ws_ratelimited():
            level = StatusLevel.WAITING
            info = "(WAITING) Websocket is ratelimited"
            data = {}
        elif not self.is_ready():
            level = StatusLevel.STARTING
            info = "(STARTING) Not yet ready"
            data = {}
        else:
            level = StatusLevel.OKAY
            info = (
                "(OK) "
                "Logged in with {guild_count} guilds, "
                ", websocket latency {latency}, and {events} running events."
            )
            data = {
                'guild_count': len(self.guilds),
                'latency': self.latency,
                'events': len(self._running_events),
            }
        return ComponentStatus(level, info, info, data)

    async def setup_hook(self) -> None:
        log_context.set(f"APP: {self.application_id}")
        await self.app_ipc.connect()

        if self.translator is not None:
            await self.tree.set_translator(self.translator)

        for extension in self.initial_extensions:
            await self.load_extension(extension)

        for guildid in self.testing_guilds:
            guild = discord.Object(guildid)
            if not self.shard_count or (self.shard_id == ((guildid >> 22) % self.shard_count)):
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)

    # To make the type checker happy about fetching cogs by name
    # TODO: Move this to stubs at some point

    @overload
    def get_cog(self, name: Literal['CoreCog']) -> 'CoreCog':
        ...

    @overload
    def get_cog(self, name: Literal['ConfigCog']) -> 'ConfigCog':
        ...

    @overload
    def get_cog(self, name: Literal['VoiceTrackerCog']) -> 'VoiceTrackerCog':
        ...

    @overload
    def get_cog(self, name: Literal['TextTrackerCog']) -> 'TextTrackerCog':
        ...

    @overload
    def get_cog(self, name: Literal['GuildConfigCog']) -> 'GuildConfigCog':
        ...

    @overload
    def get_cog(self, name: Literal['Economy']) -> 'Economy':
        ...

    @overload
    def get_cog(self, name: Literal['MemberAdminCog']) -> 'MemberAdminCog':
        ...

    @overload
    def get_cog(self, name: Literal['MetaCog']) -> 'MetaCog':
        ...

    @overload
    def get_cog(self, name: Literal['ModerationCog']) -> 'ModerationCog':
        ...

    @overload
    def get_cog(self, name: Literal['TimerCog']) -> 'TimerCog':
        ...

    @overload
    def get_cog(self, name: Literal['PremiumCog']) -> 'PremiumCog':
        ...

    @overload
    def get_cog(self, name: Literal['RankCog']) -> 'RankCog':
        ...

    @overload
    def get_cog(self, name: Literal['Reminders']) -> 'Reminders':
        ...

    @overload
    def get_cog(self, name: Literal['RoomCog']) -> 'RoomCog':
        ...

    @overload
    def get_cog(self, name: Literal['ScheduleCog']) -> 'ScheduleCog':
        ...

    @overload
    def get_cog(self, name: Literal['ShopCog']) -> 'ShopCog':
        ...

    @overload
    def get_cog(self, name: Literal['CustomSkinCog']) -> 'CustomSkinCog':
        ...

    @overload
    def get_cog(self, name: Literal['SponsorCog']) -> 'SponsorCog':
        ...

    @overload
    def get_cog(self, name: Literal['StatsCog']) -> 'StatsCog':
        ...

    @overload
    def get_cog(self, name: Literal['LeoSettings']) -> 'LeoSettings':
        ...

    @overload
    def get_cog(self, name: Literal['TasklistCog']) -> 'TasklistCog':
        ...

    @overload
    def get_cog(self, name: Literal['TopggCog']) -> 'TopggCog':
        ...

    @overload
    def get_cog(self, name: Literal['UserConfigCog']) -> 'UserConfigCog':
        ...

    @overload
    def get_cog(self, name: Literal['VideoCog']) -> 'VideoCog':
        ...

    @overload
    def get_cog(self, name: str) -> Optional[Cog]:
        ...

    def get_cog(self, name: str) -> Optional[Cog]:
        return super().get_cog(name)

    async def add_cog(self, cog: Cog, **kwargs):
        sup = super()
        @log_wrap(action=f"Attach {cog.__cog_name__}")
        async def wrapper():
            logger.info(f"Attaching Cog {cog.__cog_name__}")
            await sup.add_cog(cog, **kwargs)
            logger.debug(f"Attached Cog {cog.__cog_name__} with no errors.")
        await wrapper()

    async def load_extension(self, name, *, package=None, **kwargs):
        sup = super()
        @log_wrap(action=f"Load {name.strip('.')}")
        async def wrapper():
            logger.info(f"Loading extension {name} in package {package}.")
            await sup.load_extension(name, package=package, **kwargs)
            logger.debug(f"Loaded extension {name} in package {package}.")
        await wrapper()

    async def start(self, token: str, *, reconnect: bool = True):
        with logging_context(action="Login"):
            start_task = asyncio.create_task(self.login(token))
        await start_task

        with logging_context(stack=("Running",)):
            run_task = asyncio.create_task(self.connect(reconnect=reconnect))
        await run_task

    def dispatch(self, event_name: str, *args, **kwargs):
        with logging_context(action=f"Dispatch {event_name}"):
            super().dispatch(event_name, *args, **kwargs)

    def _schedule_event(self, coro, event_name, *args, **kwargs):
        """
        Extends client._schedule_event to keep a persistent
        background task store.
        """
        task = super()._schedule_event(coro, event_name, *args, **kwargs)
        self._running_events.add(task)
        task.add_done_callback(lambda fut: self._running_events.discard(fut))

    def idlock(self, snowflakeid):
        lock = self._locks.get(snowflakeid, None)
        if lock is None:
            lock = self._locks[snowflakeid] = asyncio.Lock()
        return lock

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
            f"with interaction: {ctx.interaction.data if ctx.interaction else None}",
            extra={'with_ctx': True}
        )

    async def on_command_error(self, ctx, exception):
        # TODO: Some of these could have more user-feedback
        logger.debug(f"Handling command error for {ctx}: {exception}")
        if isinstance(ctx.command, HybridCommand) and ctx.command.app_command:
            cmd_str = ctx.command.app_command.to_dict()
        else:
            cmd_str = str(ctx.command)
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
            except TransformerError as e:
                msg = str(e)
                if msg:
                    try:
                        await ctx.error_reply(msg)
                    except Exception:
                        pass
                logger.debug(
                    f"Caught a transformer error: {repr(e)}",
                    extra={'action': 'BotError', 'with_ctx': True}
                )
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
                logger.error(
                    f"Caught an unhandled 'HTTPException' while executing: {cmd_str}",
                    exc_info=True,
                    extra={'action': 'BotError', 'with_ctx': True}
                )
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                pass
            except RenderingException as e:
                logger.info(f"Command failed due to RenderingException: {repr(e)}")
                embed = self.tree.rendersplat(e)
                try:
                    await ctx.error_reply(embed=embed)
                except discord.HTTPException:
                    pass
            except Exception as e:
                logger.exception(
                    f"Caught an unknown CommandInvokeError while executing: {cmd_str}",
                    extra={'action': 'BotError', 'with_ctx': True}
                )

                error_embed = discord.Embed(
                    title="Something went wrong!",
                    colour=discord.Colour.dark_red()
                )
                error_embed.description = (
                    "An unexpected error occurred while processing your command!\n"
                    "Our development team has been notified, and the issue will be addressed soon.\n"
                    "If the error persists, or you have any questions, please contact our [support team]({link}) "
                    "and give them the extra details below."
                ).format(link=self.config.bot.support_guild)
                details = {}
                details['error'] = f"`{repr(e)}`"
                if ctx.interaction:
                    details['interactionid'] = f"`{ctx.interaction.id}`"
                if ctx.command:
                    details['cmd'] = f"`{ctx.command.qualified_name}`"
                if ctx.author:
                    details['author'] = f"`{ctx.author.id}` -- `{ctx.author}`"
                details['locale'] = f"`{ctx_locale.get()}`"
                if ctx.guild:
                    details['guild'] = f"`{ctx.guild.id}` -- `{ctx.guild.name}`"
                    details['my_guild_perms'] = f"`{ctx.guild.me.guild_permissions.value}`"
                    if ctx.author:
                        ownerstr = ' (owner)' if ctx.author.id == ctx.guild.owner_id else ''
                        details['author_guild_perms'] = f"`{ctx.author.guild_permissions.value}{ownerstr}`"
                if ctx.channel.type is discord.enums.ChannelType.private:
                    details['channel'] = "`Direct Message`"
                elif ctx.channel:
                    details['channel'] = f"`{ctx.channel.id}` -- `{ctx.channel.name}`"
                    details['my_channel_perms'] = f"`{ctx.channel.permissions_for(ctx.guild.me).value}`"
                    if ctx.author:
                        details['author_channel_perms'] = f"`{ctx.channel.permissions_for(ctx.author).value}`"
                details['shard'] = f"`{self.shardname}`"
                details['log_stack'] = f"`{log_action_stack.get()}`"

                table = '\n'.join(tabulate(*details.items()))
                error_embed.add_field(name='Details', value=table)

                try:
                    await ctx.error_reply(embed=error_embed)
                except discord.HTTPException:
                    pass
            finally:
                exception.original = HandledException(exception.original)
        except CheckFailure as e:
            logger.debug(
                f"Command failed check: {e}: {e.args}",
                extra={'action': 'BotError', 'with_ctx': True}
            )
            try:
                await ctx.error_reply(str(e))
            except discord.HTTPException:
                pass
        except Exception:
            # Completely unknown exception outside of command invocation!
            # Something is very wrong here, don't attempt user interaction.
            logger.exception(
                f"Caught an unknown top-level exception while executing: {cmd_str}",
                extra={'action': 'BotError', 'with_ctx': True}
            )

    def add_command(self, command):
        if not hasattr(command, '_placeholder_group_'):
            super().add_command(command)

    def request_chunking_for(self, guild):
        if not guild.chunked:
            return asyncio.create_task(
                self._connection.chunk_guild(guild, wait=False, cache=True),
                name=f"Background chunkreq for {guild.id}"
            )

    async def on_interaction(self, interaction: discord.Interaction):
        """
        Adds the interaction author to guild cache if appropriate.

        This gets run a little bit late, so it is possible the interaction gets handled
        without the author being in case.
        """
        guild = interaction.guild
        user = interaction.user
        if guild is not None and user is not None and isinstance(user, discord.Member):
            if not guild.get_member(user.id):
                guild._add_member(user)
        if guild is not None and not guild.chunked:
            # Getting an interaction in the guild is a good enough reason to request chunking
            logger.info(
                f"Unchunked guild <gid: {guild.id}> requesting chunking after interaction."
            )
            self.request_chunking_for(guild)

import logging

import discord
from discord.ext.commands import Bot, Cog, HybridCommand, HybridCommandError
from discord.ext.commands.errors import CommandInvokeError, CheckFailure
from discord.app_commands.errors import CommandInvokeError as appCommandInvokeError

from meta import LionCog, LionBot, LionContext
from meta.app import shard_talk, appname
from meta.errors import HandledException, SafeCancellation
from meta.logger import log_wrap
from utils.lib import utc_now

from .data import AnalyticsData
from .events import (
    CommandStatus, CommandEvent, command_event_handler,
    GuildAction, GuildEvent, guild_event_handler,
    VoiceAction, VoiceEvent, voice_event_handler
)
from .snapshot import shard_snapshot

logger = logging.getLogger(__name__)


# TODO: Client side might be better handled as a single connection fed by a queue?
# Maybe consider this again after the interactive REPL idea
# Or if it seems like this is giving an absurd amount of traffic


class Analytics(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(AnalyticsData())
        self.an_app = bot.config.analytics['appname']

        self.talk_command_event = command_event_handler.bind(shard_talk).route
        self.talk_guild_event = guild_event_handler.bind(shard_talk).route
        self.talk_voice_event = voice_event_handler.bind(shard_talk).route

        self.talk_shard_snapshot = shard_talk.register_route()(shard_snapshot)

    async def cog_load(self):
        await self.data.init()

    @LionCog.listener()
    @log_wrap(action='AnEvent')
    async def on_voice_state_update(self, member, before, after):
        if not before.channel and after.channel:
            # Member joined channel
            action = VoiceAction.JOINED
        elif before.channel and not after.channel:
            # Member left channel
            action = VoiceAction.LEFT
        else:
            # Member change state, we don't need to deal with that
            return

        event = VoiceEvent(
            appname=appname,
            userid=member.id,
            guildid=member.guild.id,
            action=action,
            created_at=utc_now()
        )
        if self.an_app not in shard_talk.peers:
            logger.warning(f"Analytics peer not found, discarding event: {event}")
        else:
            await self.talk_voice_event(event).send(self.an_app, wait_for_reply=False)

    @LionCog.listener()
    @log_wrap(action='AnEvent')
    async def on_guild_join(self, guild):
        """
        Send guild join event.
        """
        event = GuildEvent(
            appname=appname,
            guildid=guild.id,
            action=GuildAction.JOINED,
            created_at=utc_now()
        )
        if self.an_app not in shard_talk.peers:
            logger.warning(f"Analytics peer not found, discarding event: {event}")
        else:
            await self.talk_guild_event(event).send(self.an_app, wait_for_reply=False)

    @LionCog.listener()
    @log_wrap(action='AnEvent')
    async def on_guild_remove(self, guild):
        """
        Send guild leave event
        """
        event = GuildEvent(
            appname=appname,
            guildid=guild.id,
            action=GuildAction.LEFT,
            created_at=utc_now()
        )
        if self.an_app not in shard_talk.peers:
            logger.warning(f"Analytics peer not found, discarding event: {event}")
        else:
            await self.talk_guild_event(event).send(self.an_app, wait_for_reply=False)

    @LionCog.listener()
    @log_wrap(action='AnEvent')
    async def on_command_completion(self, ctx: LionContext):
        """
        Send command completed successfully.
        """
        duration = utc_now() - ctx.message.created_at
        event = CommandEvent(
            appname=appname,
            cmdname=ctx.command.qualified_name if ctx.command else 'Unknown',
            cogname=ctx.cog.qualified_name if ctx.cog else None,
            userid=ctx.author.id,
            created_at=utc_now(),
            status=CommandStatus.COMPLETED,
            execution_time=duration.total_seconds(),
            guildid=ctx.guild.id if ctx.guild else None,
            ctxid=ctx.message.id
        )
        if self.an_app not in shard_talk.peers:
            logger.warning(f"Analytics peer not found, discarding event: {event}")
        else:
            await self.talk_command_event(event).send(self.an_app, wait_for_reply=False)

    @LionCog.listener()
    @log_wrap(action='AnEvent')
    async def on_command_error(self, ctx: LionContext, error):
        """
        Send command failed.
        """
        duration = utc_now() - ctx.message.created_at
        status = CommandStatus.FAILED
        err_type = None
        try:
            err_type = repr(error)
            raise error
        except (HybridCommandError, CommandInvokeError, appCommandInvokeError):
            original = error.original
            try:
                err_type = repr(original)
                if isinstance(original, (HybridCommandError, CommandInvokeError, appCommandInvokeError)):
                    raise original.original
                else:
                    raise original
            except HandledException:
                status = CommandStatus.CANCELLED
            except SafeCancellation:
                status = CommandStatus.CANCELLED
            except discord.Forbidden:
                status = CommandStatus.CANCELLED
            except discord.HTTPException:
                status = CommandStatus.CANCELLED
            except Exception:
                status = CommandStatus.FAILED
        except CheckFailure:
            status = CommandStatus.CANCELLED
        except Exception:
            status = CommandStatus.FAILED

        event = CommandEvent(
            appname=appname,
            cmdname=ctx.command.name if ctx.command else 'Unknown',
            cogname=ctx.cog.qualified_name if ctx.cog else None,
            userid=ctx.author.id,
            created_at=utc_now(),
            status=status,
            error=err_type,
            execution_time=duration.total_seconds(),
            guildid=ctx.guild.id if ctx.guild else None,
            ctxid=ctx.message.id
        )
        if self.an_app not in shard_talk.peers:
            logger.warning(f"Analytics peer not found, discarding event: {event}")
        else:
            await self.talk_command_event(event).send(self.an_app, wait_for_reply=False)

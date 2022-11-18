from meta import LionCog, LionBot, LionContext

from meta.app import shard_talk, appname
from utils.lib import utc_now

from .data import AnalyticsData
from .events import (
    CommandStatus, CommandEvent, command_event_handler,
    GuildAction, GuildEvent, guild_event_handler,
    VoiceAction, VoiceEvent, voice_event_handler
)


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

    async def cog_load(self):
        await self.data.init()

    @LionCog.listener()
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
        await self.talk_guild_event(event).send(self.an_app, wait_for_reply=False)

    @LionCog.listener()
    async def on_guild_leave(self, guild):
        """
        Send guild leave event
        """
        event = GuildEvent(
            appname=appname,
            guildid=guild.id,
            action=GuildAction.LEFT,
            created_at=utc_now()
        )
        await self.talk_guild_event(event).send(self.an_app, wait_for_reply=False)

    @LionCog.listener()
    async def on_command_completion(self, ctx: LionContext):
        """
        Send command completed successfully.
        """
        event = CommandEvent(
            appname=appname,
            cmdname=ctx.command.name if ctx.command else 'Unknown',
            cogname=ctx.cog.qualified_name if ctx.cog else None,
            userid=ctx.author.id,
            created_at=utc_now(),
            status=CommandStatus.COMPLETED,
            execution_time=0,
            guildid=ctx.guild.id if ctx.guild else None,
            ctxid=ctx.message.id
        )
        await self.talk_command_event(event).send(self.an_app, wait_for_reply=False)

    @LionCog.listener()
    async def on_command_error(self, ctx: LionContext, error):
        """
        Send command failed.
        """
        # TODO: Add command error field?
        ...

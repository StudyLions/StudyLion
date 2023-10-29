from typing import Optional, TYPE_CHECKING
from enum import Enum
import asyncio
import datetime as dt
import pytz
import discord
import logging

from meta import LionBot, conf
from meta.logger import log_wrap
from utils.lib import Timezoned, utc_now
from settings.groups import ModelConfig, SettingDotDict
from babel.translator import ctx_locale

from .hooks import HookedChannel
from .data import CoreData
from . import babel

if TYPE_CHECKING:
    # TODO: Import Settings for Config type hinting
    pass


_p = babel._p

logger = logging.getLogger(__name__)


event_fields = {
    'start': (
        _p('eventlog|field:start|name', "Start"),
        "{value}",
        True,
    ),
    'expiry': (
        _p('eventlog|field:expiry|name', "Expires"),
        "{value}",
        True,
    ),
    'roles_given' : (
        _p('eventlog|field:roles_given|name', "Roles Given"),
        "{value}",
        True,
    ),
    'roles_taken' : (
        _p('eventlog|field:roles_given|name', "Roles Taken"),
        "{value}",
        True,
    ),
    'coins_earned' : (
        _p('eventlog|field:coins_earned|name', "Coins Earned"),
        "{coin} {{value}}".format(coin=conf.emojis.coin),
        True,
    ),
    'price' : (
        _p('eventlog|field:price|name', "Price"),
        "{coin} {{value}}".format(coin=conf.emojis.coin),
        True,
    ),
    'balance' : (
        _p('eventlog|field:balance|name', "Balance"),
        "{coin} {{value}}".format(coin=conf.emojis.coin),
        True,
    ),
    'refund' : (
        _p('eventlog|field:refund|name', "Coins Refunded"),
        "{coin} {{value}}".format(coin=conf.emojis.coin),
        True,
    ),
    'memberid': (
        _p('eventlog|field:memberid|name', "Member"),
        "<@{value}>",
        True,
    ),
    'channelid': (
        _p('eventlog|field:channelid|name', "Channel"),
        "<#{value}>",
        True
    ),
}


class VoiceMode(Enum):
    STUDY = 0
    VOICE = 1


class GuildMode(Enum):
    StudyGuild = (VoiceMode.STUDY,)
    VoiceGuild = (VoiceMode.VOICE,)
    TextGuild = (VoiceMode.VOICE,)

    @property
    def voice(self):
        return self.value[0]


class GuildConfig(ModelConfig):
    settings = SettingDotDict()
    _model_settings = set()
    model = CoreData.Guild

    @property
    def timezone(self):
        return self.get('timezone')


class LionGuild(Timezoned):
    """
    Represents a Guild in the LionBot paradigm.

    Provides central access to cached data and configuration for a Guild.

    No guarantee is made that the client is in the corresponding Guild,
    or that the corresponding Guild even exists.
    """
    __slots__ = (
        'bot', 'data',
        'guildid',
        'config',
        '_guild',
        'voice_lock',
        '_eventlogger',
        '_tasks',
        '__weakref__'
    )

    Config = GuildConfig
    settings = Config.settings

    def __init__(self, bot: LionBot, data: CoreData.Guild, guild: Optional[discord.Guild] = None):
        self.bot = bot
        self.data = data
        self.guildid = data.guildid

        self._guild = guild

        self.config = self.Config(self.guildid, data)

        # Guild-specific voice lock
        # Every module which uses voice alerts should hold this lock throughout the alert.
        # Avoids voice race-states
        self.voice_lock = asyncio.Lock()

        # HookedChannel managing the webhook used to send guild event logs
        # May be None if no event log is set or if the channel does not exist
        self._eventlogger: Optional[HookedChannel] = None

        # Set of background tasks associated with this guild (e.g. event logs)
        # In theory we should ensure these are finished before the lguild is gcd
        # But this is *probably* not an actual problem in practice
        self._tasks = set()

    @property
    def eventlogger(self) -> Optional[HookedChannel]:
        channelid = self.data.event_log_channel
        if channelid is None:
            self._eventlogger = None
        elif self._eventlogger is None or self._eventlogger.channelid != channelid:
            self._eventlogger = self.bot.core.hooked_channel(channelid)
        return self._eventlogger

    @property
    def guild(self):
        if self._guild is None:
            self._guild = self.bot.get_guild(self.guildid)
        return self._guild

    @property
    def guild_mode(self):
        # TODO: Configuration, data, and settings for this...
        return GuildMode.StudyGuild

    @property
    def timezone(self) -> str:
        return self.config.timezone.value

    @property
    def locale(self) -> str:
        return self.config.get('guild_locale').value

    async def touch_discord_model(self, guild: discord.Guild):
        """
        Update saved Discord model attributes for this guild.
        """
        if self.data.name != guild.name:
            await self.data.update(name=guild.name)

    @log_wrap(action='get event hook')
    async def get_event_hook(self) -> Optional[discord.Webhook]:
        hooked = self.eventlogger
        ctx_locale.set(self.locale)

        if hooked:
            hook = await hooked.get_webhook()
            if hook is not None:
                pass
            elif (channel := hooked.channel) is None:
                # Event log channel doesn't exist
                pass
            elif not channel.permissions_for(channel.guild.me).manage_webhooks:
                # Cannot create a webhook here
                if channel.permissions_for(channel.guild.me).send_messages:
                    t = self.bot.translator.t
                    try:
                        await channel.send(t(_p(
                            'eventlog|error:manage_webhooks',
                            "This channel is configured as an event log, "
                            "but I am missing the 'Manage Webhooks' permission here."
                        )))
                    except discord.HTTPException:
                        pass
            else:
                # We should be able to create the hook
                t = self.bot.translator.t
                try:
                    hook = await hooked.create_webhook(
                        name=t(_p(
                            'eventlog|create|name',
                            "{bot_name} Event Log"
                        )).format(bot_name=channel.guild.me.name),
                        reason=t(_p(
                            'eventlog|create|audit_reason',
                            "Creating event log webhook"
                        )),
                    )
                except discord.HTTPException:
                    logger.warning(
                        f"Unexpected exception while creating event log webhook for <gid: {self.guildid}>",
                        exc_info=True
                    )
            return hook

    @log_wrap(action="Log Event")
    async def _log_event(self, embed: discord.Embed, retry=True):
        logger.debug(f"Logging event log event: {embed.to_dict()}")

        hook = await self.get_event_hook()
        if hook is not None:
            try:
                await hook.send(embed=embed)
            except discord.NotFound:
                logger.info(
                    f"Event log in <gid: {self.guildid}> invalidated. Recreating: {retry}"
                )
                hooked = self.eventlogger
                if hooked is not None:
                    await hooked.invalidate(hook)
                    if retry:
                        await self._log_event(embed, retry=False)
            except discord.HTTPException:
                logger.warning(
                    f"Discord exception occurred sending event log event: {embed.to_dict()}.",
                    exc_info=True
                )
            except Exception:
                logger.exception(
                    f"Unknown exception occurred sending event log event: {embed.to_dict()}."
                )

    def log_event(self,
                  title: Optional[str]=None, description: Optional[str]=None,
                  timestamp: Optional[dt.datetime]=None,
                  *,
                  embed: Optional[discord.Embed] = None,
                  fields: dict[str, tuple[str, bool]]={},
                  errors: list[str]=[],
                  **kwargs: str | int):
        """
        Synchronously log an event to the guild event log.

        Does nothing if the event log has not been set up.

        Parameters
        ----------
        title: str
            Embed title
        description: str
            Embed description
        timestamp: dt.datetime
            Embed timestamp. Defaults to `now` if not given.
        embed: discord.Embed
            Optional base embed to use.
            May be used to completely customise log message.
        fields: dict[str, tuple[str, bool]]
            Optional embed fields to add.
        errors: list[str]
            Optional list of errors to add.
            Errors will always be added last.
        kwargs: str | int
            Optional embed fields to add to the embed.
            These differ from `fields` in that the kwargs keys will be automatically matched and localised
            if possible.
            These will be added before the `fields` given.
        """
        t = self.bot.translator.t

        # Build embed
        if embed is not None:
            base = embed
        else:
            base = discord.Embed(
                colour=(discord.Colour.brand_red() if errors else discord.Colour.dark_orange())
            )
        if description is not None:
            base.description = description
        if title is not None:
            base.title = title
        if timestamp is not None:
            base.timestamp = timestamp
        else:
            base.timestamp = utc_now()

        # Add embed fields
        for key, value in kwargs.items():
            if value is None:
                continue
            if key in event_fields:
                _field_name, _field_value, inline = event_fields[key]
                field_name = t(_field_name, locale=self.locale)
                field_value = _field_value.format(value=value)
            else:
                field_name = key
                field_value = value
                inline = False
            base.add_field(
                name=field_name,
                value=field_value,
                inline=inline
            )

        for key, (value, inline) in fields.items():
            base.add_field(
                name=key,
                value=value,
                inline=inline,
            )

        if errors:
            error_name = t(_p(
                'eventlog|field:errors|name',
                "Errors"
            ))
            error_value = '\n'.join(f"- {line}" for line in errors)
            base.add_field(
                name=error_name, value=error_value, inline=False
            )

        # Send embed
        task = asyncio.create_task(self._log_event(embed=base), name='event-log')
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

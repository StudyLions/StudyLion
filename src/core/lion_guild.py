from typing import Optional, TYPE_CHECKING
from enum import Enum
import pytz
import discord

from meta import LionBot
from utils.lib import Timezoned
from settings.groups import ModelConfig, SettingDotDict

from .data import CoreData

if TYPE_CHECKING:
    # TODO: Import Settings for Config type hinting
    pass


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
    __slots__ = ('bot', 'data', 'guildid', 'config', '_guild', '__weakref__')

    Config = GuildConfig
    settings = Config.settings

    def __init__(self, bot: LionBot, data: CoreData.Guild, guild: Optional[discord.Guild] = None):
        self.bot = bot
        self.data = data
        self.guildid = data.guildid

        self._guild = guild

        self.config = self.Config(self.guildid, data)

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
    def timezone(self) -> pytz.timezone:
        return self.config.timezone.value

    async def touch_discord_model(self, guild: discord.Guild):
        """
        Update saved Discord model attributes for this guild.
        """
        if self.data.name != guild.name:
            await self.data.update(name=guild.name)

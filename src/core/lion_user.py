from typing import Optional
import discord
import pytz

from meta import LionBot
from utils.lib import utc_now, Timezoned
from settings.groups import ModelConfig, SettingDotDict

from .data import CoreData


class UserConfig(ModelConfig):
    settings = SettingDotDict()
    _model_settings = set()
    model = CoreData.User

    @property
    def timezone(self) -> pytz.timezone:
        return self.get('timezone')


class LionUser(Timezoned):
    """
    Represents a User in the LionBot paradigm.

    Provides central access to cached data and configuration for a User.

    No guarantee is made that the client has access to this User.
    """
    __slots__ = ('bot', 'data', 'userid', '_user', 'config', '__weakref__')

    Config = UserConfig
    settings = Config.settings

    def __init__(self, bot: LionBot, data: CoreData.User, user: Optional[discord.User] = None):
        self.bot = bot
        self.data = data
        self.userid = data.userid

        self._user = user

        self.config = self.Config(self.userid, data)

    @property
    def user(self):
        if self._user is None:
            self._user = self.bot.get_user(self.userid)
        return self._user

    @property
    def timezone(self) -> pytz.timezone:
        return self.config.timezone.value or pytz.UTC

    async def touch_discord_model(self, user: discord.User, seen=True):
        """
        Updated stored Discord model attributes for this user.
        """
        to_update = {}

        avatar_key = user.avatar.key if user.avatar else None
        if self.data.avatar_hash != avatar_key:
            to_update['avatar_hash'] = avatar_key

        if self.data.name != user.name:
            to_update['name'] = user.name

        if seen:
            to_update['last_seen'] = utc_now()

        if to_update:
            await self.data.update(**to_update)

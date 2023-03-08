from typing import Optional
import datetime as dt
import pytz
import discord

from meta import LionBot
from utils.lib import Timezoned
from settings.groups import ModelConfig, SettingDotDict

from .data import CoreData
from .lion_user import LionUser
from .lion_guild import LionGuild


class MemberConfig(ModelConfig):
    settings = SettingDotDict()
    _model_settings = set()
    model = CoreData.Member


class LionMember(Timezoned):
    """
    Represents a member in the LionBot paradigm.

    Acts as a central interface to the member, user, and guild configurations.

    No guarantee is made that any corresponding Discord objects are accessible (or exist).
    """
    __slots__ = ('bot', 'data', 'userid', 'guildid', 'config', 'luser', 'lguild', '_member', '__weakref__')

    Config = MemberConfig
    settings = Config.settings

    def __init__(
        self,
        bot: LionBot, data: CoreData.Member,
        lguild: LionGuild, luser: LionUser,
        member: Optional[discord.Member] = None
    ):
        self.bot = bot
        self.data = data
        self.userid = data.userid
        self.guildid = data.guildid

        self.lguild = lguild
        self.luser = luser

        self._member = member

    @property
    def member(self):
        """
        The associated Discord member, if accessible.
        """
        if self._member is None:
            if (guild := self.lguild.guild) is not None:
                self._member = guild.get_member(self.userid)
        return self._member

    @property
    def timezone(self) -> pytz.timezone:
        user_timezone = self.luser.config.timezone
        guild_timezone = self.lguild.config.timezone
        return user_timezone.value if user_timezone._data is not None else guild_timezone.value

    async def touch_discord_model(self, member: discord.Member):
        """
        Update saved Discord model attributes for this member.
        """
        if member.display_name != self.data.display_name:
            await self.data.update(display_name=member.display_name)

    async def fetch_member(self) -> Optional[discord.Member]:
        """
        Fetches the associated member through the API. Respects cache.
        """
        if (member := self.member) is None:
            if (guild := self.lguild.guild) is not None:
                try:
                    member = await guild.fetch_member(self.userid)
                    self._member = member
                except discord.HTTPException:
                    pass
        return member

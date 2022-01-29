import pytz
import discord
from functools import reduce
from datetime import datetime, timedelta

from meta import client
from data import tables as tb
from settings import UserSettings, GuildSettings

from LionContext import LionContext


class Lion:
    """
    Class representing a guild Member.
    Mostly acts as a transparent interface to the corresponding Row,
    but also adds some transaction caching logic to `coins` and `tracked_time`.
    """
    __slots__ = ('guildid', 'userid', '_pending_coins', '_member')

    # Members with pending transactions
    _pending = {}  # userid -> User

    # Lion cache. Currently lions don't expire
    _lions = {}  # (guildid, userid) -> Lion

    # Extra methods supplying an economy bonus
    _economy_bonuses = []

    def __init__(self, guildid, userid):
        self.guildid = guildid
        self.userid = userid

        self._pending_coins = 0

        self._member = None

        self._lions[self.key] = self

    @classmethod
    def fetch(cls, guildid, userid):
        """
        Fetch a Lion with the given member.
        If they don't exist, creates them.
        If possible, retrieves the user from the user cache.
        """
        key = (guildid, userid)
        if key in cls._lions:
            return cls._lions[key]
        else:
            # TODO: Debug log
            lion = tb.lions.fetch(key)
            if not lion:
                tb.user_config.fetch_or_create(userid)
                tb.guild_config.fetch_or_create(guildid)
                tb.lions.create_row(
                    guildid=guildid,
                    userid=userid,
                    coins=GuildSettings(guildid).starting_funds.value
                )
            return cls(guildid, userid)

    @property
    def key(self):
        return (self.guildid, self.userid)

    @property
    def guild(self) -> discord.Guild:
        return client.get_guild(self.guildid)

    @property
    def member(self) -> discord.Member:
        """
        The discord `Member` corresponding to this user.
        May be `None` if the member is no longer in the guild or the caches aren't populated.
        Not guaranteed to be `None` if the member is not in the guild.
        """
        if self._member is None:
            guild = client.get_guild(self.guildid)
            if guild:
                self._member = guild.get_member(self.userid)
        return self._member

    @property
    def data(self):
        """
        The Row corresponding to this member.
        """
        return tb.lions.fetch(self.key)

    @property
    def user_data(self):
        """
        The Row corresponding to this user.
        """
        return tb.user_config.fetch_or_create(self.userid)

    @property
    def guild_data(self):
        """
        The Row corresponding to this guild.
        """
        return tb.guild_config.fetch_or_create(self.guildid)

    @property
    def settings(self):
        """
        The UserSettings interface for this member.
        """
        return UserSettings(self.userid)

    @property
    def guild_settings(self):
        """
        The GuildSettings interface for this member.
        """
        return GuildSettings(self.guildid)

    @property
    def ctx(self) -> LionContext:
        """
        Manufacture a `LionContext` with the lion member as an author.
        Useful for accessing member context utilities.
        Be aware that `author` may be `None` if the member was not cached.
        """
        return LionContext(client, guild=self.guild, author=self.member)

    @property
    def time(self):
        """
        Amount of time the user has spent studying, accounting for a current session.
        """
        # Base time from cached member data
        time = self.data.tracked_time

        # Add current session time if it exists
        if session := self.session:
            time += session.duration

        return int(time)

    @property
    def coins(self):
        """
        Number of coins the user has, accounting for the pending value and current session.
        """
        # Base coin amount from cached member data
        coins = self.data.coins

        # Add pending coin amount
        coins += self._pending_coins

        # Add current session coins if applicable
        if session := self.session:
            coins += session.coins_earned

        return int(coins)

    @property
    def economy_bonus(self):
        """
        Economy multiplier
        """
        return reduce(
            lambda x, y: x * y,
            [func(self) for func in self._economy_bonuses]
        )

    @classmethod
    def register_economy_bonus(cls, func):
        cls._economy_bonuses.append(func)

    @classmethod
    def unregister_economy_bonus(cls, func):
        cls._economy_bonuses.remove(func)

    @property
    def session(self):
        """
        The current study session the user is in, if any.
        """
        if 'sessions' not in client.objects:
            raise ValueError("Cannot retrieve session before Study module is initialised!")
        return client.objects['sessions'][self.guildid].get(self.userid, None)

    @property
    def timezone(self):
        """
        The user's configured timezone.
        Shortcut to `Lion.settings.timezone.value`.
        """
        return self.settings.timezone.value

    @property
    def day_start(self):
        """
        A timezone aware datetime representing the start of the user's day (in their configured timezone).
        NOTE: This might not be accurate over DST boundaries.
        """
        now = datetime.now(tz=self.timezone)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    @property
    def day_timestamp(self):
        """
        EPOCH timestamp representing the current day for the user.
        NOTE: This is the timestamp of the start of the current UTC day with the same date as the user's day.
        This is *not* the start of the current user's day, either in UTC or their own timezone.
        This may also not be the start of the current day in UTC (consider 23:00 for a user in UTC-2).
        """
        now = datetime.now(tz=self.timezone)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(day_start.replace(tzinfo=pytz.utc).timestamp())

    @property
    def week_timestamp(self):
        """
        EPOCH timestamp representing the current week for the user.
        """
        now = datetime.now(tz=self.timezone)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=day_start.weekday())
        return int(week_start.replace(tzinfo=pytz.utc).timestamp())

    @property
    def month_timestamp(self):
        """
        EPOCH timestamp representing the current month for the user.
        """
        now = datetime.now(tz=self.timezone)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return int(month_start.replace(tzinfo=pytz.utc).timestamp())

    @property
    def remaining_in_day(self):
        return ((self.day_start + timedelta(days=1)) - datetime.now(self.timezone)).total_seconds()

    @property
    def studied_today(self):
        """
        The amount of time, in seconds, that the member has studied today.
        Extracted from the session history.
        """
        return tb.session_history.queries.study_time_since(self.guildid, self.userid, self.day_start)

    @property
    def remaining_study_today(self):
        """
        Maximum remaining time (in seconds) this member can study today.

        May not account for DST boundaries and leap seconds.
        """
        studied_today = self.studied_today
        study_cap = self.guild_settings.daily_study_cap.value

        remaining_in_day = self.remaining_in_day
        if remaining_in_day >= (study_cap - studied_today):
            remaining = study_cap - studied_today
        else:
            remaining = remaining_in_day + study_cap

        return remaining

    @property
    def profile_tags(self):
        """
        Returns a list of profile tags, or the default tags.
        """
        tags = tb.profile_tags.queries.get_tags_for(self.guildid, self.userid)
        prefix = self.ctx.best_prefix
        return tags or [
            f"Use {prefix}setprofile",
            "and add your tags",
            "to this section",
            f"See {prefix}help setprofile for more"
        ]

    @property
    def name(self):
        """
        Returns the best local name possible.
        """
        if self.member:
            name = self.member.display_name
        elif self.data.display_name:
            name = self.data.display_name
        else:
            name = str(self.userid)

        return name

    def update_saved_data(self, member: discord.Member):
        """
        Update the stored discord data from the givem member.
        Intended to be used when we get member data from events that may not be available in cache.
        """
        if self.guild_data.name != member.guild.name:
            self.guild_data.name = member.guild.name
        if self.user_data.avatar_hash != member.avatar:
            self.user_data.avatar_hash = member.avatar
        if self.data.display_name != member.display_name:
            self.data.display_name = member.display_name

    def localize(self, naive_utc_dt):
        """
        Localise the provided naive UTC datetime into the user's timezone.
        """
        timezone = self.settings.timezone.value
        return naive_utc_dt.replace(tzinfo=pytz.UTC).astimezone(timezone)

    def addCoins(self, amount, flush=True, bonus=False):
        """
        Add coins to the user, optionally store the transaction in pending.
        """
        self._pending_coins += amount * (self.economy_bonus if bonus else 1)
        self._pending[self.key] = self
        if flush:
            self.flush()

    def flush(self):
        """
        Flush any pending transactions to the database.
        """
        self.sync(self)

    @classmethod
    def sync(cls, *lions):
        """
        Flush pending transactions to the database.
        Also refreshes the Row cache for updated lions.
        """
        lions = lions or list(cls._pending.values())

        if lions:
            # Build userid to pending coin map
            pending = [
                (lion.guildid, lion.userid, int(lion._pending_coins))
                for lion in lions
            ]

            # Write to database
            tb.lions.queries.add_pending(pending)

            # Cleanup pending users
            for lion in lions:
                lion._pending_coins -= int(lion._pending_coins)
                cls._pending.pop(lion.key, None)

import pytz
import datetime

from meta import client
from data import tables as tb
from settings import UserSettings, GuildSettings


class Lion:
    """
    Class representing a guild Member.
    Mostly acts as a transparent interface to the corresponding Row,
    but also adds some transaction caching logic to `coins` and `tracked_time`.
    """
    __slots__ = ('guildid', 'userid', '_pending_coins', '_pending_time', '_member')

    # Members with pending transactions
    _pending = {}  # userid -> User

    # Lion cache. Currently lions don't expire
    _lions = {}  # (guildid, userid) -> Lion

    def __init__(self, guildid, userid):
        self.guildid = guildid
        self.userid = userid

        self._pending_coins = 0
        self._pending_time = 0

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
    def member(self):
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
        The Row corresponding to this user.
        """
        return tb.lions.fetch(self.key)

    @property
    def settings(self):
        """
        The UserSettings object for this user.
        """
        return UserSettings(self.userid)

    @property
    def time(self):
        """
        Amount of time the user has spent studying, accounting for pending values.
        """
        return int(self.data.tracked_time + self._pending_time)

    @property
    def coins(self):
        """
        Number of coins the user has, accounting for the pending value.
        """
        return int(self.data.coins + self._pending_coins)

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
        """
        now = datetime.datetime.now(tz=self.timezone)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    @property
    def studied_today(self):
        """
        The amount of time, in seconds, that the member has studied today.
        Extracted from the session history.
        """
        return tb.session_history.queries.study_time_since(self.guildid, self.userid, self.day_start)

    def localize(self, naive_utc_dt):
        """
        Localise the provided naive UTC datetime into the user's timezone.
        """
        timezone = self.settings.timezone.value
        return naive_utc_dt.replace(tzinfo=pytz.UTC).astimezone(timezone)

    def addCoins(self, amount, flush=True):
        """
        Add coins to the user, optionally store the transaction in pending.
        """
        self._pending_coins += amount
        self._pending[self.key] = self
        if flush:
            self.flush()

    def addTime(self, amount, flush=True):
        """
        Add time to a user (in seconds), optionally storing the transaction in pending.
        """
        self._pending_time += amount
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
                (lion.guildid, lion.userid, int(lion._pending_coins), int(lion._pending_time))
                for lion in lions
            ]

            # Write to database
            tb.lions.queries.add_pending(pending)

            # Cleanup pending users
            for lion in lions:
                lion._pending_coins -= int(lion._pending_coins)
                lion._pending_time -= int(lion._pending_time)
                cls._pending.pop(lion.key, None)

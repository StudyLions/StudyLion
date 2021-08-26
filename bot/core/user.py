from . import tables as tb
from meta import conf, client


class User:
    """
    Class representing a "Lion", i.e. a member of the managed guild.
    Mostly acts as a transparent interface to the corresponding Row,
    but also adds some transaction caching logic to `coins`.
    """
    __slots__ = ('userid', '_pending_coins', '_member')

    # Users with pending transactions
    _pending = {}  # userid -> User

    # User cache. Currently users don't expire
    _users = {}  # userid -> User

    def __init__(self, userid):
        self.userid = userid
        self._pending_coins = 0

        self._users[self.userid] = self

    @classmethod
    def fetch(cls, userid):
        """
        Fetch a User with the given userid.
        If they don't exist, creates them.
        If possible, retrieves the user from the user cache.
        """
        if userid in cls._users:
            return cls._users[userid]
        else:
            tb.users.fetch_or_create(userid)
            return cls(userid)

    @property
    def member(self):
        """
        The discord `Member` corresponding to this user.
        May be `None` if the member is no longer in the guild or the caches aren't populated.
        Not guaranteed to be `None` if the member is not in the guild.
        """
        if self._member is None:
            self._member = client.get_guild(conf.meta.getint('managed_guild_id')).get_member(self.userid)

    @property
    def data(self):
        """
        The Row corresponding to this user.
        """
        return tb.users.fetch(self.userid)

    @property
    def time(self):
        """
        Amount of time the user has spent.. studying?
        """
        return self.data.tracked_time

    @property
    def coins(self):
        """
        Number of coins the user has, accounting for the pending value.
        """
        return self.data.coins + self._pending_coins

    def addCoins(self, amount, flush=True):
        """
        Add coins to the user, optionally store the transaction in pending.
        """
        self._pending_coins += amount
        if self._pending_coins != 0:
            self._pending[self.userid] = self
        else:
            self._pending.pop(self.userid, None)
        if flush:
            self.flush()

    def flush(self):
        """
        Flush any pending transactions to the database.
        """
        self.sync(self)

    @classmethod
    def sync(cls, *users):
        """
        Flush pending transactions to the database.
        Also refreshes the Row cache for updated users.
        """
        users = users or list(cls._pending.values())

        if users:
            # Build userid to pending coin map
            userid_coins = [(user.userid, user._pending_coins) for user in users]

            # Write to database
            tb.users.queries.add_coins(userid_coins)

            # Cleanup pending users
            for user in users:
                user._pending_coins = 0
                cls._pending.pop(user.userid, None)

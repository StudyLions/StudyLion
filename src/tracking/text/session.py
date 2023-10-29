from typing import Optional
import asyncio
import datetime as dt

import discord

from utils.lib import utc_now


class TextSession:
    """
    Represents an ongoing text session for a single member.

    Attributes
    ----------
    userid
    guildid
    start_time
    total_messages
    total_words
    total_periods
    this_period_start
    this_period_messages
    this_period_words
    timeout
    """
    __slots__ = (
        'userid', 'guildid',
        'start_time', 'end_time',
        'total_messages', 'total_words', 'total_periods',
        'this_period_start', 'this_period_messages', 'this_period_words',
        'last_message_at', 'timeout_task',
        'finish_callback', 'finish_task', 'finished', 'finished_at',
    )

    # Length of a single period
    # period_length = 5 * 60
    period_length = 10
    timeout_length = 2 * period_length

    # Maximum length of a session
    # session_length = 60 * 60
    session_length = 120

    def __init__(self, userid, guildid, start_time):
        self.userid = userid
        self.guildid = guildid

        self.start_time = start_time
        self.end_time = start_time + dt.timedelta(seconds=self.session_length)

        self.total_messages = 0
        self.total_words = 0
        self.total_periods = 0

        self.this_period_start = start_time
        self.this_period_messages = 0
        self.this_period_words = 0

        self.last_message_at = None
        self.timeout_task = None

        self.finish_callback = None
        self.finish_task = None
        self.finished = asyncio.Event()
        self.finished_at = None

    @property
    def duration(self) -> int:
        if self.start_time is None:
            raise ValueError("Cannot take duration of uninitialised session!")

        end = self.finished_at or utc_now()
        return int((end - self.start_time).total_seconds())

    def __repr__(self):
        return (
            "("
            "{self.__class__.__name__}: "
            "userid={self.userid}, "
            "guildid={self.guildid}, "
            "start_time={self.start_time}, "
            "end_time={self.end_time}, "
            "total_messages={self.total_messages}, "
            "total_words={self.total_words}, "
            "total_periods={self.total_periods}, "
            "last_message_at={self.last_message_at}, "
            "finished_at={self.finished_at}"
            ")"
        ).format(self=self)

    @classmethod
    def from_message(cls, message: discord.Message):
        """
        Instantiate a new TextSession from an initial discord message.

        Does not process the given message.
        """
        if not message.guild:
            raise ValueError("Cannot initialise from message outside of Guild context!")
        self = cls(message.author.id, message.guild.id,  message.created_at)
        return self

    def process(self, message: discord.Message):
        """
        Process a message into the session.
        """
        if not message.guild:
            return

        if (message.author.id != self.userid) or (message.guild.id != self.guildid):
            raise ValueError("Invalid attempt to process message from a different member!")

        # Identify if we need to start a new period
        start = self.this_period_start
        if start is not None and (message.created_at - start).total_seconds() < self.period_length:
            self.this_period_messages += 1
            self.this_period_words += len(message.content.split())
        else:
            self.roll_period()
            self.this_period_start = message.created_at
            self.this_period_messages = 1
            self.this_period_words = len(message.content.split())
        self.last_message_at = message.created_at

        # Update the session expiry
        self._reschedule_timeout(self.last_message_at + dt.timedelta(seconds=self.timeout_length))

    def roll_period(self):
        """
        Add pending stats from the current period, and start a new period.
        """
        if self.this_period_messages:
            self.total_messages += self.this_period_messages
            self.total_words += self.this_period_words
            self.total_periods += 1
        self.this_period_start = None

    async def finish(self):
        """
        Finalise the session and set the finished event. Idempotent.

        Also calls the registered finish callback, if set.
        """
        if self.finished.is_set():
            return

        self.roll_period()
        self.finished_at = self.last_message_at or utc_now()

        self.finished.set()
        if self.finish_callback:
            await self.finish_callback(self)

    async def cancel(self):
        """
        Cancel this session.

        Does not execute the finish_callback.
        """
        ...

    def on_finish(self, callback):
        """
        Register a callback coroutine to be executed when the session finishes.
        """
        self.finish_callback = callback

    async def _timeout(self, diff):
        if diff > 0:
            await asyncio.sleep(diff)
        await asyncio.shield(self.finish())

    def _reschedule_timeout(self, target_time):
        """
        Schedule the finish timeout for the given target time.
        """
        if self.finished.is_set():
            return
        if self.finish_task and not self.finish_task.cancelled():
            self.finish_task.cancel()

        target_time = min(self.end_time, target_time)
        dist = (target_time - utc_now()).total_seconds()
        self.finish_task = asyncio.create_task(self._timeout(dist))

from typing import Optional
from collections import defaultdict
import datetime as dt
import asyncio
import itertools

import discord

from meta import LionBot
from utils.lib import utc_now
from core.lion_member import LionMember

from .. import babel, logger
from ..data import ScheduleData as Data
from ..lib import slotid_to_utc

_p = babel._p


class SessionMember:
    """
    Member context for a scheduled session timeslot.

    Intended to keep track of members for ongoing and upcoming sessions.
    Primarily used to track clock time and set attended status.
    """
    # TODO: slots

    def __init__(self,
                 bot: LionBot, data: Data.ScheduleSessionMember,
                 lion: LionMember):
        self.bot = bot
        self.data = data
        self.lion = lion

        self.slotid = data.slotid
        self.slot_start = slotid_to_utc(self.slotid)
        self.slot_end = slotid_to_utc(self.slotid + 3600)
        self.userid = data.userid
        self.guildid = data.guildid

        self.clock_start = None
        self.clocked = 0

    @property
    def total_clock(self):
        clocked = self.clocked
        if self.clock_start is not None:
            end = min(utc_now(), self.slot_end)
            clocked += (end - self.clock_start).total_seconds()
        return clocked

    def clock_on(self, at: dt.datetime):
        """
        Mark this member as attending the scheduled session.
        """
        if self.clock_start:
            self.clock_off(at)
        self.clock_start = max(self.slot_start, at)

    def clock_off(self, at: dt.datetime):
        """
        Mark this member as no longer attending.
        """
        if not self.clock_start:
            raise ValueError("Member clocking off while already off.")
        end = min(at, self.slot_end)
        self.clocked += (end - self.clock_start).total_seconds()
        self.clock_start = None

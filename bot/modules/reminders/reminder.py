import asyncio
import datetime
import logging
import discord

from meta import client, sharding
from utils.lib import strfdur

from .data import reminders
from .module import module


class Reminder:
    __slots__ = ('reminderid', '_task')

    _live_reminders = {}  # map reminderid -> Reminder

    def __init__(self, reminderid):
        self.reminderid = reminderid

        self._task = None

    @classmethod
    def create(cls, **kwargs):
        row = reminders.create_row(**kwargs)
        return cls(row.reminderid)

    @classmethod
    def fetch(cls, *reminderids):
        """
        Fetch an live reminders associated to the given reminderids.
        """
        return [
            cls._live_reminders[reminderid]
            for reminderid in reminderids
            if reminderid in cls._live_reminders
        ]

    @classmethod
    def delete(cls, *reminderids):
        """
        Cancel and delete the given reminders in an idempotent fashion.
        """
        # Cancel the rmeinders
        for reminderid in reminderids:
            if reminderid in cls._live_reminders:
                cls._live_reminders[reminderid].cancel()

        # Remove from data
        if reminderids:
            return reminders.delete_where(reminderid=reminderids)
        else:
            return []

    @property
    def data(self):
        return reminders.fetch(self.reminderid)

    @property
    def timestamp(self):
        """
        True unix timestamp for (next) reminder time.
        """
        return int(self.data.remind_at.replace(tzinfo=datetime.timezone.utc).timestamp())

    @property
    def user(self):
        """
        The discord.User that owns this reminder, if we can find them.
        """
        return client.get_user(self.data.userid)

    @property
    def formatted(self):
        """
        Single-line string format for the reminder, intended for an embed.
        """
        content = self.data.content
        trunc_content = content[:50] + '...' * (len(content) > 50)

        if self.data.interval:
            interval = self.data.interval
            if interval == 24 * 60 * 60:
                interval_str = "day"
            elif interval == 60 * 60:
                interval_str = "hour"
            elif interval % (24 * 60 * 60) == 0:
                interval_str = "`{}` days".format(interval // (24 * 60 * 60))
            elif interval % (60 * 60) == 0:
                interval_str = "`{}` hours".format(interval // (60 * 60))
            else:
                interval_str = "`{}`".format(strfdur(interval))

            repeat = "(Every {})".format(interval_str)
        else:
            repeat = ""

        return "<t:{timestamp}:R>, [{content}]({jump_link}) {repeat}".format(
            jump_link=self.data.message_link,
            content=trunc_content,
            timestamp=self.timestamp,
            repeat=repeat
        )

    def cancel(self):
        """
        Cancel the live reminder waiting task, if it exists.
            Does not remove the reminder from data. Use `Reminder.delete` for this.
        """
        if self._task and not self._task.done():
            self._task.cancel()
        self._live_reminders.pop(self.reminderid, None)

    def schedule(self):
        """
        Schedule this reminder to be executed.
        """
        asyncio.create_task(self._schedule())
        self._live_reminders[self.reminderid] = self

    async def _schedule(self):
        """
        Execute this reminder after a sleep.
        Accepts cancellation by aborting the scheduled execute.
        """
        # Calculate time left
        remaining = (self.data.remind_at - datetime.datetime.utcnow()).total_seconds()

        # Create the waiting task and wait for it, accepting cancellation
        self._task = asyncio.create_task(asyncio.sleep(remaining))
        try:
            await self._task
        except asyncio.CancelledError:
            return
        await self._execute()

    async def _execute(self):
        """
        Execute the reminder.
        """
        if not self.data:
            # Reminder deleted elsewhere
            return

        if self.data.userid in client.user_blacklist():
            self.delete(self.reminderid)
            return

        userid = self.data.userid

        # Build the message embed
        embed = discord.Embed(
            title="You asked me to remind you!",
            colour=discord.Colour.orange(),
            description=self.data.content,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Context?", value="[Click here]({})".format(self.data.message_link))

        if self.data.interval:
            embed.add_field(
                name="Next reminder",
                value="<t:{}:R>".format(
                    self.timestamp + self.data.interval
                )
            )

        # Update the reminder data, and reschedule if required
        if self.data.interval:
            next_time = self.data.remind_at + datetime.timedelta(seconds=self.data.interval)
            rows = reminders.update_where(
                {'remind_at': next_time},
                reminderid=self.reminderid
            )
            self.schedule()
        else:
            rows = self.delete(self.reminderid)
        if not rows:
            # Reminder deleted elsewhere
            return

        # Send the message, if possible
        if not (user := client.get_user(userid)):
            try:
                user = await client.fetch_user(userid)
            except discord.HTTPException:
                pass
        if user:
            try:
                await user.send(embed=embed)
            except discord.HTTPException:
                # Nothing we can really do here. Maybe tell the user about their reminder next time?
                pass


async def reminder_poll(client):
    """
    One client/shard must continually poll for new or deleted reminders.
    """
    # TODO: Clean this up with database signals or IPC
    while True:
        await asyncio.sleep(60)

        client.log(
            "Running new reminder poll.",
            context="REMINDERS",
            level=logging.DEBUG
        )

        rids = {row.reminderid for row in reminders.fetch_rows_where()}

        to_delete = (rid for rid in Reminder._live_reminders if rid not in rids)
        Reminder.delete(*to_delete)

        [Reminder(rid).schedule() for rid in rids if rid not in Reminder._live_reminders]


@module.launch_task
async def schedule_reminders(client):
    if sharding.shard_number == 0:
        rows = reminders.fetch_rows_where()
        for row in rows:
            Reminder(row.reminderid).schedule()
        client.log(
            "Scheduled {} reminders.".format(len(rows)),
            context="LAUNCH_REMINDERS"
        )
        if sharding.sharded:
            asyncio.create_task(reminder_poll(client))

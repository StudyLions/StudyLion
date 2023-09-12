"""
Max 25 reminders (propagating Discord restriction)

/reminders show
-- Widget which displays and allows removing reminders.
-- Points to /remindme for setting
/reminders clear
/reminders remove <reminder: acmpl>
-- Can we autocomplete an integer field?
/remindme at <time: time> <repeat every: acmpl str> <reminder: str>
/remindme in <days: int> <hours: int> <minutes: int> <repeat every: acmpl str> <reminder: str>
"""
from typing import Optional
import datetime as dt
from cachetools import TTLCache

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.app_commands import Transform
from dateutil.parser import parse, ParserError

from data.queries import ORDER

from meta import LionBot, LionCog, LionContext
from meta.errors import UserInputError
from meta.app import shard_talk, appname_from_shard
from meta.logger import log_wrap, set_logging_context

from babel import ctx_translator, ctx_locale

from utils.lib import parse_duration, utc_now, strfdur, error_embed, check_dm
from utils.monitor import TaskMonitor
from utils.transformers import DurationTransformer
from utils.ui import AButton, AsComponents
from utils.ratelimits import Bucket

from . import babel, logger
from .data import ReminderData
from .ui import ReminderList

_, _p, _np = babel._, babel._p, babel._np


class ReminderMonitor(TaskMonitor[int]):
    ...


class Reminders(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(ReminderData())

        # Whether this process should handle reminder execution
        self.executor = (self.bot.shard_id == 0)
        self.executor_name = appname_from_shard(0)

        if self.executor:
            self.monitor: Optional[ReminderMonitor] = ReminderMonitor(
                executor=self.execute_reminder,
                bucket=Bucket(5, 10)
            )
        else:
            self.monitor = None

        self.talk_reload = shard_talk.register_route('reload_reminders')(self.reload_reminders)
        self.talk_schedule = shard_talk.register_route('schedule_reminders')(self.schedule_reminders)
        self.talk_cancel = shard_talk.register_route('cancel_reminders')(self.cancel_reminders)

        # Short term userid -> list[Reminder] cache, mainly for autocomplete
        self._user_reminder_cache: TTLCache[int, list[ReminderData.Reminder]] = TTLCache(1000, ttl=60)
        self._active_reminderlists: dict[int, ReminderList] = {}

    async def cog_load(self):
        await self.data.init()

        if self.executor and self.bot.is_ready():
            await self.on_ready()

    @LionCog.listener()
    async def on_ready(self):
        if self.executor:
            if self.monitor and self.monitor._monitor_task:
                self.monitor._monitor_task.cancel()

            # Attach and populate the reminder monitor
            self.monitor = ReminderMonitor(executor=self.execute_reminder, bucket=Bucket(5, 10))
            await self.reload_reminders()

            # Start firing reminders
            self.monitor.start()

    # ----- Cog API -----

    async def create_reminder(
        self,
        userid: int, remind_at: dt.datetime, content: str,
        message_link: Optional[str] = None,
        interval: Optional[int] = None,
        created_at: Optional[dt.datetime] = None,
    ) -> ReminderData.Reminder:
        """
        Create and schedule a new reminder from user-entered data.

        Raises UserInputError if the requested parameters are invalid.
        """
        now = utc_now()

        if remind_at <= now:
            t = self.bot.translator.t
            raise UserInputError(
                t(_p(
                    'create_reminder|error:past',
                    "The provided reminder time {timestamp} is in the past!"
                )).format(timestamp=discord.utils.format_dt(remind_at))
            )

        if interval is not None and interval < 600:
            t = self.bot.translator.t
            raise UserInputError(
                t(_p(
                    'create_reminder|error:too_fast',
                    "You cannot set a repeating reminder with a period less than 10 minutes."
                ))
            )

        existing = await self.data.Reminder.fetch_where(userid=userid)
        if len(existing) >= 25:
            t = self.bot.translator.t
            raise UserInputError(
                t(_p(
                    'create_reminder|error:too_many',
                    "Sorry, you have reached the maximum of `25` reminders."
                ))
            )

        user = self.bot.get_user(userid)
        if not user:
            user = await self.bot.fetch_user(userid)
        if not user:
            raise ValueError(f"Target user {userid} does not exist.")

        can_dm = await check_dm(user)
        if not can_dm:
            t = self.bot.translator.t
            raise UserInputError(
                t(_p(
                    'create_reminder|error:cannot_dm',
                    "I cannot direct message you! Do you have me blocked or direct messages closed?"
                ))
            )

        created_at = created_at or now

        # Passes validation, actually create
        reminder = await self.data.Reminder.create(
            userid=userid,
            remind_at=remind_at,
            content=content,
            message_link=message_link,
            interval=interval,
            created_at=created_at,
        )

        # Schedule from executor
        await self.talk_schedule(reminder.reminderid).send(self.executor_name, wait_for_reply=False)

        # Dispatch reminder update
        await self.dispatch_update_for(userid)

        # Return fresh reminder
        return reminder

    async def parse_time_static(self, timestr, timezone):
        timestr = timestr.strip()
        default = dt.datetime.now(tz=timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        if not timestr:
            return default
        try:
            ts = parse(timestr, fuzzy=True, default=default)
        except ParserError:
            t = self.bot.translator.t
            raise UserInputError(
                t(_p(
                    'parse_timestamp|error:parse',
                    "Could not parse `{given}` as a valid reminder time. "
                    "Try entering the time in the form `HH:MM` or `YYYY-MM-DD HH:MM`."
                )).format(given=timestr)
            )
        return ts

    async def get_reminders_for(self, userid: int):
        """
        Retrieve a list of reminders for the given userid, using the cache.
        """
        reminders = self._user_reminder_cache.get(userid, None)
        if reminders is None:
            reminders = await self.data.Reminder.fetch_where(
                userid=userid
            ).order_by(self.data.Reminder.created_at, ORDER.ASC)
            self._user_reminder_cache[userid] = reminders
        return reminders

    async def dispatch_update_for(self, userid: int):
        """
        Announce that the given user's reminders have changed.

        This triggers update of the cog reminder cache, and a reload of any active reminder list UIs.
        """
        self._user_reminder_cache.pop(userid, None)
        if userid in self._active_reminderlists:
            await self._active_reminderlists[userid].refresh()

    async def reload_reminders(self):
        """
        Refresh reminder data and reminder tasks.
        """
        if not self.executor:
            raise ValueError("Only the executor shard can reload reminders!")
        # Load all reminder tasks
        reminders = await self.data.Reminder.fetch_where(
            self.data.Reminder.remind_at > utc_now(),
            failed=None
        )
        tasks = [(r.reminderid, r.timestamp) for r in reminders]
        self.monitor.set_tasks(*tasks)
        logger.info(
            f"Reloaded ReminderMonitor with {len(tasks)} active reminders."
        )

    async def cancel_reminders(self, *reminderids):
        """
        ShardTalk Route.
        Cancel the given reminderids in the ReminderMonitor.
        """
        if not self.executor:
            raise ValueError("Only the executor shard can cancel scheduled reminders!")
        # If we are the executor shard, we know the monitor is loaded
        # If reminders have not yet been loaded, cancelling is a no-op
        # Since reminder loading is synchronous, we cannot get in a race state with loading
        self.monitor.cancel_tasks(*reminderids)
        logger.debug(
            f"Cancelled reminders: {reminderids}",
        )

    async def schedule_reminders(self, *reminderids):
        """
        ShardTalk Route.
        Schedule the given new reminderids in the ReminderMonitor.
        """
        if not self.executor:
            raise ValueError("Only the executor shard can schedule reminders!")
        # We refetch here to make sure the reminders actually exist
        reminders = await self.data.Reminder.fetch_where(reminderid=reminderids)
        self.monitor.schedule_tasks(*((reminder.reminderid, reminder.timestamp) for reminder in reminders))
        logger.debug(
            f"Scheduled new reminders: {tuple(reminder.reminderid for reminder in reminders)}",
        )

    @log_wrap(action="Send Reminder")
    async def execute_reminder(self, reminderid):
        """
        Send the reminder with the given reminderid.

        This should in general only be executed from the executor shard,
        through a ReminderMonitor instance.
        """
        set_logging_context(context=f"rid: {reminderid}")

        reminder = await self.data.Reminder.fetch(reminderid)
        if reminder is None:
            logger.warning(
                f"Attempted to execute a reminder <rid: {reminderid}> that no longer exists!"
            )
            return

        try:
            # Try and find the user
            userid = reminder.userid
            if not (user := self.bot.get_user(userid)):
                user = await self.bot.fetch_user(userid)

            # Set the locale variables
            locale = await self.bot.get_cog('BabelCog').get_user_locale(userid)
            ctx_locale.set(locale)
            ctx_translator.set(self.bot.translator)

            # Build the embed
            embed = reminder.embed

            # Attempt to send to user
            # TODO: Consider adding a View to this, for cancelling a repeated reminder or showing reminders
            await user.send(embed=embed)

            # Update the data as required
            if reminder.interval:
                now = utc_now()
                # Use original reminder time to calculate repeat, avoiding drift
                next_time = reminder.remind_at + dt.timedelta(seconds=reminder.interval)
                # Skip any expired repeats, to avoid spamming requests after downtime
                # TODO: Is this actually dst safe?
                while next_time.timestamp() <= now.timestamp():
                    next_time = next_time + dt.timedelta(seconds=reminder.interval)
                await reminder.update(remind_at=next_time)
                self.monitor.schedule_task(reminder.reminderid, reminder.timestamp)
                logger.debug(
                    f"Executed reminder <rid: {reminder.reminderid}> and scheduled repeat at {next_time}."
                )
            else:
                await reminder.delete()
                logger.debug(
                    f"Executed reminder <rid: {reminder.reminderid}>."
                )
        except discord.HTTPException as e:
            await reminder.update(failed=True)
            logger.debug(
                f"Reminder <rid: {reminder.reminderid}> could not be sent: {e.text}",
            )
        except Exception:
            await reminder.update(failed=True)
            logger.exception(
                f"Reminder <rid: {reminder.reminderid}> failed for an unknown reason!"
            )
        finally:
            # Dispatch for analytics
            self.bot.dispatch('reminder_sent', reminder)

    @cmds.hybrid_command(
        name=_p('cmd:reminders', "reminders"),
        description=_p(
            'cmd:reminders|desc',
            "View and set your reminders."
        )
    )
    async def cmd_reminders(self, ctx: LionContext):
        """
        Display the reminder widget for this user.
        """
        if not ctx.interaction:
            return

        if ctx.author.id in self._active_reminderlists:
            await self._active_reminderlists[ctx.author.id].quit()
        ui = ReminderList(self.bot, ctx.author)
        try:
            self._active_reminderlists[ctx.author.id] = ui
            await ui.run(ctx.interaction, ephemeral=True)
            await ui.wait()
        finally:
            self._active_reminderlists.pop(ctx.author.id, None)

    @cmds.hybrid_group(
        name=_p('cmd:remindme', "remindme"),
        description=_p('cmd:remindme|desc', "View and set task reminders."),
    )
    async def remindme_group(self, ctx: LionContext):
        # Base command group for scheduling reminders.
        pass

    @remindme_group.command(
        name=_p('cmd:reminders_cancel', "cancel"),
        description=_p(
            'cmd:reminders_cancel|desc',
            "Cancel a single reminder. Use /reminders to clear or cancel multiple reminders."
        )
    )
    @appcmds.rename(
        reminder=_p('cmd:reminders_cancel|param:reminder', 'reminder')
    )
    @appcmds.describe(
        reminder=_p(
            'cmd:reminders_cancel|param:reminder|desc',
            "Start typing, then select a reminder to cancel."
        )
    )
    async def cmd_reminders_cancel(self, ctx: LionContext, reminder: str):
        # No help string
        """
        Cancel a previously scheduled reminder.

        Autocomplete lets the user select their reminder by number or truncated content.
        Need to handle the case where reminderid is that truncated content.
        """
        t = self.bot.translator.t
        reminders = await self.get_reminders_for(ctx.author.id)

        # Guard against no reminders
        if not reminders:
            await ctx.error_reply(
                t(_p(
                    'cmd:reminders_cancel|error:no_reminders',
                    "There are no reminders to cancel!"
                ))
            )
            return

        # Now attempt to parse reminder input
        if reminder.startswith('rid:') and reminder[4:].isdigit():
            # Assume reminderid, probably selected through autocomplete
            rid = int(reminder[4:])
            rem = next((rem for rem in reminders if rem.reminderid == rid), None)
        elif reminder.strip('[] ').isdigit():
            # Assume user reminder index
            # Not strictly threadsafe, but should be okay 90% of the time
            lid = int(reminder)
            rem = next((rem for i, rem in enumerate(reminders, start=1) if i == lid), None)
        else:
            # Assume partial string from a reminder
            partial = reminder
            rem = next((rem for rem in reminders if partial in rem.content), None)

        if rem is None:
            await ctx.error_reply(
                t(_p(
                    'cmd:reminders_cancel|error:no_match',
                    "I am not sure which reminder you want to cancel. "
                    "Please try again, selecting a reminder from the list of choices."
                ))
            )
            return

        # At this point we have a valid reminder to cancel
        await rem.delete()
        await self.talk_cancel(rem.reminderid).send(self.executor_name, wait_for_reply=False)
        await ctx.reply(
            embed=discord.Embed(
                description=t(_p(
                    'cmd:reminders_cancel|embed:success|desc',
                    "Reminder successfully cancelled."
                )),
                colour=discord.Colour.brand_green()
            ),
            ephemeral=True
        )
        await self.dispatch_update_for(ctx.author.id)

    @cmd_reminders_cancel.autocomplete('reminder')
    async def cmd_reminders_cancel_acmpl_reminderid(self, interaction: discord.Interaction, partial: str):
        t = self.bot.translator.t

        reminders = await self.get_reminders_for(interaction.user.id)
        if not reminders:
            # Nothing to cancel case
            name = t(_p(
                'cmd:reminders_cancel|acmpl:reminder|error:no_reminders',
                "There are no reminders to cancel!"
            ))
            value = 'None'
            choices = [
                appcmds.Choice(name=name, value=value)
            ]
        else:
            # Build list of reminder strings
            strings = []
            for pos, reminder in enumerate(reminders, start=1):
                strings.append(
                    (f"[{pos}] {reminder.content}", reminder)
                )
            # Extract matches
            matches = [string for string in strings if partial.lower() in string[0].lower()]

            if matches:
                # Build list of valid choices
                choices = [
                    appcmds.Choice(
                        name=string[0],
                        value=f"rid:{string[1].reminderid}"
                    )
                    for string in matches
                ]
            else:
                choices = [
                    appcmds.Choice(
                        name=t(_p(
                            'cmd:reminders_cancel|acmpl:reminder|error:no_matches',
                            "You do not have any reminders matching \"{partial}\""
                        )).format(partial=partial),
                        value=partial
                    )
                ]
        return choices

    @remindme_group.command(
        name=_p('cmd:remindme_at', "at"),
        description=_p(
            'cmd:remindme_at|desc',
            "Schedule a reminder for a particular time."
        )
    )
    @appcmds.rename(
        time=_p('cmd:remindme_at|param:time', "time"),
        reminder=_p('cmd:remindme_at|param:reminder', "reminder"),
        every=_p('cmd:remindme_at|param:every', "repeat_every"),
    )
    @appcmds.describe(
        time=_p(
            'cmd:remindme_at|param:time|desc',
            "When you want to be reminded. (E.g. `4pm` or `16:00`)."
        ),
        reminder=_p(
            'cmd:remindme_at|param:reminder|desc',
            "What should the reminder be?"
        ),
        every=_p(
            'cmd:remindme_at|param:every|desc',
            "How often to repeat this reminder."
        )
    )
    async def cmd_remindme_at(
        self,
        ctx: LionContext,
        time: appcmds.Range[str, 1, 100],
        reminder: appcmds.Range[str, 1, 2000],
        every: Optional[Transform[int, DurationTransformer(60)]] = None
    ):
        t = self.bot.translator.t

        try:
            timezone = ctx.lmember.timezone
            remind_at = await self.parse_time_static(time, timezone)
            reminder = await self.create_reminder(
                userid=ctx.author.id,
                remind_at=remind_at,
                content=reminder,
                message_link=ctx.message.jump_url,
                interval=every,
            )
            embed = reminder.set_response
        except UserInputError as e:
            embed = discord.Embed(
                title=t(_p(
                    'cmd:remindme_at|error|title',
                    "Could not create reminder!"
                )),
                description=e.msg,
                colour=discord.Colour.brand_red()
            )

        await ctx.reply(
            embed=embed,
            ephemeral=True
        )

    @cmd_remindme_at.autocomplete('time')
    async def cmd_remindme_at_acmpl_time(self, interaction: discord.Interaction, partial: str):
        if interaction.guild:
            lmember = await self.bot.core.lions.fetch_member(interaction.guild.id, interaction.user.id)
            timezone = lmember.timezone
        else:
            luser = await self.bot.core.lions.fetch_user(interaction.user.id)
            timezone = luser.timezone

        t = self.bot.translator.t
        try:
            timestamp = await self.parse_time_static(partial, timezone)
            choice = appcmds.Choice(
                name=timestamp.strftime('%Y-%m-%d %H:%M'),
                value=partial
            )
        except UserInputError:
            choice = appcmds.Choice(
                name=t(_p(
                    'cmd:remindme_at|acmpl:time|error:parse',
                    "Cannot parse \"{partial}\" as a time. Try the format HH:MM or YYYY-MM-DD HH:MM"
                )).format(partial=partial),
                value=partial
            )
        return [choice]

    @remindme_group.command(
        name=_p('cmd:remindme_in', "in"),
        description=_p(
            'cmd:remindme_in|desc',
            "Schedule a reminder for a given amount of time in the future."
        )
    )
    @appcmds.rename(
        time=_p('cmd:remindme_in|param:time', "time"),
        reminder=_p('cmd:remindme_in|param:reminder', "reminder"),
        every=_p('cmd:remindme_in|param:every', "repeat_every"),
    )
    @appcmds.describe(
        time=_p(
            'cmd:remindme_in|param:time|desc',
            "How far into the future to set the reminder (e.g. 1 day 10h 5m)."
        ),
        reminder=_p(
            'cmd:remindme_in|param:reminder|desc',
            "What should the reminder be?"
        ),
        every=_p(
            'cmd:remindme_in|param:every|desc',
            "How often to repeat this reminder. (e.g. 1 day, or 2h)"
        )
    )
    async def cmd_remindme_in(
        self,
        ctx: LionContext,
        time: Transform[int, DurationTransformer(60)],
        reminder: appcmds.Range[str, 1, 2000],
        every: Optional[Transform[int, DurationTransformer(60)]] = None
    ):
        t = self.bot.translator.t

        try:
            remind_at = utc_now() + dt.timedelta(seconds=time)
            reminder = await self.create_reminder(
                userid=ctx.author.id,
                remind_at=remind_at,
                content=reminder,
                message_link=ctx.message.jump_url,
                interval=every,
            )
            embed = reminder.set_response
        except UserInputError as e:
            embed = discord.Embed(
                title=t(_p(
                    'cmd:remindme_in|error|title',
                    "Could not create reminder!"
                )),
                description=e.msg,
                colour=discord.Colour.brand_red()
            )

        await ctx.reply(
            embed=embed,
            ephemeral=True
        )

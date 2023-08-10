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
from discord.ui.select import select, SelectOption
from dateutil.parser import parse, ParserError

from data import RowModel, Registry
from data.queries import ORDER
from data.columns import Integer, String, Timestamp, Bool

from meta import LionBot, LionCog, LionContext
from meta.app import shard_talk, appname_from_shard
from meta.logger import log_wrap, logging_context

from babel import ctx_translator, ctx_locale

from utils.lib import parse_duration, utc_now, strfdur, error_embed
from utils.monitor import TaskMonitor
from utils.transformers import DurationTransformer
from utils.ui import LeoUI, AButton, AsComponents

from . import babel, logger

_, _p, _np = babel._, babel._p, babel._np


class ReminderData(Registry, name='reminders'):
    class Reminder(RowModel):
        """
        Model representing a single reminder.
        Since reminders are likely to change across shards,
        does not use an explicit reference cache.

        Schema
        ------
        CREATE TABLE reminders(
            reminderid SERIAL PRIMARY KEY,
            userid BIGINT NOT NULL REFERENCES user_config(userid) ON DELETE CASCADE,
            remind_at TIMESTAMP NOT NULL,
            content TEXT NOT NULL,
            message_link TEXT,
            interval INTEGER,
            created_at TIMESTAMP DEFAULT (now() at time zone 'utc'),
            title TEXT,
            footer TEXT
        );
        CREATE INDEX reminder_users ON reminders (userid);
        """
        _tablename_ = 'reminders'

        reminderid = Integer(primary=True)

        userid = Integer()  # User which created the reminder
        remind_at = Timestamp()  # Time when the reminder should be executed
        content = String()  # Content the user gave us to remind them
        message_link = String()  # Link to original confirmation message, for context
        interval = Integer()  # Repeat interval, if applicable
        created_at = Timestamp()  # Time when this reminder was originally created
        title = String()  # Title of the final reminder embed, only set in automated reminders
        footer = String()  # Footer of the final reminder embed, only set in automated reminders
        failed = Bool()  # Whether the reminder was already attempted and failed

        @property
        def timestamp(self) -> int:
            """
            Time when this reminder should be executed (next) as an integer timestamp.
            """
            return int(self.remind_at.timestamp())

        @property
        def embed(self) -> discord.Embed:
            t = ctx_translator.get().t

            embed = discord.Embed(
                title=self.title or t(_p('reminder|embed', "You asked me to remind you!")),
                colour=discord.Colour.orange(),
                description=self.content,
                timestamp=self.remind_at
            )

            if self.message_link:
                embed.add_field(
                    name=t(_p('reminder|embed', "Context?")),
                    value="[{click}]({link})".format(
                        click=t(_p('reminder|embed', "Click Here")),
                        link=self.message_link
                    )
                )

            if self.interval:
                embed.add_field(
                    name=t(_p('reminder|embed', "Next reminder")),
                    value=f"<t:{self.timestamp + self.interval}:R>"
                )

            if self.footer:
                embed.set_footer(text=self.footer)

            return embed

        @property
        def formatted(self):
            """
            Single-line string format for the reminder, intended for an embed.
            """
            t = ctx_translator.get().t
            content = self.content
            trunc_content = content[:50] + '...' * (len(content) > 50)

            if interval := self.interval:
                if not interval % (24 * 60 * 60):
                    # Exact day case
                    days = interval // (24 * 60 * 60)
                    repeat = t(_np(
                        'reminder|formatted|interval',
                        "Every day",
                        "Every `{days}` days",
                        days
                    )).format(days=days)
                elif not interval % (60 * 60):
                    # Exact hour case
                    hours = interval // (60 * 60)
                    repeat = t(_np(
                        'reminder|formatted|interval',
                        "Every hour",
                        "Every `{hours}` hours",
                        hours
                    )).format(hours=hours)
                else:
                    # Inexact interval, e.g 10m or 1h 10m.
                    # Use short duration format
                    repeat = t(_p(
                        'reminder|formatted|interval',
                        "Every `{duration}`"
                    )).format(duration=strfdur(interval))

                repeat = f"({repeat})"
            else:
                repeat = ""

            return "<t:{timestamp}:R>, [{content}]({jump_link}) {repeat}".format(
                jump_link=self.message_link,
                content=trunc_content,
                timestamp=self.timestamp,
                repeat=repeat
            )


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
            self.monitor: Optional[ReminderMonitor] = ReminderMonitor(executor=self.execute_reminder)
        else:
            self.monitor = None

        self.talk_reload = shard_talk.register_route('reload_reminders')(self.reload_reminders)
        self.talk_schedule = shard_talk.register_route('schedule_reminders')(self.schedule_reminders)
        self.talk_cancel = shard_talk.register_route('cancel_reminders')(self.cancel_reminders)

        # Short term userid -> list[Reminder] cache, mainly for autocomplete
        self._user_reminder_cache: TTLCache[int, list[ReminderData.Reminder]] = TTLCache(1000, ttl=60)
        self._active_reminderlists: dict[int, ReminderListUI] = {}

    async def cog_load(self):
        await self.data.init()

        if self.executor:
            # Attach and populate the reminder monitor
            self.monitor = ReminderMonitor(executor=self.execute_reminder)
            await self.reload_reminders()

            if self.bot.is_ready:
                self.monitor.start()

    @LionCog.listener()
    async def on_ready(self):
        if self.executor and not self.monitor._monitor_task:
            # Start firing reminders
            self.monitor.start()

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
        reminders = await self.data.Reminder.fetch_where(failed=None)
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

    async def execute_reminder(self, reminderid):
        """
        Send the reminder with the given reminderid.

        This should in general only be executed from the executor shard,
        through a ReminderMonitor instance.
        """
        with logging_context(action='Send Reminder', context=f"rid: {reminderid}"):
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
                        next_time + dt.timedelta(seconds=reminder.interval)
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

    @cmds.hybrid_group(
        name=_p('cmd:reminders', "reminders")
    )
    async def reminders_group(self, ctx: LionContext):
        pass

    @reminders_group.command(
        # No help string
        name=_p('cmd:reminders_show', "show"),
        description=_p(
            'cmd:reminders_show|desc',
            "Display your current reminders."
        )
    )
    async def cmd_reminders_show(self, ctx: LionContext):
        # No help string
        """
        Display the reminder widget for this user.
        """
        t = self.bot.translator.t
        if not ctx.interaction:
            return

        if ctx.author.id in self._active_reminderlists:
            await self._active_reminderlists[ctx.author.id].close(
                msg=t(_p(
                    'cmd:reminders_show|close_elsewhere',
                    "Closing since the list was opened elsewhere."
                ))
            )
        ui = ReminderListUI(self.bot, ctx.author)
        try:
            self._active_reminderlists[ctx.author.id] = ui
            await ui.run(ctx.interaction)
            await ui.wait()
        finally:
            self._active_reminderlists.pop(ctx.author.id, None)

    @reminders_group.command(
        name=_p('cmd:reminders_clear', "clear"),
        description=_p(
            'cmd:reminders_clear|desc',
            "Clear your reminder list."
        )
    )
    async def cmd_reminders_clear(self, ctx: LionContext):
        # No help string
        """
        Confirm and then clear all the reminders for this user.
        """
        if not ctx.interaction:
            return

        t = self.bot.translator.t
        reminders = await self.data.Reminder.fetch_where(userid=ctx.author.id)
        if not reminders:
            await ctx.reply(
                embed=discord.Embed(
                    description=t(_p(
                        'cmd:reminders_clear|error:no_reminders',
                        "You have no reminders to clear!"
                    )),
                    colour=discord.Colour.brand_red()
                ),
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=t(_p('cmd:reminders_clear|confirm|title', "Are You Sure?")),
            description=t(_np(
                'cmd:reminders_clear|confirm|desc',
                "Are you sure you want to delete your `{count}` reminder?",
                "Are you sure you want to clear your `{count}` reminders?",
                len(reminders)
            )).format(count=len(reminders))
        )

        @AButton(label=t(_p('cmd:reminders_clear|confirm|button:yes', "Yes, clear my reminders")))
        async def confirm(interaction, press):
            await interaction.response.defer()
            reminders = await self.data.Reminder.table.delete_where(userid=ctx.author.id)
            await self.talk_cancel(*(r['reminderid'] for r in reminders)).send(self.executor_name, wait_for_reply=False)
            await ctx.interaction.edit_original_response(
                embed=discord.Embed(
                    description=t(_p(
                        'cmd:reminders_clear|success|desc',
                        "Your reminders have been cleared!"
                    )),
                    colour=discord.Colour.brand_green()
                ),
                view=None
            )
            await press.view.close()
            await self.dispatch_update_for(ctx.author.id)

        @AButton(label=t(_p('cmd:reminders_clear|confirm|button:cancel', "Cancel")))
        async def deny(interaction, press):
            await interaction.response.defer()
            await ctx.interaction.delete_original_response()
            await press.view.close()

        components = AsComponents(confirm, deny)
        await ctx.interaction.response.send_message(embed=embed, view=components, ephemeral=True)

    @reminders_group.command(
        name=_p('cmd:reminders_cancel', "cancel"),
        description=_p(
            'cmd:reminders_cancel|desc',
            "Cancel a single reminder. Use the menu in \"reminder show\" to cancel multiple reminders."
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

    @cmds.hybrid_group(
        name=_p('cmd:remindme', "remindme")
    )
    async def remindme_group(self, ctx: LionContext):
        # Base command group for scheduling reminders.
        pass

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
        time=_p('cmd:remindme_at|param:time|desc', "When you want to be reminded. (E.g. `4pm` or `16:00`)."),
        reminder=_p('cmd:remindme_at|param:reminder|desc', "What should the reminder be?"),
        every=_p('cmd:remindme_at|param:every|desc', "How often to repeat this reminder.")
    )
    async def cmd_remindme_at(
        self,
        ctx: LionContext,
        time: str,
        reminder: str,
        every: Optional[Transform[int, DurationTransformer(60)]] = None
    ):
        t = self.bot.translator.t
        reminders = await self.data.Reminder.fetch_where(userid=ctx.author.id)

        # Guard against too many reminders
        if len(reminders) > 25:
            await ctx.error_reply(
                embed=error_embed(
                    t(_p(
                        'cmd_remindme_at|error:too_many|desc',
                        "Sorry, you have reached the maximum of `25` reminders!"
                    )),
                    title=t(_p(
                        'cmd_remindme_at|error:too_many|title',
                        "Could not create reminder!"
                    ))
                ),
                ephemeral=True
            )
            return

        # Guard against too frequent reminders
        if every is not None and every < 600:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd_remindme_at|error:too_fast|desc',
                        "You cannot set a repeating reminder with a period less than 10 minutes."
                    )),
                    title=t(_p(
                        'cmd_remindme_at|error:too_fast|title',
                        "Could not create reminder!"
                    ))
                ),
                ephemeral=True
            )
            return

        # Parse the provided static time
        timezone = ctx.lmember.timezone
        time = time.strip()
        default = dt.datetime.now(tz=timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            ts = parse(time, fuzzy=True, default=default)
        except ParserError:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:remindme_at|error:parse_time|desc',
                        "Could not parse provided time `{given}`. Try entering e.g. `4 pm` or `16:00`."
                    )).format(given=time),
                    title=t(_p(
                        'cmd:remindme_at|error:parse_time|title',
                        "Could not create reminder!"
                    ))
                ),
                ephemeral=True
            )
            return
        if ts < utc_now():
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:remindme_at|error:past_time|desc',
                        "Provided time is in the past!"
                    )),
                    title=t(_p(
                        'cmd:remindme_at|error:past_time|title',
                        "Could not create reminder!"
                    ))
                ),
                ephemeral=True
            )
            return
        # Everything seems to be in order
        # Create the reminder
        now = utc_now()
        rem = await self.data.Reminder.create(
            userid=ctx.author.id,
            remind_at=ts,
            content=reminder,
            message_link=ctx.message.jump_url,
            interval=every,
            created_at=now
        )

        # Reminder created, request scheduling from executor shard
        await self.talk_schedule(rem.reminderid).send(self.executor_name, wait_for_reply=False)

        # TODO Add repeat to description
        embed = discord.Embed(
            title=t(_p(
                'cmd:remindme_in|success|title',
                "Reminder Set at {timestamp}"
            )).format(timestamp=f"<t:{rem.timestamp}>"),
            description=f"> {rem.content}"
        )
        await ctx.reply(
            embed=embed,
            ephemeral=True
        )
        await self.dispatch_update_for(ctx.author.id)

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
        time=_p('cmd:remindme_in|param:time|desc', "How far into the future to set the reminder (e.g. 1 day 10h 5m)."),
        reminder=_p('cmd:remindme_in|param:reminder|desc', "What should the reminder be?"),
        every=_p('cmd:remindme_in|param:every|desc', "How often to repeat this reminder. (e.g. 1 day, or 2h)")
    )
    async def cmd_remindme_in(
        self,
        ctx: LionContext,
        time: Transform[int, DurationTransformer(60)],
        reminder: appcmds.Range[str, 1, 1000],  # TODO: Maximum length 1000?
        every: Optional[Transform[int, DurationTransformer(60)]] = None
    ):
        t = self.bot.translator.t
        reminders = await self.data.Reminder.fetch_where(userid=ctx.author.id)

        # Guard against too many reminders
        if len(reminders) > 25:
            await ctx.error_reply(
                embed=error_embed(
                    t(_p(
                        'cmd_remindme_in|error:too_many|desc',
                        "Sorry, you have reached the maximum of `25` reminders!"
                    )),
                    title=t(_p(
                        'cmd_remindme_in|error:too_many|title',
                        "Could not create reminder!"
                    ))
                ),
                ephemeral=True
            )
            return

        # Guard against too frequent reminders
        if every is not None and every < 600:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd_remindme_in|error:too_fast|desc',
                        "You cannot set a repeating reminder with a period less than 10 minutes."
                    )),
                    title=t(_p(
                        'cmd_remindme_in|error:too_fast|title',
                        "Could not create reminder!"
                    ))
                ),
                ephemeral=True
            )
            return

        # Everything seems to be in order
        # Create the reminder
        now = utc_now()
        rem = await self.data.Reminder.create(
            userid=ctx.author.id,
            remind_at=now + dt.timedelta(seconds=time),
            content=reminder,
            message_link=ctx.message.jump_url,
            interval=every,
            created_at=now
        )

        # Reminder created, request scheduling from executor shard
        await self.talk_schedule(rem.reminderid).send(self.executor_name, wait_for_reply=False)

        # TODO Add repeat to description
        embed = discord.Embed(
            title=t(_p(
                'cmd:remindme_in|success|title',
                "Reminder Set {timestamp}"
            )).format(timestamp=f"<t:{rem.timestamp}:R>"),
            description=f"> {rem.content}"
        )
        await ctx.reply(
            embed=embed,
            ephemeral=True
        )
        await self.dispatch_update_for(ctx.author.id)


class ReminderListUI(LeoUI):
    def __init__(self, bot: LionBot, user: discord.User, **kwargs):
        super().__init__(**kwargs)

        self.bot = bot
        self.user = user

        cog = bot.get_cog('Reminders')
        if cog is None:
            raise ValueError("Cannot create a ReminderUI without the Reminder cog!")
        self.cog: Reminders = cog
        self.userid = user.id

        # Original interaction which sent the UI message
        # Since this is an ephemeral UI, we need this to update and delete
        self._interaction: Optional[discord.Interaction] = None
        self._reminders = []

    async def cleanup(self):
        # Cleanup after an ephemeral UI
        # Just close if possible
        if self._interaction and not self._interaction.is_expired():
            try:
                await self._interaction.delete_original_response()
            except discord.HTTPException:
                pass

    @select()
    async def select_remove(self, interaction: discord.Interaction, selection):
        """
        Select a number of reminders to delete.
        """
        await interaction.response.defer()
        # Hopefully this is a list of reminderids
        values = selection.values
        # Delete from data
        await self.cog.data.Reminder.table.delete_where(reminderid=values)
        # Send cancellation
        await self.cog.talk_cancel(*values).send(self.cog.executor_name, wait_for_reply=False)
        self.cog._user_reminder_cache.pop(self.userid, None)
        await self.refresh()

    async def refresh_select_remove(self):
        """
        Refresh the select remove component from current state.
        """
        t = self.bot.translator.t

        self.select_remove.placeholder = t(_p(
            'ui:reminderlist|select:remove|placeholder',
            "Select to cancel."
        ))
        self.select_remove.options = [
            SelectOption(
                label=f"[{i}] {reminder.content[:50] + '...' * (len(reminder.content) > 50)}",
                value=reminder.reminderid,
                emoji=self.bot.config.emojis.getemoji('clock')
            )
            for i, reminder in enumerate(self._reminders, start=1)
        ]
        self.select_remove.min_values = 1
        self.select_remove.max_values = len(self._reminders)

    async def refresh_reminders(self):
        self._reminders = await self.cog.get_reminders_for(self.userid)

    async def refresh(self):
        """
        Refresh the UI message and components.
        """
        if not self._interaction:
            raise ValueError("Cannot refresh ephemeral UI without an origin interaction!")

        await self.refresh_reminders()
        await self.refresh_select_remove()
        embed = await self.build_embed()

        if self._reminders:
            self.set_layout((self.select_remove,))
        else:
            self.set_layout()

        try:
            if not self._interaction.response.is_done():
                # Fresh message
                await self._interaction.response.send_message(embed=embed, view=self, ephemeral=True)
            else:
                # Update existing message
                await self._interaction.edit_original_response(embed=embed, view=self)
        except discord.HTTPException:
            await self.close()

    async def run(self, interaction: discord.Interaction):
        """
        Run the UI responding to the given interaction.
        """
        self._interaction = interaction
        await self.refresh()

    async def build_embed(self):
        """
        Build the reminder list embed.
        """
        t = self.bot.translator.t
        reminders = self._reminders

        if reminders:
            lines = []
            num_len = len(str(len(reminders)))
            for i, reminder in enumerate(reminders):
                lines.append(
                    "`[{:<{}}]` | {}".format(
                        i+1,
                        num_len,
                        reminder.formatted
                    )
                )
            description = '\n'.join(lines)

            embed = discord.Embed(
                description=description,
                colour=discord.Colour.orange(),
                timestamp=utc_now()
            ).set_author(
                name=t(_p(
                    'ui:reminderlist|embed:list|author',
                    "{name}'s reminders"
                )).format(name=self.user.display_name),
                icon_url=self.user.avatar
            ).set_footer(
                text=t(_p(
                    'ui:reminderlist|embed:list|footer',
                    "Click a reminder twice to jump to the context!"
                ))
            )
        else:
            embed = discord.Embed(
                description=t(_p(
                    'ui:reminderlist|embed:no_reminders|desc',
                    "You have no reminders to display!\n"
                    "Use {remindme} to create a new reminder."
                )).format(
                    remindme=self.bot.core.cmd_name_cache['remindme'].mention,
                )
            )

        return embed

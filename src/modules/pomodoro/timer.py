from typing import Optional, TYPE_CHECKING
import math
from collections import namedtuple
import asyncio
from datetime import timedelta, datetime

import discord

from meta import LionBot
from meta.logger import log_wrap, log_context, set_logging_context
from utils.lib import MessageArgs, utc_now, replace_multiple
from core.lion_guild import LionGuild
from core.data import CoreData
from babel.translator import ctx_locale
from gui.errors import RenderingException

from . import babel, logger
from .data import TimerData
from .ui import TimerStatusUI
from .graphics import get_timer_card
from .lib import TimerRole, channel_name_keys, focus_alert_path, break_alert_path
from .options import TimerConfig, TimerOptions

from babel.settings import LocaleSettings

_p, _np = babel._p, babel._np


Stage = namedtuple('Stage', ['focused', 'start', 'duration', 'end'])


class Timer:
    __slots__ = (
        'bot',
        'data',
        'lguild',
        'config',
        'last_seen',
        'status_view',
        'last_status_message',
        '_hook',
        '_state',
        '_lock',
        '_last_voice_update',
        '_voice_update_task',
        '_voice_update_lock',
        '_run_task',
        '_loop_task',
        'destroyed',
    )

    break_name = _p('timer|stage:break|name', "BREAK")
    focus_name = _p('timer|stage:focus|name', "FOCUS")

    def __init__(self, bot: LionBot, data: TimerData.Timer, lguild: LionGuild):
        self.bot = bot
        self.data = data
        self.lguild = lguild
        self.config = TimerConfig(data.channelid, data)

        log_context.set(f"tid: {self.data.channelid}")

        # State
        self.last_seen: dict[int, datetime] = {}  # memberid -> last seen timestamp
        self.status_view: Optional[TimerStatusUI] = None  # Current TimerStatusUI
        self.last_status_message: Optional[discord.Message] = None  # Last deliever notification message
        self._hook: Optional[CoreData.LionHook] = None  # Cached notification webhook

        self._state: Optional[Stage] = None  # The currently active Stage
        self._lock = asyncio.Lock()  # Stage change and CRUD lock

        # Timestamp of the last voice update, used to compute the next update time
        self._last_voice_update = None
        # Wait task for the current pending channel name update
        self._voice_update_task = None
        # Lock to prevent channel name update race
        self._voice_update_lock = asyncio.Lock()

        # Wait task for the update loop. May be safely cancelled to pause updates.
        self._run_task = None
        # Main loop task. Should not be cancelled.
        self._loop_task = None

        self.destroyed = False

    def __repr__(self):
        # TODO: Add lock status and current state and stage
        return (
            "<Timer "
            f"channelid={self.data.channelid} "
            f"channel='{self.channel}' "
            f"guildid={self.data.guildid} "
            f"guild='{self.guild}' "
            f"members={len(self.members)} "
            f"pattern='{self.data.focus_length}/{self.data.break_length}' "
            f"base_name={self.data.pretty_name!r} "
            f"format_string={self.data.channel_name!r}"
            ">"
        )

    @property
    def locale(self) -> LocaleSettings.GuildLocale:
        return self.lguild.config.get(LocaleSettings.GuildLocale.setting_id)

    @property
    def auto_restart(self) -> bool:
        """
        Whether to automatically restart a stopped timer when a user joins.
        """
        return bool(self.data.auto_restart)

    @property
    def guild(self) -> Optional[discord.Guild]:
        """
        The discord.Guild that this timer belongs to.
        """
        return self.bot.get_guild(self.data.guildid)

    @property
    def channel(self) -> Optional[discord.VoiceChannel]:
        """
        The discord VoiceChannel that this timer lives in.
        """
        return self.bot.get_channel(self.data.channelid)

    @property
    def notification_channel(self) -> Optional[discord.abc.Messageable]:
        """
        The Messageable channel to which to send timer notifications.
        """
        if cid := self.data.notification_channelid:
            channel = self.bot.get_channel(cid)
        else:
            channel = self.lguild.config.get('pomodoro_channel').value
        if channel is None:
            channel = self.channel
        return channel

    @property
    def voice_lock(self):
        return self.lguild.voice_lock

    async def get_notification_webhook(self) -> Optional[discord.Webhook]:
        channel = self.notification_channel
        if channel:
            cid = channel.id
            if self._hook and self._hook.channelid == cid:
                hook = self._hook
            else:
                hook = self._hook = await self.bot.core.data.LionHook.fetch(cid)
                if not hook:
                    # Attempt to create and save webhook
                    # TODO: Localise
                    t = self.bot.translator.t
                    ctx_locale.set(self.locale.value)
                    try:
                        if channel.permissions_for(channel.guild.me).manage_webhooks:
                            avatar = self.bot.user.avatar
                            avatar_data = (await avatar.to_file()).fp.read() if avatar else None
                            webhook = await channel.create_webhook(
                                avatar=avatar_data,
                                name=t(_p(
                                    'timer|webhook|name',
                                    "{bot_name} Pomodoro"
                                )).format(bot_name=self.bot.user.name),
                                reason=t(_p(
                                    'timer|webhook|audit_reason',
                                    "Pomodoro Notifications"
                                ))
                            )
                            hook = await self.bot.core.data.LionHook.create(
                                channelid=channel.id,
                                token=webhook.token,
                                webhookid=webhook.id
                            )
                        elif channel.permissions_for(channel.guild.me).send_messages:
                            await channel.send(t(_p(
                                'timer|webhook|error:insufficient_permissions',
                                "I require the `MANAGE_WEBHOOKS` permission to send pomodoro notifications here!"
                            )))
                    except discord.HTTPException:
                        logger.warning(
                            "Unexpected Exception caught while creating timer notification webhook "
                            f"for timer: {self!r}",
                            exc_info=True
                        )
            if hook:
                return hook.as_webhook(client=self.bot)

    @property
    def members(self) -> list[discord.Member]:
        """
        The list of members of the current timer.

        Uses voice channel member cache as source-of-truth.
        """
        if (chan := self.channel):
            members = [member for member in chan.members if not member.bot]
        else:
            members = []
        return members

    @property
    def owned(self) -> bool:
        """
        Whether this timer is "owned".

        Owned timers have slightly different UI.
        """
        return bool(self.data.ownerid)

    @property
    def running(self) -> bool:
        """
        Whether this timer is currently running.
        """
        return bool(self.data.last_started)

    @property
    def channel_name(self) -> str:
        """
        The configured formatted name of the voice channel.

        Usually does not match the actual voice channel name due to Discord ratelimits.
        """
        channel_name_format = self.data.channel_name or "{name} - {stage}"
        channel_name = replace_multiple(channel_name_format, self.channel_name_map())

        # Truncate to maximum name length
        return channel_name[:100]

    @property
    def base_name(self) -> str:
        if not (name := self.data.pretty_name):
            pattern = f"{int(self.data.focus_length // 60)}/{int(self.data.break_length // 60)}"
            name = self.bot.translator.t(_p(
                'timer|default_base_name',
                "Timer {pattern}"
            ), locale=self.locale.value).format(pattern=pattern)
        return name

    @property
    def pattern(self) -> str:
        data = self.data
        return f"{int(data.focus_length // 60)}/{int(data.break_length // 60)}"

    def channel_name_map(self):
        """
        Compute the replace map used to format the channel name.
        """
        t = self.bot.translator.t
        stage = self.current_stage
        pattern = self.pattern
        name = self.base_name
        if stage is not None:
            remaining = int(math.ceil((stage.end - utc_now()).total_seconds() / 60))
            stagestr = t(self.focus_name if stage.focused else self.break_name, locale=self.locale.value)
        else:
            remaining = self.data.focus_length // 60
            stagestr = t(self.focus_name, locale=self.locale.value)

        mapping = {
            '{remaining}': f"{remaining}m",
            '{stage}': stagestr,
            '{members}': str(len(self.members)),
            '{name}': name,
            '{pattern}': pattern
        }
        return mapping

    @property
    def voice_alerts(self) -> bool:
        """
        Whether voice alerts are enabled for this timer.

        Takes into account the default.
        """
        if (alerts := self.data.voice_alerts) is None:
            alerts = True
        return alerts

    @property
    def current_stage(self) -> Optional[Stage]:
        """
        Calculate the current stage.

        Returns None if the timer is currently stopped.
        """
        if self.running:
            now = utc_now()
            focusl = self.data.focus_length
            breakl = self.data.break_length
            interval = focusl + breakl

            diff = (now - self.data.last_started).total_seconds()
            diff %= interval
            if diff > focusl:
                stage_focus = False
                stage_start = now - timedelta(seconds=(diff - focusl))
                stage_duration = breakl
            else:
                stage_focus = True
                stage_start = now - timedelta(seconds=diff)
                stage_duration = focusl
            stage_end = stage_start + timedelta(seconds=stage_duration)

            stage = Stage(stage_focus, stage_start, stage_duration, stage_end)
        else:
            stage = None
        return stage

    @property
    def inactivity_threshold(self):
        if (threshold := self.data.inactivity_threshold) is None:
            threshold = 3
        return threshold

    def get_member_role(self, member: discord.Member) -> TimerRole:
        """
        Calculate the highest timer permission level of the given member.
        """
        if member.guild_permissions.administrator:
            role = TimerRole.ADMIN
        elif member.id == self.data.ownerid:
            role = TimerRole.OWNER
        elif self.channel and self.channel.permissions_for(member).manage_channels:
            role = TimerRole.MANAGER
        elif (roleid := self.data.manager_roleid) and roleid in (r.id for r in member.roles):
            role = TimerRole.MANAGER
        else:
            role = TimerRole.OTHER
        return role

    @log_wrap(action="Start Timer")
    async def start(self):
        """
        Start a new or stopped timer.

        May also be used to restart the timer.
        """
        try:
            async with self._lock:
                now = utc_now()
                self.last_seen = {
                    member.id: now for member in self.members
                }
                await self.data.update(last_started=now)
                await self.send_status(with_warnings=False)
            self.launch()
        except Exception:
            logger.exception(
                f"Exception occurred while starting timer! Timer {self!r}"
            )
        else:
            logger.info(
                f"Starting timer {self!r}"
            )

    def warning_threshold(self, state: Stage) -> Optional[datetime]:
        """
        Timestamp warning threshold for last_seen, from the given stage.

        Members who have not been since this time are "at risk",
        and will be kicked on the next stage change.
        """
        if self.inactivity_threshold > 0:
            diff = self.inactivity_threshold * (self.data.break_length + self.data.focus_length)
            threshold = utc_now() - timedelta(seconds=diff)
        else:
            threshold = None
        return threshold

    @log_wrap(action='Timer Change Stage')
    async def notify_change_stage(self, from_stage, to_stage, kick=True):
        """
        Notify timer members that the stage has changed.

        This includes deleting the last status message,
        sending a new status message, pinging members, running the voice alert,
        and kicking inactive members if `kick` is True.
        """
        if not self.members:
            t = self.bot.translator.t
            await self.stop(auto_restart=True)
            return

        async with self._lock:
            tasks = []
            after_tasks = []
            # Submit channel name update request
            after_tasks.append(asyncio.create_task(self._update_channel_name(), name='Update-name'))

            if kick and (threshold := self.warning_threshold(from_stage)):
                now = utc_now()
                # Kick people who need kicking
                needs_kick = []
                for member in self.members:
                    last_seen = self.last_seen.get(member.id, None)
                    if last_seen is None:
                        last_seen = self.last_seen[member.id] = now
                    elif last_seen < threshold:
                        needs_kick.append(member)

                t = self.bot.translator.t
                if self.channel and self.channel.permissions_for(self.channel.guild.me).move_members:
                    for member in needs_kick:
                        tasks.append(
                            asyncio.create_task(
                                member.edit(
                                    voice_channel=None,
                                    reason=t(_p(
                                        'timer|disconnect|audit_reason',
                                        "Disconnecting inactive member from timer."
                                    ), locale=self.locale.value)
                                ),
                                name="Disconnect-timer-member"
                            )
                        )

                notify_hook = await self.get_notification_webhook()
                if needs_kick and notify_hook and self.channel:
                    if self.channel.permissions_for(self.channel.guild.me).move_members:
                        kick_message = t(_np(
                            'timer|kicked_message',
                            "{mentions} was removed from {channel} because they were inactive! "
                            "Remember to press {tick} to register your presence every stage.",
                            "{mentions} were removed from {channel} because they were inactive! "
                            "Remember to press {tick} to register your presence every stage.",
                            len(needs_kick)
                        ), locale=self.locale.value).format(
                            channel=f"<#{self.data.channelid}>",
                            mentions=', '.join(member.mention for member in needs_kick),
                            tick=self.bot.config.emojis.tick
                        )
                    else:
                        kick_message = t(_p(
                            'timer|kick_failed',
                            "**Warning!** Timer {channel} is configured to disconnect on inactivity, "
                            "but I lack the 'Move Members' permission to do this!"
                        ), locale=self.locale.value).format(
                            channel=self.channel.mention
                        )
                    tasks.append(asyncio.create_task(notify_hook.send(kick_message), name='kick-message'))

            if self.voice_alerts:
                after_tasks.append(asyncio.create_task(self._voice_alert(to_stage), name='voice-alert'))

            for task in tasks:
                try:
                    await task
                except discord.Forbidden:
                    logger.warning(
                        f"Unexpected forbidden during pre-task {task!r} for change stage in timer {self!r}"
                    )
                except discord.HTTPException:
                    logger.warning(
                        f"Unexpected API error during pre-task {task!r} for change stage in timer {self!r}"
                    )
                except Exception:
                    logger.exception(f"Exception occurred during pre-task {task!r} for change stage in timer {self!r}")

            await self.send_status()

        if after_tasks:
            try:
                await asyncio.gather(*after_tasks)
            except Exception:
                logger.exception(f"Exception occurred during post-tasks for change stage in timer {self!r}")

    @log_wrap(action='Voice Alert')
    async def _voice_alert(self, stage: Stage):
        """
        Join the voice channel, play the associated alert, and leave the channel.
        """
        if not stage:
            return

        if not self.guild or not self.channel or not self.channel.permissions_for(self.guild.me).speak:
            return

        async with self.lguild.voice_lock:
            try:
                if self.guild.voice_client:
                    await self.guild.voice_client.disconnect(force=True)
                alert_file = focus_alert_path if stage.focused else break_alert_path
                try:
                    voice_client = await asyncio.wait_for(
                        self.channel.connect(timeout=30, reconnect=False),
                        timeout=60
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Timed out while connecting to voice channel in timer {self!r}")
                    return

                with open(alert_file, 'rb') as audio_stream:
                    finished = asyncio.Event()
                    loop = asyncio.get_event_loop()

                    def voice_callback(error):
                        if error:
                            try:
                                raise error
                            except Exception:
                                logger.exception(
                                    f"Callback exception occured while playing voice alert for timer {self!r}"
                                )
                        loop.call_soon_threadsafe(finished.set)

                    voice_client.play(discord.PCMAudio(audio_stream), after=voice_callback)

                    # Quit when we finish playing or after 10 seconds, whichever comes first
                    sleep_task = asyncio.create_task(asyncio.sleep(10))
                    wait_task = asyncio.create_task(finished.wait(), name='timer-voice-waiting')
                    _, pending = await asyncio.wait([sleep_task, wait_task], return_when=asyncio.FIRST_COMPLETED)
                    for task in pending:
                        task.cancel()
            except asyncio.TimeoutError:
                logger.warning(
                    f"Timed out while sending voice alert for timer {self!r}",
                    exc_info=True
                )
            except Exception:
                logger.exception(
                    f"Exception occurred while playing voice alert for timer {self!r}"
                )
            finally:
                if self.guild and self.guild.voice_client:
                    await self.guild.voice_client.disconnect(force=True)

    def stageline(self, stage: Stage):
        t = self.bot.translator.t
        ctx_locale.set(self.locale.value)

        if stage.focused:
            lazy_stageline = _p(
                'timer|status|stage:focus|statusline',
                "{channel} is now in **FOCUS**! Good luck, **BREAK** starts {timestamp}"
            )
        else:
            lazy_stageline = _p(
                'timer|status|stage:break|statusline',
                "{channel} is now on **BREAK**! Take a rest, **FOCUS** starts {timestamp}"
            )
        stageline = t(lazy_stageline).format(
            channel=f"<#{self.data.channelid}>",
            timestamp=f"<t:{int(stage.end.timestamp())}:R>"
        )
        return stageline

    async def current_status(self, with_notify=True, with_warnings=True, render=True) -> MessageArgs:
        """
        Message arguments for the current timer status message.
        """
        t = self.bot.translator.t
        now = utc_now()
        ctx_locale.set(self.locale.value)
        stage = self.current_stage

        if self.running and stage is not None:
            stageline = self.stageline(stage)
            warningline = ""
            needs_warning = []
            if with_warnings and self.inactivity_threshold > 0:
                threshold = self.warning_threshold(stage)
                for member in self.members:
                    last_seen = self.last_seen.get(member.id, None)
                    if last_seen is None:
                        last_seen = self.last_seen[member.id] = now
                    elif threshold and last_seen < threshold:
                        needs_warning.append(member)
                if needs_warning:
                    warningline = t(_p(
                        'timer|status|warningline',
                        "**Warning:** {mentions}, please press {tick} to avoid being removed on the next stage."
                    )).format(
                        mentions=' '.join(member.mention for member in needs_warning),
                        tick=self.bot.config.emojis.tick
                    )

            if with_notify and self.members:
                # TODO: Handle case with too many members
                notifyline = ''.join(member.mention for member in self.members if member not in needs_warning)
            else:
                notifyline = ""

            if notifyline:
                notifyline = f"||{notifyline}||"

            content = "\n".join(string for string in (stageline, warningline, notifyline) if string)
        elif self.auto_restart:
            content = t(_p(
                'timer|status|stopped:auto',
                "Timer stopped! Join {channel} to start the timer."
            )).format(channel=f"<#{self.data.channelid}>")
        else:
            content = t(_p(
                'timer|status|stopped:manual',
                "Timer stopped! Press `Start` to restart the timer."
            )).format(channel=f"<#{self.data.channelid}>")

        if (ui := self.status_view) is None:
            ui = self.status_view = TimerStatusUI(self.bot, self, self.channel)

        await ui.refresh()

        rawargs = dict(content=content, view=ui)

        if render:
            try:
                card = await get_timer_card(self.bot, self, stage)
                await card.render()
                rawargs['file'] = card.as_file(f"pomodoro_{self.data.channelid}.png")
            except RenderingException:
                pass
        args = MessageArgs(**rawargs)

        return args

    @log_wrap(action='Send Timer Status')
    async def send_status(self, delete_last=True, **kwargs):
        """
        Send a new status card to the notification channel.
        """
        notify_hook = await self.get_notification_webhook()
        if not notify_hook:
            return

        # Delete last notification message if possible
        last_message_id = self.data.last_messageid
        if delete_last and last_message_id:
            try:
                if self.last_status_message:
                    await self.last_status_message.delete()
                else:
                    await notify_hook.delete_message(last_message_id)
            except discord.HTTPException:
                logger.debug(
                    f"Timer {self!r} failed to delete last status message {last_message_id}"
                )
            last_message_id = None
            self.last_status_message = None

        # Send new notification message

        # Refresh status view
        old_status = self.status_view
        self.status_view = None

        args = await self.current_status(**kwargs)
        logger.debug(
            f"Timer {self!r} is sending a new status: {args.send_args}"
        )
        try:
            message = await notify_hook.send(**args.send_args, wait=True)
            last_message_id = message.id
            self.last_status_message = message
        except discord.NotFound:
            if self._hook is not None:
                await self._hook.delete()
                self._hook = None
                # To avoid killing the client on an infinite loop (which should be impossible)
                await asyncio.sleep(1)
                await self.send_status(delete_last, **kwargs)
        except discord.HTTPException:
            pass

        # Save last message id
        if last_message_id != self.data.last_messageid:
            await self.data.update(last_messageid=last_message_id)

        if old_status is not None:
            old_status.stop()

    @log_wrap(action='Update Timer Status')
    async def update_status_card(self, **kwargs):
        """
        Update the last status card sent.
        """
        async with self._lock:
            args = await self.current_status(**kwargs)
            logger.debug(
                f"Timer {self!r} is updating last status with new status: {args.edit_args}"
            )

            last_message = self.last_status_message
            if last_message is None and self.data.last_messageid is not None:
                # Attempt to retrieve previous message
                notify_hook = await self.get_notification_webhook()
                try:
                    if notify_hook:
                        last_message = await notify_hook.fetch_message(self.data.last_messageid)
                except discord.HTTPException:
                    last_message = None
                    self.last_status_message = None
                except Exception:
                    logger.exception(
                        f"Unhandled exception while updating timer last status for timer {self!r}"
                    )

            repost = last_message is None
            if not repost:
                try:
                    await last_message.edit(**args.edit_args)
                    self.last_status_message = last_message
                except discord.NotFound:
                    repost = True
                except discord.HTTPException:
                    # Unexpected issue with sending the status message
                    logger.exception(
                        f"Exception occurred updating status for Timer {self!r}"
                    )

            if repost:
                await self.send_status(delete_last=False, with_notify=False)

    @log_wrap(action='Update Channel Name')
    async def _update_channel_name(self):
        """
        Submit a task to update the voice channel name.

        Attempts to ensure that only one task is running at a time.
        Attempts to wait until the next viable channel update slot (via ratelimit).
        """
        if self._voice_update_lock.locked():
            # Voice update is already running
            # Note that if channel editing takes a long time,
            # and the lock is waiting on that,
            # we may actually miss a channel update in this period.
            # Erring on the side of less ratelimits.
            return

        async with self._voice_update_lock:
            if self._last_voice_update:
                to_wait = ((self._last_voice_update + timedelta(minutes=5)) - utc_now()).total_seconds()
                if to_wait > 0:
                    self._voice_update_task = asyncio.create_task(asyncio.sleep(to_wait), name='timer-voice-wait')
                    try:
                        await self._voice_update_task
                    except asyncio.CancelledError:
                        return

            if not self.channel:
                return
            if not self.channel.permissions_for(self.guild.me).manage_channels:
                return

            new_name = self.channel_name
            if new_name == self.channel.name:
                return

            try:
                logger.debug(f"Requesting channel name update for timer {self}")
                await self.channel.edit(name=new_name)
            except discord.HTTPException:
                logger.warning(
                    f"Voice channel name update failed for timer {self}",
                    exc_info=True
                )
            finally:
                # Whether we fail or not, update ratelimit marker
                # (Repeatedly sending failing requests is even worse than normal ratelimits.)
                self._last_voice_update = utc_now()

    @log_wrap(action="Stop Timer")
    async def stop(self, auto_restart=False):
        """
        Stop the timer.

        Stops the run loop, and updates the last status message to a stopped message.
        """
        try:
            async with self._lock:
                if self._run_task and not self._run_task.done():
                    self._run_task.cancel()
                await self.data.update(last_started=None, auto_restart=auto_restart)
            await self.update_status_card()
        except Exception:
            logger.exception(f"Exception while stopping Timer {self!r}!")
        else:
            logger.info(f"Timer {self!r} has stopped. Auto restart is {'on' if auto_restart else 'off'}")

    @log_wrap(action="Destroy Timer")
    async def destroy(self, reason: Optional[str] = None):
        """
        Deconstructs the timer, stopping all tasks.
        """
        async with self._lock:
            if self._run_task and not self._run_task.done():
                self._run_task.cancel()
            channelid = self.data.channelid
            if self.channel:
                task = asyncio.create_task(
                    self.channel.edit(name=self.data.pretty_name, reason="Reverting timer channel name")
                )
            await self.data.delete()
            self.destroyed = True
            if self.last_status_message:
                try:
                    await self.last_status_message.delete()
                except discord.HTTPException:
                    pass
            logger.info(
                f"Timer <tid: {channelid}> deleted. Reason given: {reason!r}"
            )

    @log_wrap(isolate=True, stack=())
    async def _runloop(self):
        """
        Main loop which controls the
        regular stage changes and status updates.
        """
        set_logging_context(
            action=f"TimerLoop {self.data.channelid}",
            context=f"tid: {self.data.channelid}",
        )
        # Allow updating with 10 seconds of drift to the next stage change
        drift = 10

        if not self.running:
            # Nothing to do
            return
        if not self.channel:
            # Underlying Discord objects do not exist, destroy the timer.
            await self.destroy(reason="Underlying channel no longer exists.")
            return

        background_tasks = set()

        self._state = current = self.current_stage
        while True:
            if current is None:
                logger.exception(
                    f"Closing timer loop because current state is None. Timer {self!r}"
                )
                break
            to_next_stage = (current.end - utc_now()).total_seconds()

            # TODO: Consider request rate and load
            if to_next_stage > 5 * 60 - drift:
                time_to_sleep = 5 * 60
            else:
                time_to_sleep = to_next_stage

            self._run_task = asyncio.create_task(asyncio.sleep(time_to_sleep))
            try:
                await self._run_task
            except asyncio.CancelledError:
                break

            if not self.running:
                # We somehow stopped without cancelling the run task?
                logger.warning(
                    f"Closing timer loop because we are no longer running. This should not happen! Timer {self!r}"
                )
                break
            if not self.channel:
                # Probably left the guild or the channel was deleted
                await self.destroy(reason="Underlying channel no longer exists")
                break

            if current.end < utc_now():
                self._state = self.current_stage
                task = asyncio.create_task(
                    self.notify_change_stage(current, self._state),
                    name='notify-change-stage'
                )
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)
                current = self._state
            elif self.members:
                task = asyncio.create_task(
                    self._update_channel_name(),
                    name='regular-channel-update'
                )
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)
                task = asyncio.create_task(self.update_status_card())
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)

        if background_tasks:
            try:
                await asyncio.gather(*background_tasks)
            except Exception:
                logger.warning(
                    f"Unexpected error while finishing background tasks for timer {self!r}",
                    exc_info=True
                )

    def launch(self):
        """
        Launch the update loop, if the timer is running, otherwise do nothing.
        """
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()

        if self.running:
            self._loop_task = asyncio.create_task(self._runloop())

    async def unload(self):
        """
        Unload the timer without changing stored state.

        Waits for all background tasks to complete.
        """
        async with self._lock:
            if self._loop_task and not self._loop_task.done():
                if self._run_task and not self._run_task.done():
                    self._run_task.cancel()
                await self._loop_task

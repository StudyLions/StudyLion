from typing import Optional
from collections import defaultdict
from weakref import WeakValueDictionary
import datetime as dt
import asyncio

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.app_commands import Range

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.sharding import THIS_SHARD
from core.data import CoreData
from utils.lib import utc_now
from wards import high_management_ward, low_management_ward, equippable_role
from modules.moderation.cog import ModerationCog


from . import babel, logger
from .data import VideoData
from .settings import VideoSettings
from .settingui import VideoSettingUI
from .ticket import VideoTicket

_p = babel._p


class VideoCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(VideoData())
        self.settings = VideoSettings()

        self.ready = asyncio.Event()
        self._video_tasks: dict[tuple[int, int], asyncio.Task] = {}
        self._event_locks: dict[tuple[int, int], asyncio.Lock] = WeakValueDictionary()

    async def cog_load(self):
        await self.data.init()
        # TODO: Register Video Ticket type here

        modcog = self.bot.get_cog('ModerationCog')
        if modcog is None:
            raise ValueError("Cannot load VideoCog before ModerationCog!")

        self.bot.core.guild_config.register_model_setting(self.settings.VideoBlacklist)
        self.bot.core.guild_config.register_model_setting(self.settings.VideoGracePeriod)

        await self.settings.VideoChannels.setup(self.bot)
        await self.settings.VideoExempt.setup(self.bot)

        configcog = self.bot.get_cog('ConfigCog')
        if configcog is None:
            logger.warning(
                "Could not load ConfigCog. VideoCog configuration will not crossload."
            )
        else:
            self.crossload_group(self.configure_group, configcog.configure_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        ...

    @LionCog.listener('on_ready')
    async def initialise(self):
        """
        Read all current voice channel members.

        Ensure that all video channel members have tasks running or are valid.
        Note that we do start handling events before the bot cache is ready.
        This is because the event data carries all required member data with it.
        However, members who were already present and didn't fire an event
        may still need to be handled.
        """
        # Re-cache, now using the actual client guilds
        await self.settings.VideoChannels.setup(self.bot)
        await self.settings.VideoExempt.setup(self.bot)

        # Collect members that need handling
        active = [channel for guild in self.bot.guilds for channel in guild.voice_channels if channel.members]
        tasks = []
        for channel in active:
            if await self.check_video_channel(channel):
                for member in list(channel.members):
                    key = (channel.guild.id, member.id)
                    async with self.event_lock(key):
                        if key in self._video_tasks:
                            pass
                        elif await self.check_member_exempt(member):
                            pass
                        elif await self.check_member_blacklist(member):
                            task = asyncio.create_task(
                                    self._remove_blacklisted(member, channel)
                            )
                            tasks.append(task)
                        else:
                            task = asyncio.create_task(
                                    self._joined_video_channel(member, channel)
                            )
                            tasks.append(task)
                            self._video_tasks[key] = task
        if tasks:
            await asyncio.gather(*tasks)

    # ----- Event Handlers -----
    def event_lock(self, key) -> asyncio.Lock:
        """
        Get an asyncio.Lock for the given key.

        Guarantees sequential event handling.
        """
        lock = self._event_locks.get(key, None)
        if lock is None:
            lock = self._event_locks[key] = asyncio.Lock()
        logger.debug(f"Getting video event lock {key} (locked: {lock.locked()})")
        return lock

    @LionCog.listener('on_voice_state_update')
    @log_wrap(action='Video Watchdog')
    async def video_watchdog(self, member: discord.Member,
                             before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        task_key = (member.guild.id, member.id)
        # Freeze the state so it doesn't get updated by other events
        after_channel = after.channel
        before_channel = before.channel
        after_video = after.self_video

        async with self.event_lock(task_key):
            if after_channel != before_channel:
                # Channel changed, cancel any running tasks
                task = self._video_tasks.pop(task_key, None)
                if task and not task.done() and not task.cancelled():
                    task.cancel()

                # If they are joining a video channel, run join logic
                run_join = (
                    after_channel and not after_video
                    and await self.check_video_channel(after_channel)
                    and not await self.check_member_exempt(member)
                )
                if run_join:
                    # Check if the member is blacklisted
                    if await self.check_member_blacklist(member):
                        # Kick them from the channel
                        await self._remove_blacklisted(member, after_channel)
                    join_task = asyncio.create_task(
                        self._joined_video_channel(member, after_channel)
                    )
                    self._video_tasks[task_key] = join_task
                    logger.debug(
                        f"Launching video channel join task for <uid:{member.id}> "
                        f"in <cid:{after_channel.id}> of guild <gid:{member.guild.id}>."
                    )
            elif after_channel and (before.self_video != after_video):
                # Video state changed
                channel = after_channel
                if (await self.check_video_channel(channel) and not await self.check_member_exempt(member)):
                    # Relevant video event
                    if after_video:
                        # They turned their video on!
                        # Cancel any running tasks
                        task = self._video_tasks.pop(task_key, None)
                        if task and not task.done() and not task.cancelled():
                            task.cancel()
                    elif (task := self._video_tasks.get(task_key, None)) is None or task.done():
                        # They turned their video off, and there are no tasks handling the member
                        # Give them a brief grace period and then kick them
                        kick_task = asyncio.create_task(
                            self._disabled_video_kick(member, channel)
                        )
                        self._video_tasks[task_key] = kick_task
                        logger.debug(
                            f"Launching video channel kick task for <uid:{member.id}> "
                            f"in <cid:{channel.id}> of guild <gid:{member.guild.id}>"
                        )

    async def check_member_exempt(self, member: discord.Member) -> bool:
        """
        Check whether a member is video-exempt.

        Should almost always hit cache.
        """
        exempt_setting = await self.settings.VideoExempt.get(member.guild.id)
        exempt_ids = set(exempt_setting.data)
        return any(role.id in exempt_ids for role in member.roles)

    async def check_member_blacklist(self, member: discord.Member) -> bool:
        """
        Check whether a member is video blacklisted.

        (i.e. check whether they have the blacklist role)
        """
        blacklistid = (await self.settings.VideoBlacklist.get(member.guild.id)).data
        return (blacklistid and any(role.id == blacklistid for role in member.roles))

    async def check_video_channel(self, channel: discord.VoiceChannel) -> bool:
        """
        Check whether a given channel is a video only channel.

        Should almost always hit cache.
        """
        channel_setting = await self.settings.VideoChannels.get(channel.guild.id)
        channelids = set(channel_setting.data)
        return (channel.id in channelids) or (channel.category_id and channel.category_id in channelids)

    async def _remove_blacklisted(self, member: discord.Member, channel: discord.VoiceChannel):
        """
        Remove a video blacklisted member from the channel.
        """
        logger.info(
            f"Removing video blacklisted member <uid:{member.id}> from <cid:{channel.id}> in "
            f"<gid:{member.guild.id}>"
        )
        t = self.bot.translator.t
        try:
            # Kick the member from the channel
            await asyncio.shield(
                member.edit(
                    voice_channel=None,
                    reason=t(_p(
                        'video_watchdog|kick_blacklisted_member|audit_reason',
                        "Removing video blacklisted member from a video channel."
                    ))
                )
            )
        except discord.HTTPException:
            # TODO: Event log
            ...
        except asyncio.CancelledError:
            # This shouldn't happen because we don't wait for this task the same way
            # And the event lock should wait for this to be complete anyway
            pass

        # TODO: Notify through the moderation alert API
        embed = discord.Embed(
            colour=discord.Colour.brand_red(),
            title=t(_p(
                'video_watchdog|kick_blacklisted_member|notification|title',
                "You have been disconnected."
            )),
            description=t(_p(
                'video_watchdog|kick_blacklisted_member|notification|desc',
                "You were disconnected from the video channel {channel} because you are "
                "blacklisted from video channels in **{server}**."
            )).format(channel=channel.mention, server=channel.guild.name),
        )
        modcog: ModerationCog = self.bot.get_cog('ModerationCog')
        await modcog.send_alert(
            member,
            embed=embed
        )

    async def _joined_video_channel(self, member: discord.Member, channel: discord.VoiceChannel):
        """
        Handle a (non-exempt, non-blacklisted) member joining a video channel.
        """
        if not member.voice or not member.voice.channel:
            # In case the member already left
            return
        if member.voice.self_video:
            # In case they already turned video on
            return

        try:
            # First wait for 15 seconds for them to turn their video on (without prompting)
            await asyncio.sleep(15)

            # Fetch the required setting data (allow cancellation while we fetch or create)
            lion = await self.bot.core.lions.fetch_member(member.guild.id, member.id)
        except asyncio.CancelledError:
            # They left the video channel or turned their video on
            return

        t = self.bot.translator.t
        modcog: ModerationCog = self.bot.get_cog('ModerationCog')
        now = utc_now()
        # Important that we use a sync request here
        grace = lion.lguild.config.get(self.settings.VideoGracePeriod.setting_id).value
        disconnect_at = now + dt.timedelta(seconds=grace)

        jump_field = t(_p(
            'video_watchdog|join_task|jump_field',
            "[Click to jump back]({link})"
        )).format(link=channel.jump_url)

        request = discord.Embed(
            colour=discord.Colour.orange(),
            title=t(_p(
                'video_watchdog|join_task|initial_request:title',
                "Please enable your video!"
            )),
            description=t(_p(
                'video_watchdog|join_task|initial_request:description',
                "**You have joined the video channel {channel}!**\n"
                "Please **enable your video** or **leave the channel** "
                "or you will be disconnected {timestamp} and "
                "potentially **blacklisted**."
            )).format(
                channel=channel.mention,
                timestamp=discord.utils.format_dt(disconnect_at, 'R'),
            ),
            timestamp=now
        ).add_field(name='', value=jump_field)

        thanks = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'video_watchdog|join_task|thanks:title',
                "Thanks for enabling your video!"
            )),
        ).add_field(name='', value=jump_field)
        bye = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'video_watchdog|join_task|bye:title',
                "Thanks for leaving the channel promptly!"
            ))
        )
        alert_task = asyncio.create_task(
            modcog.send_alert(
                member,
                embed=request
            )
        )
        try:
            message = await asyncio.shield(alert_task)
            await discord.utils.sleep_until(disconnect_at)
        except asyncio.CancelledError:
            # Member enabled video or moved to another channel or left the server

            # Wait for the message to finish sending if we need to
            message = await alert_task

            # Fetch a new member to check voice state
            member = member.guild.get_member(member.id)
            if member and message:
                if member.voice and (member.voice.channel == channel) and member.voice.self_video:
                    # Assume member enabled video
                    embed = thanks
                else:
                    # Assume member left channel
                    embed = bye
                embed.timestamp = utc_now()
                try:
                    await message.edit(embed=embed)
                except discord.HTTPException:
                    pass
        else:
            # Member never enabled video in the grace period.
            
            # No longer accept cancellation
            self._video_tasks.pop((member.guild.id, member.id), None)

            # Disconnect user
            try:
                await member.edit(
                    voice_channel=None,
                    reason=t(_p(
                        'video_watchdog|join_task|kick_after_grace|audit_reason',
                        "Member never enabled their video in video channel."
                    ))
                )
            except discord.HTTPException:
                # TODO: Event log
                ...

            # Assign warn/blacklist ticket as needed
            blacklist = lion.lguild.config.get(self.settings.VideoBlacklist.setting_id)
            only_warn = (not lion.data.video_warned) and blacklist
            ticket = None
            if not only_warn:
                # Try to apply blacklist
                try:
                    ticket = await self.blacklist_member(
                        member,
                        reason=t(_p(
                            'video_watchdog|join_task|kick_after_grace|ticket_reason',
                            "Failed to enable their video in time in the video channel {channel}"
                        )).format(channel=channel.mention)
                    )
                except discord.HTTPException as e:
                    logger.debug(
                        f"Could not create blacklist ticket on member <uid:{member.id}> "
                        f"in <gid:{member.guild.id}>: {e.text}"
                    )
                    only_warn = True

            # Ack based on ticket created
            alert_ref = message.to_reference(fail_if_not_exists=False)
            if only_warn:
                # TODO: Warn ticket
                warning = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'video_watchdog|join_task|kick_after_grace|warning|title',
                        "You have received a warning!"
                    )),
                    description=t(_p(
                        'video_watchdog|join_task|kick_after_grace|warning|desc',
                        "**You must enable your camera in camera-only rooms.**\n"
                        "You have been disconnected from the video {channel} for not "
                        "enabling your camera."
                    )).format(channel=channel.mention),
                    timestamp=utc_now()
                ).add_field(name='', value=jump_field)
                
                await modcog.send_alert(member, embed=warning, reference=alert_ref)
                if not lion.data.video_warned:
                    await lion.data.update(video_warned=True)
            else:
                alert = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'video_watchdog|join_task|kick_after_grace|blacklist|title',
                        "You have been blacklisted!"
                    )),
                    description=t(_p(
                        'video_watchdog|join_task|kick_after_grace|blacklist|desc',
                        "You have been blacklisted from the video channels in this server."
                    )),
                    timestamp=utc_now()
                ).add_field(name='', value=jump_field)
                # TODO: Add duration
                await modcog.send_alert(member, embed=alert, reference=alert_ref)
            
    async def _disabled_video_kick(self, member: discord.Member, channel: discord.VoiceChannel):
        """
        Kick a video channel member who has disabled their video.
        """
        # Give them 15 seconds to re-enable
        try:
            await asyncio.sleep(15)
        except asyncio.CancelledError:
            # Member left the channel or turned on their video
            return

        # Member did not turn on their video, actually kick and notify
        t = self.bot.translator.t
        logger.info(
            f"Removing member <uid:{member.id}> from video channel <cid:{channel.id}> in "
            f"<gid:{member.guild.id}> because they disabled their video."
        )
        # Disconnection is now inevitable
        # We also don't want our own disconnection to cancel the task
        self._video_tasks.pop((member.guild.id, member.id), None)
        try:
            await asyncio.shield(
                member.edit(
                    voice_channel=None,
                    reason=t(_p(
                        'video_watchdog|disabled_video_kick|audit_reason',
                        "Disconnected for disabling video for more than {number} seconds in video channel."
                    )).format(number=15)
                )
            )
        except asyncio.CancelledError:
            # Ignore cancelled error at this point
            pass
        except discord.HTTPException:
            # TODO: Event logging
            pass

        embed = discord.Embed(
            colour=discord.Colour.brand_red(),
            title=t(_p(
                'video_watchdog|disabled_video_kick|notification|title',
                "You have been disconnected."
            )),
            description=t(_p(
                'video_watchdog|disabled_video_kick|notification|desc',
                "You were disconnected from the video channel {channel} because "
                "you disabled your video.\n"
                "Please keep your video on at all times, and leave the channel if you need "
                "to disable it!"
            ))
        )
        modcog: ModerationCog = self.bot.get_cog('ModerationCog')
        await modcog.send_alert(
            member,
            embed=embed
        )

    async def blacklist_member(self, member: discord.Member, reason: str):
        """
        Create a VideoBlacklist ticket with the appropriate duration,
        and apply the video blacklist role.

        Propagates any exceptions that may arise.
        """
        return await VideoTicket.autocreate(
            self.bot, member, reason
        )

    # ----- Commands -----

    # ------ Configuration -----
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        ...

    @configure_group.command(
        name=_p('cmd:configure_video', "video_channels"),
        description=_p(
            'cmd:configure_video|desc', "Configure video-only channels and blacklisting."
        )
    )
    @appcmds.rename(
        video_blacklist=VideoSettings.VideoBlacklist._display_name,
        video_blacklist_durations=VideoSettings.VideoBlacklistDurations._display_name,
        video_grace_period=VideoSettings.VideoGracePeriod._display_name,
    )
    @appcmds.describe(
        video_blacklist=VideoSettings.VideoBlacklist._desc,
        video_blacklist_durations=VideoSettings.VideoBlacklistDurations._desc,
        video_grace_period=VideoSettings.VideoGracePeriod._desc,
    )
    @low_management_ward
    async def configure_video(self, ctx: LionContext,
                              video_blacklist: Optional[discord.Role] = None,
                              video_blacklist_durations: Optional[str] = None,
                              video_grace_period: Optional[str] = None,
                              ):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True)

        modified = []

        if video_blacklist is not None:
            await equippable_role(self.bot, video_blacklist, ctx.author)
            setting = self.settings.VideoBlacklist
            await setting._check_value(ctx.guild.id, video_blacklist)
            instance = setting(ctx.guild.id, video_blacklist.id)
            modified.append(instance)

        if video_blacklist_durations is not None:
            setting = self.settings.VideoBlacklistDurations
            instance = await setting.from_string(ctx.guild.id, video_blacklist_durations)
            modified.append(instance)

        if video_grace_period is not None:
            setting = self.settings.VideoGracePeriod
            instance = await setting.from_string(ctx.guild.id, video_grace_period)
            modified.append(instance)

        if modified:
            ack_lines = []
            for instance in modified:
                await instance.write()
                ack_lines.append(instance.update_message)

            # Ack modified
            tick = self.bot.config.emojis.tick
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description='\n'.join(f"{tick} {line}" for line in ack_lines),
            )
            await ctx.reply(embed=embed)

        if ctx.channel.id not in VideoSettingUI._listening or not modified:
            ui = VideoSettingUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()


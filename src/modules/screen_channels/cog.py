# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Screen share enforcement cog - watches voice state
#          updates and enforces screen sharing in designated
#          channels (mirrors video_channels/cog.py)
# ============================================================
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
from utils.lib import utc_now, strfdelta
from wards import high_management_ward, low_management_ward, equippable_role
from modules.moderation.cog import ModerationCog
from modules.moderation.data import TicketType, TicketState


from . import babel, logger
from .data import ScreenData
from .settings import ScreenSettings
from .settingui import ScreenSettingUI
from .ticket import ScreenTicket

_p = babel._p


class ScreenCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(ScreenData())
        self.settings = ScreenSettings()

        self.ready = asyncio.Event()
        self._screen_tasks: dict[tuple[int, int], asyncio.Task] = {}
        self._event_locks: dict[tuple[int, int], asyncio.Lock] = WeakValueDictionary()

    async def cog_load(self):
        await self.data.init()

        modcog = self.bot.get_cog('ModerationCog')
        if modcog is None:
            raise ValueError("Cannot load ScreenCog before ModerationCog!")

        self.bot.core.guild_config.register_model_setting(self.settings.ScreenBlacklist)
        self.bot.core.guild_config.register_model_setting(self.settings.ScreenGracePeriod)

        await self.settings.ScreenChannels.setup(self.bot)
        await self.settings.ScreenExempt.setup(self.bot)

        configcog = self.bot.get_cog('ConfigCog')
        if configcog is None:
            logger.warning(
                "Could not load ConfigCog. ScreenCog configuration will not crossload."
            )
        else:
            self.crossload_group(self.configure_group, configcog.admin_config_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        ...

    @LionCog.listener('on_ready')
    async def initialise(self):
        """
        Read all current voice channel members.

        Ensure that all screen share channel members have tasks running or are valid.
        """
        await self.settings.ScreenChannels.setup(self.bot)
        await self.settings.ScreenExempt.setup(self.bot)

        active = [channel for guild in self.bot.guilds for channel in guild.voice_channels if channel.members]
        tasks = []
        for channel in active:
            if await self.check_screen_channel(channel):
                for member in list(channel.members):
                    key = (channel.guild.id, member.id)
                    async with self.event_lock(key):
                        if key in self._screen_tasks:
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
                                    self._joined_screen_channel(member, channel)
                            )
                            tasks.append(task)
                            self._screen_tasks[key] = task
        if tasks:
            await asyncio.gather(*tasks)

    # ----- Event Handlers -----
    def event_lock(self, key) -> asyncio.Lock:
        lock = self._event_locks.get(key, None)
        if lock is None:
            lock = self._event_locks[key] = asyncio.Lock()
        logger.debug(f"Getting screen event lock {key} (locked: {lock.locked()})")
        return lock

    @LionCog.listener('on_voice_state_update')
    @log_wrap(action='Screen Watchdog')
    async def screen_watchdog(self, member: discord.Member,
                              before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        task_key = (member.guild.id, member.id)
        after_channel = after.channel
        before_channel = before.channel
        after_stream = after.self_stream

        async with self.event_lock(task_key):
            if after_channel != before_channel:
                task = self._screen_tasks.pop(task_key, None)
                if task and not task.done() and not task.cancelled():
                    task.cancel()

                run_join = (
                    after_channel and not after_stream
                    and await self.check_screen_channel(after_channel)
                    and not await self.check_member_exempt(member)
                )
                if run_join:
                    if await self.check_member_blacklist(member):
                        await self._remove_blacklisted(member, after_channel)
                    join_task = asyncio.create_task(
                        self._joined_screen_channel(member, after_channel)
                    )
                    self._screen_tasks[task_key] = join_task
                    logger.debug(
                        f"Launching screen channel join task for <uid:{member.id}> "
                        f"in <cid:{after_channel.id}> of guild <gid:{member.guild.id}>."
                    )
            elif after_channel and (before.self_stream != after_stream):
                channel = after_channel
                if (await self.check_screen_channel(channel) and not await self.check_member_exempt(member)):
                    if after_stream:
                        task = self._screen_tasks.pop(task_key, None)
                        if task and not task.done() and not task.cancelled():
                            task.cancel()
                    elif (task := self._screen_tasks.get(task_key, None)) is None or task.done():
                        kick_task = asyncio.create_task(
                            self._disabled_screen_kick(member, channel)
                        )
                        self._screen_tasks[task_key] = kick_task
                        logger.debug(
                            f"Launching screen channel kick task for <uid:{member.id}> "
                            f"in <cid:{channel.id}> of guild <gid:{member.guild.id}>"
                        )

    async def check_member_exempt(self, member: discord.Member) -> bool:
        exempt_setting = await self.settings.ScreenExempt.get(member.guild.id)
        exempt_ids = set(exempt_setting.data)
        return any(role.id in exempt_ids for role in member.roles)

    async def check_member_blacklist(self, member: discord.Member) -> bool:
        blacklistid = (await self.settings.ScreenBlacklist.get(member.guild.id)).data
        return (blacklistid and any(role.id == blacklistid for role in member.roles))

    async def check_screen_channel(self, channel: discord.VoiceChannel) -> bool:
        channel_setting = await self.settings.ScreenChannels.get(channel.guild.id)
        channelids = set(channel_setting.data)
        return (channel.id in channelids) or (channel.category_id and channel.category_id in channelids)

    async def _remove_blacklisted(self, member: discord.Member, channel: discord.VoiceChannel):
        logger.info(
            f"Removing screen blacklisted member <uid:{member.id}> from <cid:{channel.id}> in "
            f"<gid:{member.guild.id}>"
        )
        t = self.bot.translator.t
        try:
            await asyncio.shield(
                member.edit(
                    voice_channel=None,
                    reason=t(_p(
                        'screen_watchdog|kick_blacklisted_member|audit_reason',
                        "Removing screen blacklisted member from a screen share channel."
                    ))
                )
            )
        except discord.HTTPException:
            ...
        except asyncio.CancelledError:
            pass

        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Add blacklist expiry info to the disconnection notification
        modcog: ModerationCog = self.bot.get_cog('ModerationCog')
        expiry_str = t(_p(
            'screen_watchdog|blacklist|expiry:permanent',
            "Permanent"
        ))
        try:
            active_tickets = await ScreenTicket.fetch_tickets(
                self.bot,
                guildid=member.guild.id,
                targetid=member.id,
                ticket_type=TicketType.SCREEN_BAN,
                ticket_state=TicketState.EXPIRING,
            )
            if active_tickets and active_tickets[0].data.expiry:
                expiry_str = discord.utils.format_dt(active_tickets[0].data.expiry, 'R')
        except Exception:
            pass

        embed = discord.Embed(
            colour=discord.Colour.brand_red(),
            title=t(_p(
                'screen_watchdog|kick_blacklisted_member|notification|title',
                "You have been disconnected."
            )),
            description=t(_p(
                'screen_watchdog|kick_blacklisted_member|notification|desc',
                "You were disconnected from the screen share channel {channel} because you are "
                "blacklisted from screen share channels in **{server}**.\n"
                "**Your blacklist expires:** {expiry}"
            )).format(channel=channel.mention, server=channel.guild.name, expiry=expiry_str),
        )
        await modcog.send_alert(
            member,
            embed=embed
        )
        # --- END AI-MODIFIED ---

    async def _joined_screen_channel(self, member: discord.Member, channel: discord.VoiceChannel):
        if not member.voice or not member.voice.channel:
            return
        if member.voice.self_stream:
            return

        try:
            await asyncio.sleep(15)
            lion = await self.bot.core.lions.fetch_member(member.guild.id, member.id)
        except asyncio.CancelledError:
            return

        t = self.bot.translator.t
        modcog: ModerationCog = self.bot.get_cog('ModerationCog')
        now = utc_now()
        grace = lion.lguild.config.get(self.settings.ScreenGracePeriod.setting_id).value
        disconnect_at = now + dt.timedelta(seconds=grace)

        jump_field = t(_p(
            'screen_watchdog|join_task|jump_field',
            "[Click to jump back]({link})"
        )).format(link=channel.jump_url)

        request = discord.Embed(
            colour=discord.Colour.orange(),
            title=t(_p(
                'screen_watchdog|join_task|initial_request:title',
                "Please share your screen!"
            )),
            description=t(_p(
                'screen_watchdog|join_task|initial_request:description',
                "**You have joined the screen share channel {channel}!**\n"
                "Please **share your screen** or **leave the channel** "
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
                'screen_watchdog|join_task|thanks:title',
                "Thanks for sharing your screen!"
            )),
        ).add_field(name='', value=jump_field)
        bye = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'screen_watchdog|join_task|bye:title',
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
            message = await alert_task

            member = member.guild.get_member(member.id)
            if member and message:
                if member.voice and (member.voice.channel == channel) and member.voice.self_stream:
                    embed = thanks
                else:
                    embed = bye
                embed.timestamp = utc_now()
                try:
                    await message.edit(embed=embed)
                except discord.HTTPException:
                    pass
        else:
            self._screen_tasks.pop((member.guild.id, member.id), None)

            try:
                await member.edit(
                    voice_channel=None,
                    reason=t(_p(
                        'screen_watchdog|join_task|kick_after_grace|audit_reason',
                        "Member never shared their screen in screen share channel."
                    ))
                )
            except discord.HTTPException:
                ...

            blacklist = lion.lguild.config.get(self.settings.ScreenBlacklist.setting_id)
            only_warn = (not lion.data.screen_warned) and blacklist
            ticket = None
            if not only_warn:
                try:
                    ticket = await self.blacklist_member(
                        member,
                        reason=t(_p(
                            'screen_watchdog|join_task|kick_after_grace|ticket_reason',
                            "Failed to share their screen in time in the screen share channel {channel}"
                        )).format(channel=channel.mention)
                    )
                except discord.HTTPException as e:
                    logger.debug(
                        f"Could not create blacklist ticket on member <uid:{member.id}> "
                        f"in <gid:{member.guild.id}>: {e.text}"
                    )
                    only_warn = True

            alert_ref = message.to_reference(fail_if_not_exists=False) if message else None
            if only_warn:
                warning = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'screen_watchdog|join_task|kick_after_grace|warning|title',
                        "You have received a warning!"
                    )),
                    description=t(_p(
                        'screen_watchdog|join_task|kick_after_grace|warning|desc',
                        "**You must share your screen in screen-share-only rooms.**\n"
                        "You have been disconnected from the channel {channel} for not "
                        "sharing your screen."
                    )).format(channel=channel.mention),
                    timestamp=utc_now()
                ).add_field(name='', value=jump_field)

                await modcog.send_alert(member, embed=warning, reference=alert_ref)
                if not lion.data.screen_warned:
                    await lion.data.update(screen_warned=True)
            else:
                # --- AI-MODIFIED (2026-04-03) ---
                # Purpose: Add duration, offense count, expiry, server, and channel
                #   as format placeholders to the blacklist notification embed
                violation_number = getattr(ticket, 'violation_number', None) or '?'
                if ticket and ticket.data.duration:
                    duration_str = strfdelta(dt.timedelta(seconds=ticket.data.duration))
                    expiry_str = discord.utils.format_dt(ticket.data.expiry, 'R')
                else:
                    duration_str = t(_p(
                        'screen_watchdog|blacklist|duration:permanent',
                        "Permanent"
                    ))
                    expiry_str = t(_p(
                        'screen_watchdog|blacklist|expiry:never',
                        "Never"
                    ))
                alert = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=t(_p(
                        'screen_watchdog|join_task|kick_after_grace|blacklist|title',
                        "You have been blacklisted!"
                    )),
                    description=t(_p(
                        'screen_watchdog|join_task|kick_after_grace|blacklist|desc',
                        "You have been blacklisted from the screen share channels in **{server}** "
                        "(offense #{count}).\n"
                        "**Duration:** {duration}\n"
                        "**Expires:** {expiry}"
                    )).format(
                        server=channel.guild.name,
                        channel=channel.mention,
                        count=violation_number,
                        duration=duration_str,
                        expiry=expiry_str,
                    ),
                    timestamp=utc_now()
                ).add_field(name='', value=jump_field)
                await modcog.send_alert(member, embed=alert, reference=alert_ref)
                # --- END AI-MODIFIED ---

    async def _disabled_screen_kick(self, member: discord.Member, channel: discord.VoiceChannel):
        try:
            await asyncio.sleep(15)
        except asyncio.CancelledError:
            return

        t = self.bot.translator.t
        logger.info(
            f"Removing member <uid:{member.id}> from screen share channel <cid:{channel.id}> in "
            f"<gid:{member.guild.id}> because they stopped sharing their screen."
        )
        self._screen_tasks.pop((member.guild.id, member.id), None)
        try:
            await asyncio.shield(
                member.edit(
                    voice_channel=None,
                    reason=t(_p(
                        'screen_watchdog|disabled_screen_kick|audit_reason',
                        "Disconnected for stopping screen share for more than {number} seconds in screen share channel."
                    )).format(number=15)
                )
            )
        except asyncio.CancelledError:
            pass
        except discord.HTTPException:
            pass

        embed = discord.Embed(
            colour=discord.Colour.brand_red(),
            title=t(_p(
                'screen_watchdog|disabled_screen_kick|notification|title',
                "You have been disconnected."
            )),
            description=t(_p(
                'screen_watchdog|disabled_screen_kick|notification|desc',
                "You were disconnected from the screen share channel {channel} because "
                "you stopped sharing your screen.\n"
                "Please keep your screen shared at all times, and leave the channel if you need "
                "to stop sharing!"
            )).format(channel=channel.mention)
        )
        modcog: ModerationCog = self.bot.get_cog('ModerationCog')
        await modcog.send_alert(
            member,
            embed=embed
        )

    async def blacklist_member(self, member: discord.Member, reason: str):
        return await ScreenTicket.autocreate(
            self.bot, member, reason
        )

    # ----- Commands -----

    # ------ Configuration -----
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        ...

    @configure_group.command(
        name=_p('cmd:configure_screen', "screen_channels"),
        description=_p(
            'cmd:configure_screen|desc', "Configure screen-share-only channels and blacklisting."
        )
    )
    @appcmds.rename(
        screen_blacklist=ScreenSettings.ScreenBlacklist._display_name,
        screen_blacklist_durations=ScreenSettings.ScreenBlacklistDurations._display_name,
        screen_grace_period=ScreenSettings.ScreenGracePeriod._display_name,
    )
    @appcmds.describe(
        screen_blacklist=ScreenSettings.ScreenBlacklist._desc,
        screen_blacklist_durations=ScreenSettings.ScreenBlacklistDurations._desc,
        screen_grace_period=ScreenSettings.ScreenGracePeriod._desc,
    )
    @high_management_ward
    async def configure_screen(self, ctx: LionContext,
                               screen_blacklist: Optional[discord.Role] = None,
                               screen_blacklist_durations: Optional[str] = None,
                               screen_grace_period: Optional[str] = None,
                               ):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True)

        modified = []

        if screen_blacklist is not None:
            await equippable_role(self.bot, screen_blacklist, ctx.author)
            setting = self.settings.ScreenBlacklist
            await setting._check_value(ctx.guild.id, screen_blacklist)
            instance = setting(ctx.guild.id, screen_blacklist.id)
            modified.append(instance)

        if screen_blacklist_durations is not None:
            setting = self.settings.ScreenBlacklistDurations
            instance = await setting.from_string(ctx.guild.id, screen_blacklist_durations)
            modified.append(instance)

        if screen_grace_period is not None:
            setting = self.settings.ScreenGracePeriod
            instance = await setting.from_string(ctx.guild.id, screen_grace_period)
            modified.append(instance)

        if modified:
            ack_lines = []
            for instance in modified:
                await instance.write()
                ack_lines.append(instance.update_message)

            tick = self.bot.config.emojis.tick
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description='\n'.join(f"{tick} {line}" for line in ack_lines),
            )
            await ctx.reply(embed=embed)

        if ctx.channel.id not in ScreenSettingUI._listening or not modified:
            ui = ScreenSettingUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()

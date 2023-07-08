from typing import Optional
import datetime as dt
import asyncio

import discord

from meta import LionBot
from utils.lib import utc_now
from utils.lib import MessageArgs

from .. import babel, logger
from ..data import ScheduleData as Data
from ..lib import slotid_to_utc
from ..settings import ScheduleSettings as Settings
from ..settings import ScheduleConfig
from ..ui.sessionui import SessionUI

from .session_member import SessionMember

_p = babel._p

my_room_permissions = discord.Permissions(
    connect=True,
    view_channel=True,
    manage_roles=True,
    manage_permissions=True
)
member_room_permissions = discord.PermissionOverwrite(
    connect=True,
    view_channel=True
)


class ScheduledSession:
    """
    Guild-local context for a scheduled session timeslot.

    Manages the status message and member list.
    """
    update_interval = 60
    max_update_interval = 10

    # TODO: Slots
    # NOTE: All methods MUST permit the guild or channels randomly vanishing
    # NOTE: All methods MUST be robust, and not propagate exceptions
    # TODO: Guild locale context
    def __init__(self,
                 bot: LionBot,
                 data: Data.ScheduleSession, config_data: Data.ScheduleGuild,
                 session_channels: Settings.SessionChannels):
        self.bot = bot
        self.data = data
        self.slotid = data.slotid
        self.guildid = data.guildid
        self.config = ScheduleConfig(self.guildid, config_data)
        self.channels_setting = session_channels

        self.starts_at = slotid_to_utc(self.slotid)
        self.ends_at = slotid_to_utc(self.slotid + 3600)

        # Whether to listen to clock events
        # should be set externally after the clocks have been initially set
        self.listening = False
        # Whether the session has prepared the room and sent the first message
        # Also set by open()
        self.prepared = False
        # Whether the session has set the room permissions
        self.opened = False
        # Whether this session has been cancelled. Always set externally
        self.cancelled = False

        self.members: dict[int, SessionMember] = {}
        self.lock = asyncio.Lock()

        self.status_message = None
        self._hook = None  # Lobby webhook data
        self._warned_hook = False

        self._last_update = None
        self._updater = None
        self._status_task = None

    def __repr__(self):
        return ' '.join(
            "<ScheduledSession"
            f"slotid={self.slotid}",
            f"guildid={self.guildid}",
            f"lobbyid={ch.id if (ch := self.lobby_channel) else None}",
            f"roomid={ch.id if (ch := self.room_channel) else None}",
            f"members={len(self.members)}",
            f"listening={self.listening}",
            f"prepared={self.prepared}",
            f"opened={self.opened}",
            f"cancelled={self.cancelled}",
            f"locked={self.lock.locked()}",
            f"status_message={msg.id if (msg := self.status_message) else None}",
            f"lobby_hook={hook.webhookid if (hook := self._hook) else None}",
            f"last_update={self._last_update}",
            f"updater_running={True if (self._updater and not self._updater.done()) else False}",
            ">"
        )

    # Setting shortcuts
    @property
    def room_channel(self) -> Optional[discord.VoiceChannel]:
        return self.config.get(Settings.SessionRoom.setting_id).value

    @property
    def lobby_channel(self) -> Optional[discord.TextChannel]:
        return self.config.get(Settings.SessionLobby.setting_id).value

    @property
    def bonus_reward(self) -> int:
        return self.config.get(Settings.AttendanceBonus.setting_id).value

    @property
    def attended_reward(self) -> int:
        return self.config.get(Settings.AttendanceReward.setting_id).value

    @property
    def min_attendence(self) -> int:
        return self.config.get(Settings.MinAttendance.setting_id).value

    @property
    def all_attended(self) -> bool:
        return all(member.total_clock >= self.min_attendence for member in self.members.values())

    @property
    def can_run(self) -> bool:
        """
        Returns True if this session exists and needs to run.
        """
        return self.guild and self.members

    @property
    def messageid(self) -> Optional[int]:
        return self.status_message.id if self.status_message else None

    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.guildid)

    def validate_channel(self, channelid) -> bool:
        channel = self.bot.get_channel(channelid)
        if channel is not None:
            channels = self.channels_setting.value
            return (not channels) or (channel in channels) or (channel.category and (channel.category in channels))
        else:
            return False

    async def get_lobby_hook(self) -> Optional[discord.Webhook]:
        """
        Fetch or create the webhook in the scheduled session lobby
        """
        channel = self.lobby_channel
        if channel:
            cid = channel.id
            if self._hook and self._hook.channelid == cid:
                hook = self._hook
            else:
                hook = self._hook = await self.bot.core.data.LionHook.fetch(cid)
                if not hook:
                    # Attempt to create
                    try:
                        if channel.permissions_for(channel.guild.me).manage_webhooks:
                            avatar = self.bot.user.avatar
                            avatar_data = (await avatar.to_file()).fp.read() if avatar else None
                            webhook = await channel.create_webhook(
                                avatar=avatar_data,
                                name=f"{self.bot.user.name} Scheduled Sessions",
                                reason="Scheduled Session Lobby"
                            )
                            hook = await self.bot.core.data.LionHook.create(
                                channelid=cid,
                                token=webhook.token,
                                webhookid=webhook.id
                            )
                        elif channel.permissions_for(channel.guild.me).send_messages and not self._warned_hook:
                            t = self.bot.translator.t
                            self._warned_hook = True
                            await channel.send(
                                t(_p(
                                    'session|error:lobby_webhook_perms',
                                    "Insufficient permissions to create a webhook in this channel. "
                                    "I require the `MANAGE_WEBHOOKS` permission."
                                ))
                            )
                    except discord.HTTPException:
                        logger.warning(
                            "Unexpected Exception occurred while creating scheduled session lobby webhook.",
                            exc_info=True
                        )
            if hook:
                return hook.as_webhook(client=self.bot)

    async def send(self, *args, wait=True, **kwargs):
        lobby_hook = await self.get_lobby_hook()
        if lobby_hook:
            try:
                return await lobby_hook.send(*args, wait=wait, **kwargs)
            except discord.NotFound:
                # Webhook was deleted under us
                if self._hook is not None:
                    await self._hook.delete()
                    self._hook = None
            except discord.HTTPException:
                logger.warning(
                    f"Exception occurred sending to webhooks for scheduled session {self!r}",
                    exc_info=True
                )

    async def prepare(self, **kwargs):
        """
        Execute prepare stage for this guild.
        """
        async with self.lock:
            await self.prepare_room()
            await self.update_status(**kwargs)
            self.prepared = True

    async def prepare_room(self):
        """
        Add overwrites allowing current members to connect.
        """
        async with self.lock:
            if not (members := list(self.members.values())):
                return
            if not (guild := self.guild):
                return
            if not (room := self.room_channel):
                return

            if room.permissions_for(guild.me) >= my_room_permissions:
                # Add member overwrites
                overwrites = room.overwrites
                for member in members:
                    mobj = guild.get_member(member.userid)
                    if mobj:
                        overwrites[mobj] = discord.PermissionOverwrite(connect=True, view_channel=True)
                try:
                    await room.edit(overwrites=overwrites)
                except discord.HTTPException:
                    logger.warning(
                        f"Unexpected discord exception received while preparing schedule session room {self!r}",
                        exc_info=True
                    )
                else:
                    logger.debug(
                        f"Prepared schedule session room for session {self!r}"
                    )
            else:
                t = self.bot.translator.t
                await self.send(
                    t(_p(
                        'session|prepare|error:room_permissions',
                        f"Could not prepare the configured session room {room} for the next scheduled session! "
                        "I require the `MANAGE_CHANNEL`, `MANAGE_ROLES`, `CONNECT` and `VIEW_CHANNEL` permissions."
                    )).format(room=room.mention)
                )

    async def open_room(self):
        """
        Remove overwrites for non-members.
        """
        async with self.lock:
            if not (members := list(self.members.values())):
                return
            if not (guild := self.guild):
                return
            if not (room := self.room_channel):
                return

            if room.permissions_for(guild.me) >= my_room_permissions:
                # Replace the member overwrites
                overwrites = {
                    target: overwrite for target, overwrite in room.overwrites.items()
                    if not isinstance(target, discord.Member)
                }
                for member in members:
                    mobj = guild.get_member(member.userid)
                    if mobj:
                        overwrites[mobj] = discord.PermissionOverwrite(connect=True, view_channel=True)
                try:
                    await room.edit(overwrites=overwrites)
                except discord.HTTPException:
                    logger.exception(
                        f"Unhandled discord exception received while opening schedule session room {self!r}"
                    )
                else:
                    logger.debug(
                        f"Opened schedule session room for session {self!r}"
                    )
            else:
                t = self.bot.translator.t
                await self.send(
                    t(_p(
                        'session|open|error:room_permissions',
                        f"Could not set up the configured session room {room} for this scheduled session! "
                        "I require the `MANAGE_CHANNEL`, `MANAGE_ROLES`, `CONNECT` and `VIEW_CHANNEL` permissions."
                    )).format(room=room.mention)
                )
            self.prepared = True
            self.opened = True

    async def notify(self):
        """
        Ghost ping members who have not yet attended.
        """
        missing = [mid for mid, m in self.members.items() if m.total_clock == 0 and m.clock_start is None]
        if missing:
            ping = ''.join(f"<@{mid}>" for mid in missing)
            message = await self.send(ping)
            if message is not None:
                asyncio.create_task(message.delete())

    async def current_status(self) -> MessageArgs:
        """
        Lobby status message args.
        """
        t = self.bot.translator.t
        now = utc_now()

        view = SessionUI(self.bot, self.slotid, self.guildid)
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=t(_p(
                'session|status|title',
                "Session {start} - {end}"
            )).format(
                start=discord.utils.format_dt(self.starts_at, 't'),
                end=discord.utils.format_dt(self.ends_at, 't'),
            )
        )
        embed.timestamp = now

        if self.cancelled:
            embed.description = t(_p(
                'session|status|desc:cancelled',
                "I cancelled this scheduled session because I was unavailable. "
                "All members who booked the session have been refunded."
            ))
            view = None
        elif not self.members:
            embed.description = t(_p(
                'session|status|desc:no_members',
                "*No members scheduled this session.*"
            ))
        elif now < self.starts_at:
            # Preparation stage
            embed.description = t(_p(
                'session|status:preparing|desc:has_members',
                "Starting {start}"
            )).format(start=discord.utils.format_dt(self.starts_at, 'R'))
            embed.add_field(
                name=t(_p('session|status:preparing|field:members', "Members")),
                value=', '.join(f"<@{m}>" for m in self.members)
            )
        elif now < self.starts_at + dt.timedelta(hours=1):
            # Running status
            embed.description = t(_p(
                'session|status:running|desc:has_members',
                "Finishing {start}"
            )).format(start=discord.utils.format_dt(self.ends_at, 'R'))

            missing = []
            present = []
            min_attendence = self.min_attendence
            for mid, member in self.members.items():
                clock = int(member.total_clock)
                if clock == 0 and member.clock_start is None:
                    memstr = f"<@{mid}>"
                    missing.append(memstr)
                else:
                    memstr = "<@{mid}> **({M:02}:{S:02})**".format(
                        mid=mid,
                        M=int(clock // 60),
                        S=int(clock % 60)
                    )
                    present.append((memstr, clock, bool(member.clock_start)))

            waiting_for = []
            attending = []
            attended = []
            present.sort(key=lambda t: t[1], reverse=True)
            for memstr, clock, clocking in present:
                if clocking:
                    attending.append(memstr)
                elif clock >= min_attendence:
                    attended.append(memstr)
                else:
                    waiting_for.append(memstr)
            waiting_for.extend(missing)

            if waiting_for:
                embed.add_field(
                    name=t(_p('session|status:running|field:waiting', "Waiting For")),
                    value='\n'.join(waiting_for),
                    inline=True
                )
            if attending:
                embed.add_field(
                    name=t(_p('session|status:running|field:attending', "Attending")),
                    value='\n'.join(attending),
                    inline=True
                )
            if attended:
                embed.add_field(
                    name=t(_p('session|status:running|field:attended', "Attended")),
                    value='\n'.join(attended),
                    inline=True
                )
        else:
            # Finished, show summary
            attended = []
            missed = []
            min_attendence = self.min_attendence
            for mid, member in self.members.items():
                clock = int(member.total_clock)
                memstr = "<@{mid}> **({M:02}:{S:02})**".format(
                    mid=mid,
                    M=int(clock // 60),
                    S=int(clock % 60)
                )
                if clock < min_attendence:
                    missed.append(memstr)
                else:
                    attended.append(memstr)

            if not missed:
                # Everyone attended
                embed.description = t(_p(
                    'session|status:finished|desc:everyone_att',
                    "Everyone attended the session! "
                    "All members were rewarded with {coin} **{reward} + {bonus}**!"
                )).format(
                    coin=self.bot.config.emojis.coin,
                    reward=self.attended_reward,
                    bonus=self.bonus_reward
                )
            elif missed and attended:
                # Mix of both
                embed.description = t(_p(
                    'session|status:finished|desc:some_att',
                    "Everyone who attended was rewarded with {coin} **{reward}**! "
                    "Some members did not attend so everyone missed out on the bonus {coin} **{bonus}**.\n"
                    "**Members who missed their session have all future sessions cancelled without refund!*"
                )).format(
                    coin=self.bot.config.emojis.coin,
                    reward=self.attended_reward,
                    bonus=self.bonus_reward
                )
            else:
                # No-one attended
                embed.description = t(_p(
                    'session|status:finished|desc:some_att',
                    "No-one attended this session! No-one received rewards.\n"
                    "**Members who missed their session have all future sessions cancelled without refund!*"
                ))

            if attended:
                embed.add_field(
                    name=t(_p('session|status:finished|field:attended', "Attended")),
                    value='\n'.join(attended)
                )
            if missed:
                embed.add_field(
                    name=t(_p('session|status:finished|field:missing', "Missing")),
                    value='\n'.join(missed)
                )
            view = None

        if view is not None:
            await view.reload()
        args = MessageArgs(embed=embed, view=view)
        return args

    async def _update_status(self, save=True, resend=True):
        """
        Send or update the lobby message.
        """
        self._last_update = utc_now()
        args = await self.current_status()

        message = self.status_message
        if message is None and self.data.messageid is not None:
            lobby_hook = await self.get_lobby_hook()
            if lobby_hook:
                try:
                    message = await lobby_hook.fetch_message(self.data.messageid)
                except discord.HTTPException:
                    message = None

        repost = message is None
        if not repost:
            try:
                await message.edit(**args.edit_args)
                self.status_message = message
            except discord.NotFound:
                repost = True
                self.status_message = None
            except discord.HTTPException:
                # Unexpected issue updating the message
                logger.exception(
                    f"Exception occurred updating status for scheduled session {self!r}"
                )

        if repost and resend and self.members:
            message = await self.send(**args.send_args)
            self.status_message = message
            if save:
                await self.data.update(messageid=message.id if message else None)

    async def _update_status_soon(self, **kwargs):
        try:
            if self._last_update is not None:
                next_update = self._last_update + dt.timedelta(seconds=self.max_update_interval)
                await discord.utils.sleep_until(next_update)
            task = asyncio.create_task(self._update_status(**kwargs))
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass

    def update_status_soon(self, **kwargs):
        if self._status_task and not self._status_task.done():
            self._status_task.cancel()
        self._status_task = asyncio.create_task(self._update_status_soon(**kwargs))

    async def update_status(self, **kwargs):
        if self._status_task and not self._status_task.done():
            self._status_task.cancel()
        await self._update_status(**kwargs)

    async def update_loop(self):
        """
        Keep the lobby message up to date with a message per minute.
        Takes into account external and manual updates.
        """
        try:
            if self._last_update:
                await discord.utils.sleep_until(self._last_update + dt.timedelta(seconds=self.update_interval))

            while (now := utc_now()) <= self.ends_at:
                await self.update_status()
                while now < (next_update := (self._last_update + dt.timedelta(seconds=self.update_interval))):
                    await discord.utils.sleep_until(next_update)
                    now = utc_now()
            await self.update_status()
        except asyncio.CancelledError:
            logger.debug(
                f"Cancelled scheduled session update loop for session {self!r}"
            )
        except Exception:
            logger.exception(
                "Unknown exception encountered during session update loop for session {self!r} "
            )

    def start_updating(self):
        self._updater = asyncio.create_task(self.update_loop())
        return self._updater

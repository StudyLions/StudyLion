from typing import Optional
import asyncio
from datetime import timedelta, datetime

import discord

from meta import LionBot
from meta.logger import log_wrap, log_context
from utils.lib import utc_now
from core.lion_guild import LionGuild
from babel.translator import ctx_locale

from modules.pomodoro.cog import TimerCog
from modules.pomodoro.timer import Timer

from . import babel, logger
from .data import RoomData
from .roomui import RoomUI
from .lib import owner_overwrite, member_overwrite

_p = babel._p


class Room:
    __slots__ = ('bot', 'data', 'lguild', 'members', '_tick_wait')

    tick_length = timedelta(days=1)
    # tick_length = timedelta(hours=1)

    def __init__(self, bot: LionBot, data: RoomData.Room, lguild: LionGuild, members: list[int]):
        self.bot = bot
        self.data = data
        self.lguild = lguild
        self.members = members

        log_context.set(f"cid: {self.data.channelid}")

        # State
        self._tick_wait: Optional[asyncio.Task] = None

    @property
    def channel(self) -> Optional[discord.VoiceChannel]:
        """
        Discord Channel which this room lives in.
        """
        return self.bot.get_channel(self.data.channelid)

    @property
    def timer(self) -> Optional[Timer]:
        timer_cog: TimerCog = self.bot.get_cog('TimerCog')
        if timer_cog is not None:
            return timer_cog.get_channel_timer(self.data.channelid)

    @property
    def last_tick(self):
        return self.data.last_tick or self.data.created_at

    @property
    def next_tick(self):
        return self.last_tick + self.tick_length

    @property
    def rent(self):
        return self.lguild.config.get('rooms_price').value

    @property
    def expiring(self):
        return self.rent > self.data.coin_balance

    @property
    def deleted(self):
        return bool(self.data.deleted_at)

    async def notify_deposit(self, member: discord.Member, amount: int):
        # Assumes locale is set correctly
        t = self.bot.translator.t
        notification = discord.Embed(
            colour=discord.Colour.brand_green(),
            description=t(_p(
                'room|notify:deposit|description',
                "{member} has deposited {coin}**{amount}** into the room bank!"
            )).format(member=member.mention, coin=self.bot.config.emojis.coin, amount=amount)
        )
        if self.channel:
            try:
                await self.channel.send(embed=notification)
            except discord.HTTPException:
                pass

    async def add_new_members(self, memberids):
        # Ensure members exist
        await self.bot.core.lions.fetch_members(*((self.data.guildid, mid) for mid in memberids))
        member_data = self.bot.get_cog('RoomCog').data.RoomMember
        await member_data.table.insert_many(
            ('channelid', 'userid'),
            *((self.data.channelid, memberid) for memberid in memberids)
        )
        self.members.extend(memberids)
        t = self.bot.translator.t
        notification = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'room|notify:new_members|title',
                "New Members!"
            )),
            description=t(_p(
                'room|notify:new_members|desc',
                "Welcome {members}"
            )).format(members=', '.join(f"<@{mid}>" for mid in memberids))
        )
        if self.channel:
            try:
                await self.channel.send(embed=notification)
            except discord.HTTPException:
                pass

    async def rm_members(self, memberids):
        member_data = self.bot.get_cog('RoomCog').data.RoomMember
        await member_data.table.delete_where(channelid=self.data.channelid, userid=list(memberids))
        self.members = list(set(self.members).difference(memberids))
        # No need to notify for removal
        return

    async def transfer_ownership(self, new_owner):
        member_data = self.bot.get_cog('RoomCog').data.RoomMember
        old_ownerid = self.data.ownerid

        # Add old owner as a member
        await member_data.create(channelid=self.data.channelid, userid=old_ownerid)
        self.members.append(old_ownerid)

        # Remove new owner from the members
        await member_data.table.delete_where(channelid=self.data.channelid, userid=new_owner.id)
        self.members.remove(new_owner.id)

        # Change room owner
        await self.data.update(ownerid=new_owner.id)

        if self.channel:
            try:
                # Update overwrite for old owner
                if old_owner := self.channel.guild.get_member(old_ownerid):
                    await self.channel.set_permissions(
                        old_owner,
                        overwrite=member_overwrite
                    )
                # Update overwrite for new owner
                await self.channel.set_permissions(
                    new_owner,
                    overwrite=owner_overwrite
                )
            except discord.HTTPException:
                logger.warning(
                    "Exception while changing room ownership. Room overwrites may be incorrect.",
                    exc_info=True
                )
            # Notification
            t = self.bot.translator.t
            notification = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'room|notify:transfer|description',
                    "{old_owner} has transferred private room ownership to {new_owner}"
                )).format(old_owner=f"<@{old_ownerid}>", new_owner=new_owner.mention)
            )
            try:
                await self.channel.send(embed=notification)
            except discord.HTTPException:
                pass

    @log_wrap(action="Room Runloop")
    async def run(self):
        """
        Tick loop.

        Keeps scheduling ticks until expired or cancelled.
        May be safely cancelled.
        """
        if self._tick_wait and not self._tick_wait.done():
            self._tick_wait.cancel()

        while not self.deleted:
            now = utc_now()
            diff = (self.next_tick - now).total_seconds()
            self._tick_wait = asyncio.create_task(asyncio.sleep(diff))
            try:
                await self._tick_wait
                await asyncio.shield(self._tick())
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    f"Unhandled exception while ticking for room: {self.data!r}"
                )

    @log_wrap(action="Room Tick")
    async def _tick(self):
        """
        Execute the once-per day room tick.

        This deducts the rent amount from the room balance,
        if the balance is insufficient, expires the room.
        Posts a status message in the room channel when it does so.
        """
        t = self.bot.translator.t
        ctx_locale.set(self.lguild.config.get('guild_locale').value)
        if self.deleted:
            # Already deleted, nothing to do
            pass
        else:
            # Run tick
            logger.debug(f"Tick running for room: {self.data!r}")

            # Deduct balance
            await self.data.update(
                coin_balance=RoomData.Room.coin_balance - self.rent,
                last_tick=utc_now()
            )

            # If balance is negative, expire room, otherwise notify channel
            if self.data.coin_balance < 0:
                if owner := self.bot.get_user(self.data.ownerid):
                    embed = discord.Embed(
                        colour=discord.Colour.red(),
                        title=t(_p(
                            'room|embed:expiry|title',
                            "Private Room Expired!"
                        )),
                        description=t(_p(
                            'room|embed:expiry|description',
                            "Your private room in **{guild}** has expired!"
                        )).format(guild=self.bot.get_guild(self.data.guildid))
                    )
                    try:
                        await owner.send(embed=embed)
                    except discord.HTTPException:
                        pass
                await self.destroy(reason='Room Expired')
            elif self.channel:
                # Notify channel
                embed = discord.Embed(
                    colour=discord.Colour.orange(),
                    description=self.bot.translator.t(_p(
                            'room|tick|rent_deducted',
                            "Daily rent deducted from room balance. New balance: {coin}**{amount}**"
                        )).format(
                            coin=self.bot.config.emojis.coin, amount=self.data.coin_balance
                        )
                )
                try:
                    await self.channel.send(embed=embed)
                except discord.HTTPException:
                    pass
            else:
                # No channel means room was deleted
                # Just cleanup quietly
                await self.destroy(reason='Channel Missing')

    @log_wrap(action="Destroy Room")
    async def destroy(self, reason: Optional[str] = None):
        """
        Destroy the room.

        Attempts to delete the voice channel and log destruction.
        This is idempotent, so multiple events may trigger destroy.
        """
        if self._tick_wait:
            self._tick_wait.cancel()

        if self.channel:
            try:
                await self.channel.delete()
            except discord.HTTPException:
                pass

        if not self.deleted:
            logger.info(
                f"Destroying private room <cid: {self.data.channelid}> for reason '{reason}': {self.data!r}"
            )
            await self.data.update(deleted_at=utc_now())

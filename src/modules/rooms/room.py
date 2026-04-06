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
# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Import ROOM_DASHBOARD_URL for link buttons in room notifications
from .lib import owner_overwrite, member_overwrite, ROOM_DASHBOARD_URL
# --- END AI-MODIFIED ---

_p = babel._p


class Room:
    # --- AI-MODIFIED (2026-04-03) ---
    # Purpose: Added _member_sync_task to periodically sync member list from DB
    # (catches dashboard-initiated leaves that only delete the DB row).
    # --- Original code (commented out for rollback) ---
    # __slots__ = ('bot', 'data', 'lguild', 'members', '_tick_wait', '_name_sync_task')
    # --- End original code ---
    __slots__ = ('bot', 'data', 'lguild', 'members', '_tick_wait', '_name_sync_task', '_member_sync_task')
    # --- END AI-MODIFIED ---

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
        self._name_sync_task: Optional[asyncio.Task] = None
        self._member_sync_task: Optional[asyncio.Task] = None

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

    def eventlog_fields(self) -> dict[str, tuple[str, bool]]:
        t = self.bot.translator.t
        fields = {
            t(_p(
                'room|eventlog|field:owner', "Owner"
            )): (
                f"<@{self.data.ownerid}>",
                True
            ),
            t(_p(
                'room|eventlog|field:channel', "Channel"
            )): (
                f"<#{self.data.channelid}>",
                True
            ),
            t(_p(
                'room|eventlog|field:balance', "Room Balance"
            )): (
                f"{self.bot.config.emojis.coin} **{self.data.coin_balance}**",
                True
            ),
            t(_p(
                'room|eventlog|field:created', "Created At"
            )): (
                discord.utils.format_dt(self.data.created_at, 'F'),
                True
            ),
            t(_p(
                'room|eventlog|field:tick', "Next Rent Due"
            )): (
                discord.utils.format_dt(self.next_tick, 'R'),
                True
            ),
            t(_p(
                'room|eventlog|field:members', "Private Room Members"
            )): (
                ','.join(f"<@{member}>" for member in self.members),
                False
            ),
        }
        return fields

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
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Add "View Room" dashboard link button to deposit notification
        link_view = discord.ui.View()
        link_view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            url=ROOM_DASHBOARD_URL,
            label="View Room"
        ))
        # --- END AI-MODIFIED ---
        if self.channel:
            try:
                # --- AI-MODIFIED (2026-03-22) ---
                # --- Original code (commented out for rollback) ---
                # await self.channel.send(embed=notification)
                # --- End original code ---
                await self.channel.send(embed=notification, view=link_view)
                # --- END AI-MODIFIED ---
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
        self.lguild.log_event(
            title=t(_p(
                'room|eventlog|event:new_members|title',
                "Members invited to private room"
            )),
            description=t(_p(
                'room|eventlog|event:new_members|desc',
                "{owner} added members to their private room: {members}"
            )).format(
                members=', '.join(f"<@{mid}>" for mid in memberids),
                owner="<@{mid}>".format(mid=self.data.ownerid),
            ),
            fields=self.eventlog_fields()
        )
        if self.channel:
            # --- AI-MODIFIED (2026-04-04) ---
            # Purpose: Only send join notification if rooms_notifications is enabled
            notify = self.lguild.config.get('rooms_notifications').value
            if notify is not False:
                try:
                    await self.channel.send(embed=notification)
                except discord.HTTPException:
                    pass
            # --- END AI-MODIFIED ---
            guild = self.channel.guild
            members = [guild.get_member(memberid) for memberid in memberids]
            members = [member for member in members if member]
            for member in members:
                await self.channel.set_permissions(
                    member,
                    overwrite=member_overwrite,
                    reason="Adding invited members to private room."
                )

    async def rm_members(self, memberids):
        member_data = self.bot.get_cog('RoomCog').data.RoomMember
        await member_data.table.delete_where(channelid=self.data.channelid, userid=list(memberids))
        self.members = list(set(self.members).difference(memberids))
        # No need to notify for removal
        t = self.bot.translator.t
        self.lguild.log_event(
            title=t(_p(
                'room|eventlog|event:rm_members|title',
                "Members removed from private room"
            )),
            description=t(_p(
                'room|eventlog|event:rm_members|desc',
                "{owner} removed members from their private room: {members}"
            )).format(
                members=', '.join(f"<@{mid}>" for mid in memberids),
                owner="<@{mid}>".format(mid=self.data.ownerid),
            ),
            fields=self.eventlog_fields()
        )
        if self.channel:
            guild = self.channel.guild
            members = [guild.get_member(memberid) for memberid in memberids]
            members = [member for member in members if member]
            for member in members:
                if member.id != self.data.ownerid and member != guild.me:
                    await self.channel.set_permissions(
                        member,
                        overwrite=None,
                        reason="Removing kicked members from private room."
                    )
        return

    # --- AI-MODIFIED (2026-04-03) ---
    # Purpose: Allow a non-owner member to voluntarily leave the room
    async def leave_member(self, memberid: int):
        member_data = self.bot.get_cog('RoomCog').data.RoomMember
        await member_data.table.delete_where(channelid=self.data.channelid, userid=[memberid])
        self.members = [m for m in self.members if m != memberid]
        t = self.bot.translator.t
        self.lguild.log_event(
            title=t(_p(
                'room|eventlog|event:member_left|title',
                "Member left private room"
            )),
            description=t(_p(
                'room|eventlog|event:member_left|desc',
                "<@{member}> left {owner}'s private room."
            )).format(
                member=memberid,
                owner=self.data.ownerid,
            ),
            fields=self.eventlog_fields()
        )
        if self.channel:
            guild = self.channel.guild
            member = guild.get_member(memberid)
            if member and member.id != self.data.ownerid and member != guild.me:
                await self.channel.set_permissions(
                    member,
                    overwrite=None,
                    reason="Member left private room voluntarily."
                )
            # --- AI-MODIFIED (2026-04-04) ---
            # Purpose: Only send leave notification if rooms_notifications is enabled
            notify = self.lguild.config.get('rooms_notifications').value
            if notify is not False:
                notification = discord.Embed(
                    colour=discord.Colour.orange(),
                    description=t(_p(
                        'room|notify:member_left|desc',
                        "<@{member}> has left the room."
                    )).format(member=memberid)
                )
                try:
                    await self.channel.send(embed=notification)
                except discord.HTTPException:
                    pass
            # --- END AI-MODIFIED ---
    # --- END AI-MODIFIED ---

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

    # --- AI-MODIFIED (2026-04-03) ---
    # Purpose: Periodically re-read member list from DB and sync Discord permissions
    # for any changes made externally (e.g. dashboard leave). This fixes the bug where
    # the dashboard leave.ts only deletes the rented_members row but doesn't update
    # Discord channel permissions or the bot's in-memory member list.
    async def _sync_members_from_db(self):
        member_model = self.bot.get_cog('RoomCog').data.RoomMember
        db_rows = await member_model.table.select_where(
            channelid=self.data.channelid
        )
        db_member_ids = set(row['userid'] for row in db_rows)
        current_member_ids = set(self.members)

        removed = current_member_ids - db_member_ids
        added = db_member_ids - current_member_ids

        if not removed and not added:
            return

        if self.channel:
            guild = self.channel.guild
            t = self.bot.translator.t
            # --- AI-MODIFIED (2026-04-04) ---
            # Purpose: Only send leave notification if rooms_notifications is enabled
            notify = self.lguild.config.get('rooms_notifications').value
            # --- END AI-MODIFIED ---
            for mid in removed:
                member = guild.get_member(mid)
                if member and member.id != self.data.ownerid and member != guild.me:
                    try:
                        await self.channel.set_permissions(
                            member,
                            overwrite=None,
                            reason="Dashboard sync: member left via website"
                        )
                    except discord.HTTPException:
                        pass
                # --- AI-MODIFIED (2026-04-04) ---
                # Purpose: Only send leave notification if rooms_notifications is enabled
                if notify is not False:
                    notification = discord.Embed(
                        colour=discord.Colour.orange(),
                        description=t(_p(
                            'room|notify:member_left|desc',
                            "<@{member}> has left the room."
                        )).format(member=mid)
                    )
                    try:
                        await self.channel.send(embed=notification)
                    except discord.HTTPException:
                        pass
                # --- END AI-MODIFIED ---
            for mid in added:
                member = guild.get_member(mid)
                if member:
                    try:
                        await self.channel.set_permissions(
                            member,
                            overwrite=member_overwrite,
                            reason="Dashboard sync: member added via website"
                        )
                    except discord.HTTPException:
                        pass

        self.members = list(db_member_ids)
        if removed:
            logger.info(
                f"Dashboard member sync <cid: {self.data.channelid}>: removed {removed}"
            )
        if added:
            logger.info(
                f"Dashboard member sync <cid: {self.data.channelid}>: added {added}"
            )

    async def _member_sync_loop(self):
        while not self.deleted:
            try:
                await asyncio.sleep(300)
                if self.deleted:
                    break
                await self._sync_members_from_db()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    f"Error in member sync loop for room <cid: {self.data.channelid}>"
                )
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: Safe name sync loop -- ONLY syncs when name_changed_at is set in the DB,
    # meaning the dashboard explicitly renamed the room. Clears name_changed_at after
    # syncing so it never fires again for the same rename. User-initiated Discord renames
    # (which don't touch name_changed_at) are never overwritten.
    async def _name_sync_loop(self):
        while not self.deleted:
            try:
                await asyncio.sleep(300)
                if self.deleted:
                    break
                fresh = await RoomData.Room.fetch(self.data.channelid)
                if not fresh or fresh.deleted_at:
                    break
                if fresh.name_changed_at is None:
                    continue
                db_name = fresh.name
                if not db_name or not self.channel:
                    continue
                if self.channel.name != db_name:
                    try:
                        await self.channel.edit(name=db_name, reason="Room name synced from dashboard")
                        logger.info(
                            f"Synced dashboard rename for <cid: {self.data.channelid}> to '{db_name}'"
                        )
                    except discord.HTTPException as e:
                        if e.status == 429:
                            retry_after = getattr(e, 'retry_after', 60)
                            logger.warning(
                                f"Rate limited syncing dashboard rename for "
                                f"<cid: {self.data.channelid}>, retry in {retry_after}s"
                            )
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            logger.warning(
                                f"Failed to sync dashboard rename for <cid: {self.data.channelid}>",
                                exc_info=True
                            )
                self.data.name = db_name
                await fresh.update(name_changed_at=None)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    f"Error in name sync loop for room <cid: {self.data.channelid}>"
                )
                await asyncio.sleep(60)
    # --- END AI-MODIFIED ---

    @log_wrap(action="Room Runloop")
    async def run(self):
        """
        Tick loop.

        Keeps scheduling ticks until expired or cancelled.
        May be safely cancelled.
        """
        if self._tick_wait and not self._tick_wait.done():
            self._tick_wait.cancel()

        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Launch name sync + member sync loops alongside the tick loop.
        # Member sync catches dashboard-initiated leaves that only delete the DB row.
        # --- Original code (commented out for rollback) ---
        # self._name_sync_task = asyncio.create_task(self._name_sync_loop())
        # --- End original code ---
        self._name_sync_task = asyncio.create_task(self._name_sync_loop())
        self._member_sync_task = asyncio.create_task(self._member_sync_loop())
        # --- END AI-MODIFIED ---

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

        # --- AI-MODIFIED (2026-04-03) ---
        # Purpose: Cancel sync tasks when run loop exits
        # --- Original code (commented out for rollback) ---
        # if self._name_sync_task and not self._name_sync_task.done():
        #     self._name_sync_task.cancel()
        # --- End original code ---
        if self._name_sync_task and not self._name_sync_task.done():
            self._name_sync_task.cancel()
        if self._member_sync_task and not self._member_sync_task.done():
            self._member_sync_task.cancel()
        # --- END AI-MODIFIED ---

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

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Re-read room state from DB to detect dashboard-initiated changes
        # (e.g., admin force-closed or froze the room via the website)
        fresh = await RoomData.Room.fetch(self.data.channelid)
        if fresh:
            self.data.deleted_at = fresh.deleted_at
            self.data.frozen_at = fresh.frozen_at
            self.data.frozen_by = fresh.frozen_by
            self.data.name = fresh.name
        # --- END AI-MODIFIED ---

        if self.deleted:
            # Already deleted, nothing to do
            pass
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Skip rent deduction when room is frozen by admin; still sync name
        elif self.data.frozen_at:
            logger.debug(f"Room <cid: {self.data.channelid}> is frozen, skipping rent deduction")
            await self.data.update(last_tick=utc_now())
            if self.channel:
                t = self.bot.translator.t
                embed = discord.Embed(
                    colour=discord.Colour.blue(),
                    description="This room is **frozen** by a server admin. Rent is paused."
                )
                try:
                    await self.channel.send(embed=embed)
                except discord.HTTPException:
                    pass
        # --- END AI-MODIFIED ---
        else:
            # Run tick
            logger.debug(f"Tick running for room: {self.data!r}")

            # Deduct balance
            await self.data.update(
                coin_balance=RoomData.Room.coin_balance - self.rent,
                last_tick=utc_now()
            )

            # If balance is negative, try auto-extend or expire room
            if self.data.coin_balance < 0:
                # --- AI-MODIFIED (2026-04-01) ---
                # Purpose: Auto-extend by charging owner's wallet when room bank is empty
                from .settings import RoomSettings
                from core.data import CoreData
                auto_extend = self.lguild.config.get(RoomSettings.AutoExtend.setting_id).value
                auto_extended = False
                if auto_extend:
                    try:
                        rent = self.rent
                        owner_lion = await self.bot.core.lions.fetch_member(self.data.guildid, self.data.ownerid)
                        await owner_lion.data.refresh()
                        if owner_lion.data.coins >= rent:
                            await owner_lion.data.update(coins=CoreData.Member.coins - rent)
                            await self.data.update(coin_balance=RoomData.Room.coin_balance + rent)
                            auto_extended = True
                            coin = self.bot.config.emojis.coin
                            if self.channel:
                                embed = discord.Embed(
                                    colour=discord.Colour.gold(),
                                    description=t(_p(
                                        'room|tick|auto_extend',
                                        "Room bank was empty! {coin}**{rent}** was automatically "
                                        "deducted from the owner's wallet. "
                                        "New room balance: {coin}**{balance}**"
                                    )).format(
                                        coin=coin, rent=rent,
                                        balance=self.data.coin_balance
                                    )
                                )
                                link_view = discord.ui.View()
                                link_view.add_item(discord.ui.Button(
                                    style=discord.ButtonStyle.link,
                                    url=ROOM_DASHBOARD_URL,
                                    label="Deposit Now"
                                ))
                                try:
                                    await self.channel.send(embed=embed, view=link_view)
                                except discord.HTTPException:
                                    pass
                            logger.info(
                                f"Auto-extended room <cid: {self.data.channelid}> "
                                f"by charging owner {self.data.ownerid} {rent} coins"
                            )
                    except Exception:
                        logger.exception(
                            f"Failed to auto-extend room <cid: {self.data.channelid}>"
                        )
                # --- END AI-MODIFIED ---

                if not auto_extended:
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
                        # --- AI-MODIFIED (2026-03-22) ---
                        # Purpose: Add "View All Rooms" dashboard link button to expiry DM
                        link_view = discord.ui.View()
                        link_view.add_item(discord.ui.Button(
                            style=discord.ButtonStyle.link,
                            url=ROOM_DASHBOARD_URL,
                            label="View All Rooms"
                        ))
                        # --- END AI-MODIFIED ---
                        try:
                            # --- AI-MODIFIED (2026-03-22) ---
                            # --- Original code (commented out for rollback) ---
                            # await owner.send(embed=embed)
                            # --- End original code ---
                            await owner.send(embed=embed, view=link_view)
                            # --- END AI-MODIFIED ---
                        except discord.HTTPException:
                            pass
                    self.lguild.log_event(
                        title=t(_p(
                            'room|eventlog|event:expired|title',
                            "Private Room Expired"
                        )),
                        description=t(_p(
                            'room|eventlog|event:expired|desc',
                            "{owner}'s private room has expired."
                        )).format(
                            owner="<@{mid}>".format(mid=self.data.ownerid),
                        ),
                        fields=self.eventlog_fields()
                    )
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
                # --- AI-MODIFIED (2026-03-22) ---
                # Purpose: Add "Deposit Now" dashboard link button to tick notification
                link_view = discord.ui.View()
                link_view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    url=ROOM_DASHBOARD_URL,
                    label="Deposit Now"
                ))
                # --- END AI-MODIFIED ---
                try:
                    # --- AI-MODIFIED (2026-03-22) ---
                    # --- Original code (commented out for rollback) ---
                    # await self.channel.send(embed=embed)
                    # --- End original code ---
                    await self.channel.send(embed=embed, view=link_view)
                    # --- END AI-MODIFIED ---
                except discord.HTTPException:
                    pass
            else:
                # No channel means room was deleted
                # Just cleanup quietly
                self.lguild.log_event(
                    title=t(_p(
                        'room|eventlog|event:room_deleted|title',
                        "Private Room Deleted"
                    )),
                    description=t(_p(
                        'room|eventlog|event:room_deleted|desc',
                        "{owner}'s private room was deleted."
                    )).format(
                        owner="<@{mid}>".format(mid=self.data.ownerid),
                    ),
                    fields=self.eventlog_fields()
                )
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
        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: Cancel name sync task on room destroy
        if self._name_sync_task and not self._name_sync_task.done():
            self._name_sync_task.cancel()
        # --- END AI-MODIFIED ---

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

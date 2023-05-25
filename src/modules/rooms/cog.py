from typing import Optional
from collections import defaultdict
import asyncio

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.app_commands import Range

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.errors import ResponseTimedOut
from meta.sharding import THIS_SHARD
from utils.lib import utc_now, error_embed
from utils.ui import Confirm
from constants import MAX_COINS
from core.data import CoreData

from wards import low_management

from . import babel, logger
from .data import RoomData
from .settings import RoomSettings
from .settingui import RoomSettingUI
from .room import Room
from .roomui import RoomUI
from .lib import parse_members, owner_overwrite, member_overwrite

_p, _np = babel._p, babel._np


class RoomCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(RoomData())
        self.settings = RoomSettings()

        self.ready = False
        self.event_lock = asyncio.Lock()
        self._room_cache = defaultdict(dict)  # Map guildid -> channelid -> Room
        self._ticker_tasks = {}  # Map channelid -> room run task

    async def cog_load(self):
        await self.data.init()

        for setting in self.settings.model_settings:
            self.bot.core.guild_config.register_model_setting(setting)

        configcog = self.bot.get_cog('ConfigCog')
        self.crossload_group(self.configure_group, configcog.configure_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        # Cancel room tick loops
        for task in self._ticker_tasks.values():
            task.cancel()

    async def _prepare_rooms(self, room_data: list[RoomData.Room]):
        """
        Launch or destroy rooms from the provided room data.

        Client cache MUST be initialised, or rooms will be destroyed.
        """
        # Launch or destroy rooms for the given data rows
        to_delete = []
        to_launch = []
        lguildids = set()
        for row in room_data:
            channel = self.bot.get_channel(row.channelid)
            if channel is None:
                to_delete.append(row.channelid)
            else:
                lguildids.add(row.guildid)
                to_launch.append(row)

        if to_delete:
            now = utc_now()
            await self.data.Room.table.update_where(channelid=to_delete).set(deleted_at=now)
            room_list = ', '.join(map(str, to_delete))
            logger.info(
                f"Deleted {len(to_delete)} private rooms with no underlying channel: {room_list}"
            )

        if to_launch:
            lguilds = await self.bot.core.lions.fetch_guilds(*lguildids)
            member_data = await self.data.RoomMember.fetch_where(channelid=[r.channelid for r in to_launch])
            member_map = defaultdict(list)
            for row in member_data:
                member_map[row.channelid].append(row.userid)
            for row in to_launch:
                room = Room(self.bot, row, lguilds[row.guildid], member_map[row.channelid])
                self._start(room)

        logger.info(
            f"Launched ticker tasks for {len(to_launch)} private rooms."
        )

    def _start(self, room: Room):
        task = asyncio.create_task(self._ticker(room))
        key = room.data.channelid
        self._ticker_tasks[key] = task
        task.add_done_callback(lambda fut: self._ticker_tasks.pop(key, None))

    async def _ticker(self, room: Room):
        cache = self._room_cache
        cache[room.data.guildid][room.data.channelid] = room
        try:
            await room.run()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                f"Unhandled exception during room run task. This should not happen! {room.data!r}"
            )
        finally:
            cache[room.data.guildid].pop(room.data.channelid)

    # ----- Event Handlers -----
    @LionCog.listener('on_ready')
    @log_wrap(action='Init Rooms')
    async def initialise(self):
        """
        Restore rented channels.
        """
        async with self.event_lock:
            # Cancel any running tickers, we will recreate them
            for task in self._ticker_tasks.values():
                task.cancel()

            room_data = await self.data.Room.fetch_where(THIS_SHARD, deleted_at=None)
            await self._prepare_rooms(room_data)

            logger.info(
                f"Private Room system initialised with {len(self._ticker_tasks)} running rooms."
            )

    @LionCog.listener('on_guild_remove')
    @log_wrap(action='Destroy Guild Rooms')
    async def _unload_guild_rooms(self, guild: discord.Guild):
        if guild.id in self._room_cache:
            rooms = list(self._room_cache[guild.id].values())
            for room in rooms:
                await room.destroy("Guild Removed")
            logger.info(
                f"Deleted {len(rooms)} private rooms after leaving guild."
            )

    # Channel delete event handler
    @LionCog.listener('on_guild_channel_delete')
    @log_wrap(action='Destroy Channel Room')
    async def _destroy_channel_room(self, channel: discord.abc.GuildChannel):
        room = self._room_cache[channel.guild.id].get(channel.id, None)
        if room is not None:
            await room.destroy(reason="Underlying Channel Deleted")

    # Setting event handlers
    @LionCog.listener('on_guildset_rooms_category')
    @log_wrap(action='Update Rooms Category')
    async def _update_rooms_category(self, guildid: int, data: Optional[int]):
        """
        Move all active private channels to the new category.

        This shouldn't affect the channel function at all.
        """
        guild = self.bot.get_guild(guildid)
        new_category = guild.get_channel(data) if guild else None
        if new_category:
            tasks = []
            for room in list(self._room_cache[guildid].values()):
                if (channel := room.channel) is not None and channel.category != new_category:
                    tasks.append(channel.edit(category=new_category))
            if tasks:
                try:
                    await asyncio.gather(*tasks)
                except Exception:
                    logger.exception(
                        "Unhandled exception updating private room category."
                    )

    @LionCog.listener('on_guildset_rooms_visible')
    @log_wrap(action='Update Rooms Visibility')
    async def _update_rooms_visibility(self, guildid: int, data: bool):
        """
        Update the everyone override on each room to reflect the new setting.
        """
        tasks = []
        for room in list(self._room_cache[guildid].values()):
            if room.channel:
                tasks.append(
                    room.channel.set_permissions(
                        room.channel.guild.default_role,
                        view_channel=data
                    )
                )
        if tasks:
            try:
                await asyncio.gather(*tasks)
            except Exception:
                logger.exception(
                    "Unhandled exception updating private room visibility!"
                )

    # ----- Room API -----
    @log_wrap(action="Create Room")
    async def create_private_room(self,
                                  guild: discord.Guild, owner: discord.Member,
                                  initial_balance: int, name: str, members: list[discord.Member]
                                  ) -> Room:
        """
        Create a new private room.
        """
        lguild = await self.bot.core.lions.fetch_guild(guild.id)

        # TODO: Consider extending invites to members rather than giving them immediate access
        # Potential for abuse in moderation-free channel a member can add anyone too
        everyone_overwrite = discord.PermissionOverwrite(
            view_channel=lguild.config.get(RoomSettings.Visible.setting_id).value,
            connect=False
        )

        # Build permission overwrites for owner and members, take into account visible setting
        overwrites = {
            owner: owner_overwrite,
            guild.default_role: everyone_overwrite
        }
        for member in members:
            overwrites[member] = member_overwrite

        # Create channel
        channel = await guild.create_voice_channel(
            name=name,
            reason=f"Creating Private Room for {owner.id}",
            category=lguild.config.get(RoomSettings.Category.setting_id).value,
            overwrites=overwrites
        )
        try:
            # Create Room
            now = utc_now()
            data = await self.data.Room.create(
                channelid=channel.id,
                guildid=guild.id,
                ownerid=owner.id,
                coin_balance=initial_balance,
                name=name,
                created_at=now,
                last_tick=now
            )
            if members:
                await self.data.RoomMember.table.insert_many(
                    ('channelid', 'userid'),
                    *((channel.id, member.id) for member in members)
                )
            room = Room(
                self.bot,
                data,
                lguild,
                [member.id for member in members]
            )
            self._start(room)

            # Send tips message
            await channel.send("{mention} welcome to your private room! (TBD TIPS HERE)".format(mention=owner.mention))

            # Send config UI
            ui = RoomUI(self.bot, room, callerid=owner.id, timeout=None)
            await ui.send(channel)
        except Exception:
            try:
                await channel.delete(reason="Failed to created private room")
            except discord.HTTPException:
                pass
            logger.exception(
                "Unhandled exception occurred while trying to create a new private room!"
            )
            raise
        else:
            logger.info(
                f"New private room created: {room.data!r}"
            )

        return room

    async def destroy_private_room(self, room: Room, reason: Optional[str] = None):
        """
        Delete a private room.

        Since this destroys the room, it will automatically remove itself from the running cache.
        """
        await room.destroy(reason=reason)

    def get_channel_room(self, channelid: int) -> Optional[Room]:
        """
        Get a private room if it exists in the given channel.
        """
        channel = self.bot.get_channel(channelid)
        if channel:
            room = self._room_cache[channel.guild.id].get(channelid, None)
            return room

    def get_owned_room(self, guildid: int, userid: int) -> Optional[Room]:
        """
        Get a private room owned by the given member, if it exists.
        """
        return next(
            (room for channel, room in self._room_cache[guildid].items() if room.data.ownerid == userid),
            None
        )

    # ----- Room Commands -----
    @cmds.hybrid_group(
        name=_p('cmd:room', "room"),
        description=_p('cmd:room|desc', "Base command group for private room configuration.")
    )
    @appcmds.guild_only()
    async def room_group(self, ctx: LionContext):
        ...

    @room_group.command(
        name=_p('cmd:room_rent', "rent"),
        description=_p(
            'cmd:room_rent|desc',
            "Rent a private voice channel with LionCoins."
        )
    )
    @appcmds.rename(
        days=_p('cmd:room_rent|param:days', "days"),
        members=_p('cmd:room_rent|param:members', "members"),
        name=_p('cmd:room_rent|param:name', "name"),
    )
    @appcmds.describe(
        days=_p(
            'cmd:room_rent|param:days|desc',
            "Number of days to pre-purchase. (Default: 1)"
        ),
        members=_p(
            'cmd:room_rent|param:members|desc',
            "Mention the members you want to add to your private room."
        ),
        name=_p(
            'cmd:room_rent|param:name|desc',
            "Name of your private voice channel."
        )
    )
    async def room_rent_cmd(self, ctx: LionContext,
                            days: Optional[Range[int, 1, 30]] = 1,
                            members: Optional[str] = None,
                            name: Optional[Range[str, 1, 100]] = None,):
        t = self.bot.translator.t
        if not ctx.guild or not ctx.interaction:
            return

        # Check renting is set up, with permissions
        category: discord.CategoryChannel = ctx.lguild.config.get(RoomSettings.Category.setting_id).value
        if category is None:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:room_rent|error:not_setup',
                        "The private room system has not been set up! "
                        "A private room category needs to be set first with `/configure rooms`."
                    ))
                ), ephemeral=True
            )
            return
        if not category.permissions_for(ctx.guild.me).manage_channels:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:room_rent|error:insufficient_perms',
                        "I do not have enough permissions to create a new channel under "
                        "the configured private room category!"
                    ))
                ), ephemeral=True
            )
            return

        # Check that the author doesn't already own a room
        room = self.get_owned_room(ctx.guild.id, ctx.author.id)
        if room is not None and room.channel:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:room_rent|error:room_exists',
                        "You already own a private room! Click to visit: {channel}"
                    )).format(channel=room.channel.mention)
                ), ephemeral=True
            )
            return

        # Check that provided members actually exist
        memberids = set(parse_members(members)) if members else set()
        memberids.discard(ctx.author.id)
        provided = []
        for mid in memberids:
            member = ctx.guild.get_member(mid)
            if not member:
                try:
                    member = await ctx.guild.fetch_member(mid)
                except discord.HTTPException:
                    await ctx.reply(
                        embed=error_embed(
                            t(_p(
                                'cmd:room_rent|error:member_not_found',
                                "Could not find the requested member {mention} in this server!"
                            )).format(member=f"<@{mid}>")
                        ), ephemeral=True
                    )
                    return
            provided.append(member)

        # Check provided members don't go over cap
        cap = ctx.lguild.config.get(RoomSettings.MemberLimit.setting_id).value
        if len(provided) >= cap:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:room_rent|error:too_many_members',
                        "Too many members! You have requested to add `{count}` members to your room, "
                        "but the maximum private room size is `{cap}`!"
                    )).format(count=len(provided), cap=cap),
                ),
                ephemeral=True
            )
            return

        # Balance checks
        rent = ctx.lguild.config.get(RoomSettings.Rent.setting_id).value
        required = rent * days
        # Purchase confirmation
        confirm_msg = t(_np(
            'cmd:room_rent|confirm:purchase',
            "Are you sure you want to spend {coin}**{required}** to "
            "rent a private room for `one` day?",
            "Are you sure you want to spend {coin}**{required}** to "
            "rent a private room for `{days}` days?",
            days
        )).format(
            coin=self.bot.config.emojis.coin,
            required=required,
            days=days
        )
        confirm = Confirm(confirm_msg, ctx.author.id)
        try:
            result = await confirm.ask(ctx.interaction, ephemeral=True)
        except ResponseTimedOut:
            result = False
        if not result:
            return

        # Positive response. Start a transaction.
        conn = await self.bot.db.get_connection()
        async with conn.transaction():
            # Check member balance is sufficient
            await ctx.alion.data.refresh()
            member_balance = ctx.alion.data.coins
            if member_balance < required:
                await ctx.reply(
                    embed=error_embed(
                        t(_np(
                            'cmd:room_rent|error:insufficient_funds',
                            "Renting a private room for `one` day costs {coin}**{required}**, "
                            "but you only have {coin}**{balance}**!",
                            "Renting a private room for `{days}` days costs {coin}**{required}**, "
                            "but you only have {coin}**{balance}**!",
                            days
                        )).format(
                            coin=self.bot.config.emojis.coin,
                            balance=member_balance,
                            required=required,
                            days=days
                        ),
                        ephemeral=True
                    )
                )
                return

            # Deduct balance
            # TODO: Economy transaction instead of manual deduction
            await ctx.alion.data.update(coins=CoreData.Member.coins - required)

            # Create room with given starting balance and other parameters
            room = await self.create_private_room(
                ctx.guild,
                ctx.author,
                required - rent,
                name or ctx.author.display_name,
                members=provided
            )

            # Ack with confirmation message pointing to the room
            msg = t(_p(
                'cmd:room_rent|success',
                "Successfully created your private room {channel}!"
            )).format(channel=room.channel.mention)
            await ctx.reply(
                embed=discord.Embed(
                    colour=discord.Colour.brand_green(),
                    title=t(_p('cmd:room_rent|success|title', "Private Room Created!")),
                    description=msg
                )
            )

    @room_group.command(
        name=_p('cmd:room_status', "status"),
        description=_p(
            'cmd:room_status|desc',
            "Display the status of your current room."
        )
    )
    async def room_status_cmd(self, ctx: LionContext):
        t = self.bot.translator.t
        if not ctx.guild or not ctx.interaction:
            return

        # Resolve target room
        # Resolve order: Current channel, then owned room
        room = self.get_channel_room(ctx.channel.id)
        if room is None:
            room = self.get_owned_room(ctx.guild.id, ctx.author.id)
        if room is None:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_status|error:no_target',
                    "Could not identify target private room! Please re-run the command "
                    "in the private room you wish to view the status of."
                ))
                ),
                ephemeral=True
            )
            return

        # Respond with room UI
        # Ephemeral UI unless we are in the room
        ui = RoomUI(self.bot, room, callerid=ctx.author.id)
        await ui.run(ctx.interaction, ephemeral=(ctx.channel.id != room.data.channelid))
        await ui.wait()

    @room_group.command(
        name=_p('cmd:room_invite', "invite"),
        description=_p(
            'cmd:room_invite|desc',
            "Add members to your private room."
        )
    )
    @appcmds.rename(
        members=_p('cmd:room_invite|param:members', "members"),
    )
    @appcmds.describe(
        members=_p(
            'cmd:room_invite|param:members|desc',
            "Mention the members you want to add."
        )
    )
    async def room_invite_cmd(self, ctx: LionContext, members: str):
        t = self.bot.translator.t
        if not ctx.guild or not ctx.interaction:
            return

        # Resolve target room
        room = self.get_owned_room(ctx.guild.id, ctx.author.id)
        if room is None:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_invite|error:no_room',
                    "You do not own a private room! Use `/room rent` to rent one with {coin}!"
                )).format(coin=self.bot.config.emojis.coin)),
                ephemeral=True
            )
            return

        # Check that provided members actually exist
        memberids = set(parse_members(members)) if members else set()
        memberids.discard(ctx.author.id)
        memberids.difference_update(room.members)
        provided = []
        for mid in memberids:
            member = ctx.guild.get_member(mid)
            if not member:
                try:
                    member = await ctx.guild.fetch_member(mid)
                except discord.HTTPException:
                    await ctx.reply(
                        embed=error_embed(
                            t(_p(
                                'cmd:room_invite|error:member_not_found',
                                "Could not find the invited member {mention} in this server!"
                            )).format(member=f"<@{mid}>")
                        ), ephemeral=True
                    )
                    return
            provided.append(member)
        if not provided:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:room_invite|error:no_new_members',
                        "All members mentioned are already in the room!"
                    ))
                ),
                ephemeral=True
            )
            return

        # Check provided members don't go over cap
        cap = ctx.lguild.config.get(RoomSettings.MemberLimit.setting_id).value
        if len(room.members) + len(provided) >= cap:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:room_invite|error:too_many_members',
                        "Too many members! You have invited `{count}` new members to your room, "
                        "but you already have `{current}`, "
                        "and the member cap is `{cap}`!"
                    )).format(
                        count=len(provided),
                        current=len(room.members) + 1,
                        cap=cap
                    ),
                ),
                ephemeral=True
            )
            return

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        # Finally, add the members
        await room.add_new_members([m.id for m in provided])

        # And ack
        if ctx.channel.id != room.data.channelid:
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'cmd:room_invite|success|ack',
                    "Members Invited successfully."
                ))
            )
            await ctx.reply(embed=embed)
        else:
            await ctx.interaction.delete_original_response()

    @room_group.command(
        name=_p('cmd:room_kick', "kick"),
        description=_p(
            'cmd:room_kick|desc',
            "Remove a members from your private room."
        )
    )
    @appcmds.rename(
        members=_p('cmd:room_kick|param:members', "members")
    )
    @appcmds.describe(
        members=_p(
            'cmd:room_kick|param:members|desc',
            "Mention the members you want to remove. Also accepts space-separated user ids."
        )
    )
    async def room_kick_cmd(self, ctx: LionContext, members: str):
        t = self.bot.translator.t
        if not ctx.guild or not ctx.interaction:
            return

        # Resolve target room
        room = self.get_owned_room(ctx.guild.id, ctx.author.id)
        if room is None:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_kick|error:no_room',
                    "You do not own a private room! Use `/room rent` to rent one with {coin}!"
                )).format(coin=self.bot.config.emojis.coin)),
                ephemeral=True
            )
            return

        # Only remove members which are actually in the room
        # Also ignore the owner
        memberids = set(parse_members(members)) if members else set()
        if ctx.guild.me.id in memberids:
            await ctx.reply("Ouch, what did I do?")
        memberids.intersection_update(room.members)
        if not memberids:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:room_kick|error:no_matching_members',
                        "None of the mentioned members are in this room!"
                    ))
                ),
                ephemeral=True
            )
            return

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        # Finally, add the members
        await room.rm_members(memberids)

        # And ack
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'cmd:room_kick|success|ack',
                "Members removed."
            ))
        )
        await ctx.reply(embed=embed)

    @room_group.command(
        name=_p('cmd:room_transfer', "transfer"),
        description=_p(
            'cmd:room_transfer|desc',
            "Transfer your private room to another room member. Not reversible!"
        )
    )
    @appcmds.rename(
        new_owner=_p('cmd:room_transfer|param:new_owner', "new_owner")
    )
    @appcmds.describe(
        new_owner=_p(
            'cmd:room_transfer|param:new_owner',
            "The room member you would like to transfer your room to."
        )
    )
    async def room_transfer_cmd(self, ctx: LionContext, new_owner: discord.Member):
        t = self.bot.translator.t
        if not ctx.guild or not ctx.interaction:
            return

        # Resolve target room
        room = self.get_owned_room(ctx.guild.id, ctx.author.id)
        if room is None:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_transfer|error:no_room',
                    "You do not own a private room to transfer!"
                )).format(coin=self.bot.config.emojis.coin)),
                ephemeral=True
            )
            return

        # Check if the target owner is actually a member of the room
        if new_owner.id not in room.members:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:room_transfer|error:target_not_member',
                        "{mention} is not a member of your private room! You must invite them first."
                    )).format(mention=new_owner)
                ), ephemeral=True)
            return

        # Check if target owner already has a room
        new_owner_room = self.get_owned_room(ctx.guild.id, new_owner.id)
        if new_owner_room is not None:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:room_transfer|error:target_has_room',
                        "{mention} already owns a room! Members can only own one room at a time."
                    )).format(mention=new_owner.mention)
                ), ephemeral=True
            )
            return

        # Confirm transfer
        confirm_msg = t(_p(
                'cmd:room_transfer|confirm|question',
                "Are you sure you wish to transfer your private room {channel} to {new_owner}? "
                "This action is not reversible!"
        )).format(channel=room.channel, new_owner=new_owner.mention)
        confirm = Confirm(confirm_msg, ctx.author.id)
        try:
            result = await confirm.ask(ctx.interaction, ephemeral=True)
        except ResponseTimedOut:
            result = False
        if not result:
            return

        # Finally, do the transfer
        await room.transfer_ownership(new_owner)

        # Ack
        await ctx.reply(
            embed=discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:room_transfer|success|description',
                    "You have successfully transferred ownership of {channel} to {new_owner}."
                )).format(channel=room.channel, new_owner=new_owner.mention)
            )
        )

    @room_group.command(
        name=_p('cmd:room_deposit', "deposit"),
        description=_p(
            'cmd:room_deposit|desc',
            "Deposit LionCoins in your private room bank to add more days. (Members may also deposit!)"
        )
    )
    @appcmds.rename(
        coins=_p('cmd:room_deposit|param:coins', "coins")
    )
    @appcmds.describe(
        coins=_p(
            'cmd:room_deposit|param:coins|desc',
            "Number of coins to deposit."
        )
    )
    async def room_deposit_cmd(self, ctx: LionContext, coins: Range[int, 1, MAX_COINS]):
        t = self.bot.translator.t
        if not ctx.guild or not ctx.interaction:
            return

        # All responses will be ephemeral
        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        # Resolve target room
        # Resolve order: Current channel, then owned room
        room = self.get_channel_room(ctx.channel.id)
        if room is None:
            room = self.get_owned_room(ctx.guild.id, ctx.author.id)
        if room is None:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_deposit|error:no_target',
                    "Could not identify target private room! Please re-run the command "
                    "in the private room you wish to contribute to."
                ))
                ),
                ephemeral=True
            )
            return

        # Start Transaction
        conn = await self.bot.db.get_connection()
        async with conn.transaction():
            await ctx.alion.data.refresh()
            member_balance = ctx.alion.data.coins
            if member_balance < coins:
                await ctx.reply(
                    embed=error_embed(t(_p(
                        'cmd:room_deposit|error:insufficient_funds',
                        "You cannot deposit {coin}**{amount}**! You only have {coin}**{balance}**."
                    )).format(
                        coin=self.bot.config.emojis.coin,
                        amount=coins,
                        balance=member_balance
                    )),
                    ephemeral=True
                )
                return

            # Deduct balance
            # TODO: Economy transaction
            await ctx.alion.data.update(coins=CoreData.Member.coins - coins)
            await room.data.update(coin_balance=RoomData.Room.coin_balance + coins)

            # Post deposit message
            await room.notify_deposit(ctx.author, coins)

            # Ack the deposit
            if ctx.channel.id != room.data.channelid:
                ack_msg = t(_p(
                    'cmd:room_depost|success',
                    "Success! You have contributed {coin}**{amount}** to the private room bank."
                )).format(coin=self.bot.config.emojis.coin, amount=coins)
                await ctx.reply(
                    embed=discord.Embed(colour=discord.Colour.brand_green(), description=ack_msg)
                )
            else:
                await ctx.interaction.delete_original_response()

    # ----- Guild Configuration -----
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_commands=False)
    async def configure_group(self, ctx: LionContext):
        ...

    @configure_group.command(
        name=_p('cmd:configure_rooms', "rooms"),
        description=_p('cmd:configure_rooms|desc', "Configure Rented Private Rooms")
    )
    @appcmds.rename(
        **{setting.setting_id: setting._display_name for setting in RoomSettings.model_settings}
    )
    @appcmds.describe(
        **{setting.setting_id: setting._desc for setting in RoomSettings.model_settings}
    )
    @cmds.check(low_management)
    async def configure_rooms_cmd(self, ctx: LionContext,
                                  rooms_category: Optional[discord.CategoryChannel] = None,
                                  rooms_price: Optional[Range[int, 0, MAX_COINS]] = None,
                                  rooms_slots: Optional[Range[int, 1, MAX_COINS]] = None,
                                  rooms_visible: Optional[bool] = None):
        # t = self.bot.translator.t

        # Type checking guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # TODO: Value verification on the category channel for permissions
        await ctx.interaction.response.defer(thinking=True)

        provided = {
            'rooms_category': rooms_category,
            'rooms_price': rooms_price,
            'rooms_slots': rooms_slots,
            'rooms_visible': rooms_visible
        }
        modified = {(sid, val) for sid, val in provided.items() if val is not None}
        if modified:
            lines = []
            update_args = {}
            settings = []
            for setting_id, value in modified:
                setting = ctx.lguild.config.get(setting_id)
                setting.value = value
                settings.append(setting)
                update_args[setting._column] = setting._data
                lines.append(setting.update_message)

            # Data update
            await ctx.lguild.data.update(**update_args)
            for setting in settings:
                setting.dispatch_update()

            # Ack modified
            tick = self.bot.config.emojis.tick
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description='\n'.join(f"{tick} {line}" for line in lines)
            )
            await ctx.reply(embed=embed)

        if ctx.channel.id not in RoomSettingUI._listening or not modified:
            ui = RoomSettingUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()

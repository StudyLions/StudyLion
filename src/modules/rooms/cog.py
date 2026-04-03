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

from wards import high_management_ward

from . import babel, logger
from .data import RoomData
from .settings import RoomSettings
from .settingui import RoomSettingUI
from .room import Room
# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Import dashboard URL constants for link buttons in room messages
from .lib import ROOM_DASHBOARD_URL, ROOM_ADMIN_URL_TEMPLATE
# --- END AI-MODIFIED ---
from .roomui import RoomUI
# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Import mod_role_overwrite for room moderator role feature
from .lib import parse_members, owner_overwrite, member_overwrite, bot_overwrite, mod_role_overwrite
# --- END AI-MODIFIED ---

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

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Register ListData-based role gate settings (separate tables, not guild_config columns)
        for setting in self.settings.list_settings:
            self.bot.core.guild_config.register_setting(setting)
        # --- END AI-MODIFIED ---

        configcog = self.bot.get_cog('ConfigCog')
        self.crossload_group(self.configure_group, configcog.admin_config_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        # Cancel room tick loops
        for task in self._ticker_tasks.values():
            task.cancel()

    def get_rooms(self, guildid: int, userid: Optional[int] = None):
        """
        Get the private rooms in the given guild, using cache.

        If `userid` is provided, filters by rooms which the given user is a member or owner of.
        """
        guild_rooms = self._room_cache[guildid]
        if userid:
            rooms = {
                cid: room for cid, room in guild_rooms.items() if userid in room.members or userid == room.data.ownerid
            }
        else:
            rooms = guild_rooms
        return rooms

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Count rooms owned by a user (for max_per_user enforcement)
    def count_owned_rooms(self, guildid: int, userid: int) -> int:
        return sum(
            1 for room in self._room_cache[guildid].values()
            if room.data.ownerid == userid
        )
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Check cooldown — returns remaining seconds, or 0 if no cooldown active
    async def get_cooldown_remaining(self, guildid: int, userid: int, cooldown_minutes: int) -> int:
        if not cooldown_minutes:
            return 0
        from datetime import timedelta
        rows = await self.data.Room.table.select_where(
            guildid=guildid, ownerid=userid
        ).with_no_cache().order_by('deleted_at', ORDER='DESC').limit(1)
        if not rows:
            return 0
        last_deleted = rows[0]['deleted_at']
        if last_deleted is None:
            return 0
        now = utc_now()
        cooldown_end = last_deleted + timedelta(minutes=cooldown_minutes)
        remaining = (cooldown_end - now).total_seconds()
        return max(0, int(remaining))
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Check whether a member satisfies the room rent role gate (required + any-of roles)
    async def check_rent_role_gate(self, guild: 'discord.Guild', member: 'discord.Member'):
        """
        Check if the member passes the role gate for room renting.

        Returns (allowed: bool, error_message: str | None).
        Gracefully handles deleted roles by filtering them out.
        If all roles in a list are deleted/gone, treats it as "not configured".
        """
        t = self.bot.translator.t
        member_role_ids = {r.id for r in member.roles}

        required_setting = await RoomSettings.RentRequiredRoles.get(guild.id)
        required_data = required_setting.data if required_setting.data else []
        required_roles = [guild.get_role(rid) for rid in required_data]
        required_roles = [r for r in required_roles if r is not None]

        anyof_setting = await RoomSettings.RentAnyOfRoles.get(guild.id)
        anyof_data = anyof_setting.data if anyof_setting.data else []
        anyof_roles = [guild.get_role(rid) for rid in anyof_data]
        anyof_roles = [r for r in anyof_roles if r is not None]

        missing_required = [r for r in required_roles if r.id not in member_role_ids]
        if required_roles and missing_required:
            role_names = ', '.join(f"**{r.name}**" for r in missing_required)
            msg = t(_p(
                'cmd:room_rent|error:missing_required_roles',
                "You need the following role(s) to rent a room: {roles}"
            )).format(roles=role_names)
            if anyof_roles:
                anyof_names = ', '.join(f"**{r.name}**" for r in anyof_roles)
                msg += '\n' + t(_p(
                    'cmd:room_rent|error:missing_required_roles:also_need_anyof',
                    "You also need at least one of: {roles}"
                )).format(roles=anyof_names)
            return False, msg

        if anyof_roles:
            has_any = any(r.id in member_role_ids for r in anyof_roles)
            if not has_any:
                anyof_names = ', '.join(f"**{r.name}**" for r in anyof_roles)
                msg = t(_p(
                    'cmd:room_rent|error:missing_anyof_roles',
                    "You need at least one of the following roles to rent a room: {roles}"
                )).format(roles=anyof_names)
                return False, msg

        return True, None
    # --- END AI-MODIFIED ---

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
            t = self.bot.translator.t
            room.lguild.log_event(
                title=t(_p(
                    'room|eventlog|event:room_deleted|title',
                    "Private Room Deleted"
                )),
                description=t(_p(
                    'room|eventlog|event:room_deleted|desc',
                    "{owner}'s private room was deleted."
                )).format(
                    owner="<@{mid}>".format(mid=room.data.ownerid),
                ),
                fields=room.eventlog_fields()
            )
            await room.destroy(reason="Underlying Channel Deleted")

    # Setting event handlers
    @LionCog.listener('on_guildset_rooms_category')
    @log_wrap(action='Update Rooms Category')
    async def _update_rooms_category(self, guildid: int, setting: RoomSettings.Category):
        """
        Move all active private channels to the new category.

        This shouldn't affect the channel function at all.
        """
        data = setting.data
        guild = self.bot.get_guild(guildid)
        new_category = guild.get_channel(data) if guild and data else None
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
    async def _update_rooms_visibility(self, guildid: int, setting: RoomSettings.Visible):
        """
        Update the everyone override on each room to reflect the new setting.
        """
        data = setting.data
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

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Update all active rooms when the room moderator role setting changes
    @LionCog.listener('on_guildset_rooms_role')
    @log_wrap(action='Update Rooms Moderator Role')
    async def _update_rooms_role(self, guildid: int, setting: RoomSettings.RentingRole):
        """
        Update the mod role override on each room when the renting_role setting changes.
        Detects old mod role overwrites by matching the mod_role_overwrite permission pair,
        removes them, and adds the new role's overwrite if set.
        """
        new_role_id = setting.data
        guild = self.bot.get_guild(guildid)
        if not guild:
            return

        new_role = guild.get_role(new_role_id) if new_role_id else None
        expected_pair = mod_role_overwrite.pair()

        tasks = []
        for room in list(self._room_cache[guildid].values()):
            if not room.channel:
                continue
            for target, ow in room.channel.overwrites.items():
                if not isinstance(target, discord.Role):
                    continue
                if target == guild.default_role:
                    continue
                if new_role and target.id == new_role.id:
                    continue
                if ow.pair() == expected_pair:
                    tasks.append(
                        room.channel.set_permissions(target, overwrite=None)
                    )
            if new_role:
                tasks.append(
                    room.channel.set_permissions(new_role, overwrite=mod_role_overwrite)
                )
        if tasks:
            try:
                await asyncio.gather(*tasks)
            except Exception:
                logger.exception(
                    "Unhandled exception updating private room moderator role!"
                )
    # --- END AI-MODIFIED ---

    # ----- Room API -----
    @log_wrap(action="Create Room")
    async def create_private_room(self,
                                  guild: discord.Guild, owner: discord.Member,
                                  initial_balance: int, name: str, members: list[discord.Member]
                                  ) -> Room:
        """
        Create a new private room.
        """
        t = self.bot.translator.t
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
            guild.default_role: everyone_overwrite,
            guild.me: bot_overwrite,
        }
        for member in members:
            overwrites[member] = member_overwrite

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Add room moderator role overwrite if configured
        renting_role_id = lguild.config.get(RoomSettings.RentingRole.setting_id).data
        if renting_role_id:
            renting_role = guild.get_role(renting_role_id)
            if renting_role:
                overwrites[renting_role] = mod_role_overwrite
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Copy category permission overwrites when sync_perms is enabled
        if lguild.config.get(RoomSettings.SyncPerms.setting_id).value:
            category = lguild.config.get(RoomSettings.Category.setting_id).value
            if category:
                for target, ow in category.overwrites.items():
                    if target not in overwrites:
                        overwrites[target] = ow
        # --- END AI-MODIFIED ---

        # Create channel
        try:
            channel = await guild.create_voice_channel(
                name=name,
                reason=t(_p(
                    'create_room|create_channel|audit_reason',
                    "Creating Private Room for {ownerid}"
                )).format(ownerid=owner.id),
                category=lguild.config.get(RoomSettings.Category.setting_id).value,
                overwrites=overwrites
            )
        except discord.HTTPException as e:
            lguild.log_event(
                t(_p(
                    'eventlog|event:private_room_create_error|name',
                    "Private Room Creation Failed"
                )),
                t(_p(
                    'eventlog|event:private_room_create_error|desc',
                    "{owner} attempted to rent a new private room, but I could not create it!\n"
                    "They were not charged."
                )).format(owner=owner.mention),
                errors=[f"`{repr(e)}`"]
            )
            raise

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
            lguild.log_event(
                t(_p(
                    'eventlog|event:private_room_create|name',
                    "Private Room Rented"
                )),
                t(_p(
                    'eventlog|event:private_room_create|desc',
                    "{owner} has rented a new private room {channel}!"
                )).format(owner=owner.mention, channel=channel.mention),
                fields=room.eventlog_fields(),
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
                        "A private room category needs to be set first with `/admin config rooms`."
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

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Check role gate before other checks so users get the most relevant error first
        allowed, role_error = await self.check_rent_role_gate(ctx.guild, ctx.author)
        if not allowed:
            await ctx.reply(embed=error_embed(role_error), ephemeral=True)
            return
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Replace single-room check with count-based check using max_per_user setting
        max_rooms = ctx.lguild.config.get(RoomSettings.MaxPerUser.setting_id).value
        owned_count = self.count_owned_rooms(ctx.guild.id, ctx.author.id)
        if owned_count >= max_rooms:
            existing = self.get_owned_room(ctx.guild.id, ctx.author.id)
            channel_note = ""
            if existing and existing.channel:
                channel_note = " " + t(_p(
                    'cmd:room_rent|error:room_exists:visit',
                    "Click to visit: {channel}"
                )).format(channel=existing.channel.mention)
            if max_rooms == 1:
                msg = t(_p(
                    'cmd:room_rent|error:room_exists',
                    "You already own a private room!{visit}"
                )).format(visit=channel_note)
            else:
                msg = t(_p(
                    'cmd:room_rent|error:max_rooms',
                    "You already own **{count}** room(s), which is the maximum allowed!{visit}"
                )).format(count=owned_count, visit=channel_note)
            await ctx.reply(embed=error_embed(msg), ephemeral=True)
            return
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Validate room name against the admin-configured name_limit setting
        if name:
            name_limit = ctx.lguild.config.get(RoomSettings.NameLimit.setting_id).value
            if len(name) > name_limit:
                await ctx.reply(
                    embed=error_embed(
                        t(_p(
                            'cmd:room_rent|error:name_too_long',
                            "Room name is too long! Maximum length is **{limit}** characters, "
                            "but yours is **{length}**."
                        )).format(limit=name_limit, length=len(name))
                    ), ephemeral=True
                )
                return
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Enforce creation cooldown after a room expires/is deleted
        cooldown_minutes = ctx.lguild.config.get(RoomSettings.Cooldown.setting_id).value
        if cooldown_minutes:
            remaining = await self.get_cooldown_remaining(ctx.guild.id, ctx.author.id, cooldown_minutes)
            if remaining > 0:
                mins_left = remaining // 60
                secs_left = remaining % 60
                if mins_left > 0:
                    time_str = f"**{mins_left}** minute(s)"
                else:
                    time_str = f"**{secs_left}** second(s)"
                await ctx.reply(
                    embed=error_embed(
                        t(_p(
                            'cmd:room_rent|error:cooldown',
                            "You must wait {time} before renting a new room!"
                        )).format(time=time_str)
                    ), ephemeral=True
                )
                return
        # --- END AI-MODIFIED ---

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
                            )).format(mention=f"<@{mid}>")
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
        room = await self._do_create_room(ctx, required, days, rent, name, provided)

        if room:
            # Ack with confirmation message pointing to the room
            msg = t(_p(
                'cmd:room_rent|success',
                "Successfully created your private room {channel}!"
            )).format(channel=room.channel.mention)
            # --- AI-MODIFIED (2026-03-22) ---
            # Purpose: Add "Manage Room" dashboard link button to rent success
            link_view = discord.ui.View()
            link_view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=ROOM_DASHBOARD_URL,
                label="Manage Room"
            ))
            # --- END AI-MODIFIED ---
            # --- AI-MODIFIED (2026-03-22) ---
            # --- Original code (commented out for rollback) ---
            # await ctx.reply(
            #     embed=discord.Embed(
            #         colour=discord.Colour.brand_green(),
            #         title=t(_p('cmd:room_rent|success|title', "Private Room Created!")),
            #         description=msg
            #     )
            # )
            # --- End original code ---
            await ctx.reply(
                embed=discord.Embed(
                    colour=discord.Colour.brand_green(),
                    title=t(_p('cmd:room_rent|success|title', "Private Room Created!")),
                    description=msg
                ),
                view=link_view
            )
            # --- END AI-MODIFIED ---
            self._start(room)

            # Send tips message
            tips = (
                "Welcome to your very own private room {owner}!\n"
                "You may use the control panel below to quickly configure your room, including:\n"
                "- Inviting (and removing) members,\n"
                "- Depositing LionCoins into the room bank to pay the daily rent, and\n"
                "- Adding your very own Pomodoro timer to the room.\n\n"
                "You also have elevated Discord permissions over the room itself!\n"
                "This includes managing messages, and changing the name, region,"
                " and bitrate of the channel, or even deleting the room entirely!"
                " (Beware you will not be refunded in this case.)\n\n"
                "Finally, you now have access to some new commands:\n"
                "{status_cmd}: This brings up the room control panel again,"
                " in case the interface below times out or is deleted/hidden.\n"
                "{deposit_cmd}:  Room members may use this command to easily contribute LionCoins to the room bank.\n"
                "{invite_cmd} and {kick_cmd}: Quickly invite (or remove) multiple members by mentioning them.\n"
                "{transfer_cmd}: Transfer the room to another owner, keeping the balance (this is not reversible!)"
            ).format(
                owner=ctx.author.mention,
                status_cmd=self.bot.core.mention_cmd('room status'),
                deposit_cmd=self.bot.core.mention_cmd('room deposit'),
                invite_cmd=self.bot.core.mention_cmd('room invite'),
                kick_cmd=self.bot.core.mention_cmd('room kick'),
                transfer_cmd=self.bot.core.mention_cmd('room transfer'),
            )
            await room.channel.send(tips)

            # Send config UI
            ui = RoomUI(self.bot, room, callerid=ctx.author.id, timeout=None)
            await ui.send(room.channel)

    @log_wrap(action='create_room')
    async def _do_create_room(self, ctx, required, days, rent, name, provided) -> Optional[Room]:
        t = self.bot.translator.t
        # TODO: Rollback the channel create if this fails
        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            # Note that the room creation will go into the UI as well.
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
                try:
                    return await self.create_private_room(
                        ctx.guild,
                        ctx.author,
                        required - rent,
                        name or ctx.author.display_name,
                        members=provided
                    )
                except discord.Forbidden:
                    await ctx.reply(
                        embed=error_embed(
                            t(_p(
                                'cmd:room_rent|error:my_permissions',
                                "Could not create your private room! You were not charged.\n"
                                "I have insufficient permissions to create a private room channel."
                            )),
                        )
                    )
                    await ctx.alion.data.update(coins=CoreData.Member.coins + required)
                except discord.HTTPException as e:
                    await ctx.reply(
                        embed=error_embed(
                            t(_p(
                                'cmd:room_rent|error:unknown',
                                "Could not create your private room! You were not charged.\n"
                                "An unknown error occurred while creating your private room.\n"
                                "`{error}`"
                            )).format(error=e.text),
                        )
                    )
                    await ctx.alion.data.update(coins=CoreData.Member.coins + required)

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
                            )).format(mention=f"<@{mid}>")
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
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Add "Manage Room" dashboard link button to invite success
        if ctx.channel.id != room.data.channelid:
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'cmd:room_invite|success|ack',
                    "Members Invited successfully."
                ))
            )
            link_view = discord.ui.View()
            link_view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=ROOM_DASHBOARD_URL,
                label="Manage Room"
            ))
            await ctx.reply(embed=embed, view=link_view)
        else:
            await ctx.interaction.delete_original_response()
        # --- END AI-MODIFIED ---

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
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Add "Manage Room" dashboard link button to kick success
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'cmd:room_kick|success|ack',
                "Members removed."
            ))
        )
        link_view = discord.ui.View()
        link_view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            url=ROOM_DASHBOARD_URL,
            label="Manage Room"
        ))
        await ctx.reply(embed=embed, view=link_view)
        # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-03) ---
    # Purpose: Let non-owner members voluntarily leave a private room
    @room_group.command(
        name=_p('cmd:room_leave', "leave"),
        description=_p(
            'cmd:room_leave|desc',
            "Leave a private room you are a member of."
        )
    )
    async def room_leave_cmd(self, ctx: LionContext):
        t = self.bot.translator.t
        if not ctx.guild or not ctx.interaction:
            return

        room = self.get_channel_room(ctx.channel.id)
        if room is None:
            for r in self._room_cache[ctx.guild.id].values():
                if ctx.author.id in r.members:
                    room = r
                    break

        if room is None:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_leave|error:no_room',
                    "You are not a member of any private room in this server! "
                    "Run this command inside the room you wish to leave."
                ))),
                ephemeral=True
            )
            return

        if ctx.author.id == room.data.ownerid:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_leave|error:is_owner',
                    "You are the owner of this room! "
                    "Use {delete_cmd} to close the room, or {transfer_cmd} to transfer ownership first."
                )).format(
                    delete_cmd=self.bot.core.mention_cmd('room delete'),
                    transfer_cmd=self.bot.core.mention_cmd('room transfer'),
                )),
                ephemeral=True
            )
            return

        if ctx.author.id not in room.members:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_leave|error:not_member',
                    "You are not a member of this private room!"
                ))),
                ephemeral=True
            )
            return

        confirm_msg = t(_p(
            'cmd:room_leave|confirm',
            "Are you sure you want to leave {channel}? "
            "You will lose access until the owner invites you back."
        )).format(channel=room.channel.mention if room.channel else "this room")
        confirm = Confirm(confirm_msg, ctx.author.id)
        try:
            result = await confirm.ask(ctx.interaction, ephemeral=True)
        except ResponseTimedOut:
            result = False
        if not result:
            return

        await room.leave_member(ctx.author.id)

        await ctx.reply(
            embed=discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:room_leave|success',
                    "You have left the private room."
                ))
            ),
            ephemeral=True
        )
    # --- END AI-MODIFIED ---

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
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Add "Manage Room" dashboard link button to transfer success
        link_view = discord.ui.View()
        link_view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            url=ROOM_DASHBOARD_URL,
            label="Manage Room"
        ))
        await ctx.reply(
            embed=discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:room_transfer|success|description',
                    "You have successfully transferred ownership of {channel} to {new_owner}."
                )).format(channel=room.channel, new_owner=new_owner.mention)
            ),
            view=link_view
        )
        # --- END AI-MODIFIED ---

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

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Enforce minimum deposit amount from admin setting
        min_deposit = ctx.lguild.config.get(RoomSettings.MinDeposit.setting_id).value
        if min_deposit and coins < min_deposit:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_deposit|error:below_minimum',
                    "The minimum deposit is {coin}**{minimum}**! "
                    "You tried to deposit {coin}**{amount}**."
                )).format(
                    coin=self.bot.config.emojis.coin,
                    minimum=min_deposit,
                    amount=coins
                )),
                ephemeral=True
            )
            return
        # --- END AI-MODIFIED ---

        # Start Transaction
        # TODO: Economy transaction
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
        await ctx.alion.data.update(coins=CoreData.Member.coins - coins)
        await room.data.update(coin_balance=RoomData.Room.coin_balance + coins)

        # Post deposit message
        await room.notify_deposit(ctx.author, coins)

        # Ack the deposit
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Add "View Room" dashboard link button to deposit success
        if ctx.channel.id != room.data.channelid:
            ack_msg = t(_p(
                'cmd:room_depost|success',
                "Success! You have contributed {coin}**{amount}** to the private room bank."
            )).format(coin=self.bot.config.emojis.coin, amount=coins)
            link_view = discord.ui.View()
            link_view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=ROOM_DASHBOARD_URL,
                label="View Room"
            ))
            await ctx.reply(
                embed=discord.Embed(colour=discord.Colour.brand_green(), description=ack_msg),
                view=link_view
            )
        else:
            await ctx.interaction.delete_original_response()
        # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: /room sound command — rent an available ambient sound bot to a private room
    SOUND_CHOICES = [
        appcmds.Choice(name="Rain", value="rain"),
        appcmds.Choice(name="Campfire", value="campfire"),
        appcmds.Choice(name="Ocean Waves", value="ocean"),
        appcmds.Choice(name="Brown Noise", value="brown_noise"),
        appcmds.Choice(name="White Noise", value="white_noise"),
        appcmds.Choice(name="LoFi", value="lofi"),
    ]

    @room_group.command(
        name=_p('cmd:room_sound', "sound"),
        description=_p(
            'cmd:room_sound|desc',
            "Rent an ambient sound bot for your private room (costs LionCoins per hour)."
        )
    )
    @appcmds.describe(
        sound=_p('cmd:room_sound|param:sound', "The ambient sound to play"),
        hours=_p('cmd:room_sound|param:hours', "How many hours to rent (1–24)"),
    )
    @appcmds.choices(sound=SOUND_CHOICES)
    async def room_sound_cmd(
        self, ctx: LionContext,
        sound: appcmds.Choice[str],
        hours: Range[int, 1, 24] = 1,
    ):
        t = self.bot.translator.t
        if not ctx.guild or not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        room = self.get_channel_room(ctx.channel.id)
        if room is None:
            room = self.get_owned_room(ctx.guild.id, ctx.author.id)
        if room is None:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_sound|error:no_room',
                    "You don't have a private room! Use `/room rent` to create one first."
                ))),
                ephemeral=True,
            )
            return

        guild_id = ctx.guild.id

        async with self.bot.db.connection() as conn:
            async with conn.cursor() as cur:
                # Check if rental feature is enabled for this guild
                await cur.execute(
                    "SELECT room_rental_enabled, room_rental_hourly_rate "
                    "FROM ambient_sounds_guild_config WHERE guildid = %s",
                    [guild_id],
                )
                rental_cfg = await cur.fetchone()

            if not rental_cfg or not rental_cfg['room_rental_enabled']:
                await ctx.reply(
                    embed=error_embed(t(_p(
                        'cmd:room_sound|error:not_enabled',
                        "Sound bot rentals are not enabled in this server. "
                        "Ask an admin to enable it in the dashboard."
                    ))),
                    ephemeral=True,
                )
                return

            hourly_rate = rental_cfg['room_rental_hourly_rate']
            total_cost = hourly_rate * hours

            async with conn.cursor() as cur:
                # Check if room already has an active rental
                await cur.execute(
                    "SELECT rental_id FROM ambient_sounds_rentals "
                    "WHERE guildid = %s AND channelid = %s AND ended_at IS NULL AND expires_at > NOW()",
                    [guild_id, room.data.channelid],
                )
                existing = await cur.fetchone()

            if existing:
                await ctx.reply(
                    embed=error_embed(t(_p(
                        'cmd:room_sound|error:already_rented',
                        "This room already has an active sound bot rental!"
                    ))),
                    ephemeral=True,
                )
                return

            async with conn.cursor() as cur:
                # Find an available bot (not currently configured or rented in this guild)
                await cur.execute(
                    "SELECT DISTINCT bot_number FROM ("
                    "  SELECT bot_number FROM ambient_sounds_config "
                    "  WHERE guildid = %s AND enabled = true AND channelid IS NOT NULL "
                    "  UNION ALL "
                    "  SELECT bot_number FROM ambient_sounds_rentals "
                    "  WHERE guildid = %s AND ended_at IS NULL AND expires_at > NOW()"
                    ") sub",
                    [guild_id, guild_id],
                )
                busy_bots = await cur.fetchall()

            busy_set = {r['bot_number'] for r in busy_bots}
            available = [n for n in range(1, 6) if n not in busy_set]

            if not available:
                await ctx.reply(
                    embed=error_embed(t(_p(
                        'cmd:room_sound|error:no_bots',
                        "All 5 sound bots are currently in use in this server. "
                        "Try again later when one becomes available."
                    ))),
                    ephemeral=True,
                )
                return

            bot_number = available[0]
            coin_emoji = self.bot.config.emojis.coin

            # Confirm with the user
            confirm_embed = discord.Embed(
                colour=discord.Colour.gold(),
                title="Rent Sound Bot",
                description=(
                    f"**Sound:** {sound.name}\n"
                    f"**Duration:** {hours} hour{'s' if hours > 1 else ''}\n"
                    f"**Cost:** {coin_emoji}**{total_cost}** ({coin_emoji}{hourly_rate}/hr)\n"
                    f"**Bot:** Sound Bot #{bot_number}\n\n"
                    f"The bot will join your room and play this sound."
                ),
            )
            confirm = Confirm(ctx.author.id)
            confirm_msg = await ctx.reply(embed=confirm_embed, view=confirm, ephemeral=True)
            await confirm.wait()

            if not confirm.result:
                try:
                    await confirm_msg.edit(
                        embed=discord.Embed(
                            colour=discord.Colour.dark_grey(),
                            description="Rental cancelled.",
                        ),
                        view=None,
                    )
                except Exception:
                    pass
                return

            # Deduct coins
            await ctx.alion.data.refresh()
            member_balance = ctx.alion.data.coins
            if member_balance < total_cost:
                await confirm_msg.edit(
                    embed=error_embed(t(_p(
                        'cmd:room_sound|error:insufficient_funds',
                        "You don't have enough LionCoins! "
                        "You need {coin}**{cost}** but only have {coin}**{balance}**."
                    )).format(coin=coin_emoji, cost=total_cost, balance=member_balance)),
                    view=None,
                )
                return

            await ctx.alion.data.update(coins=CoreData.Member.coins - total_cost)

            # Create rental row
            try:
                await conn.execute(
                    "INSERT INTO ambient_sounds_rentals "
                    "(guildid, channelid, userid, bot_number, sound_type, volume, "
                    " expires_at, total_cost) "
                    "VALUES (%s, %s, %s, %s, %s, 50, NOW() + INTERVAL '%s hours', %s)",
                    [guild_id, room.data.channelid, ctx.author.id, bot_number,
                     sound.value, hours, total_cost],
                )
            except Exception as exc:
                # Refund on failure
                await ctx.alion.data.update(coins=CoreData.Member.coins + total_cost)
                await confirm_msg.edit(
                    embed=error_embed(
                        f"Failed to create rental: {str(exc)[:100]}"
                    ),
                    view=None,
                )
                return

            await confirm_msg.edit(
                embed=discord.Embed(
                    colour=discord.Colour.brand_green(),
                    title="Sound Bot Rented!",
                    description=(
                        f"**{sound.name}** will start playing in your room shortly.\n"
                        f"Sound Bot #{bot_number} will connect within a minute.\n\n"
                        f"Duration: **{hours}h** • Cost: {coin_emoji}**{total_cost}**"
                    ),
                ),
                view=None,
            )
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Add /room delete command so owners can close their own rooms and get a coin refund
    @room_group.command(
        name=_p('cmd:room_delete', "delete"),
        description=_p(
            'cmd:room_delete|desc',
            "Permanently close your private room. Remaining balance is refunded."
        )
    )
    async def room_delete_cmd(self, ctx: LionContext):
        t = self.bot.translator.t
        if not ctx.guild or not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        room = self.get_owned_room(ctx.guild.id, ctx.author.id)
        if room is None:
            await ctx.reply(
                embed=error_embed(t(_p(
                    'cmd:room_delete|error:no_room',
                    "You don't own a private room in this server!"
                ))),
                ephemeral=True
            )
            return

        balance = room.data.coin_balance
        coin = self.bot.config.emojis.coin

        confirm_embed = discord.Embed(
            colour=discord.Colour.brand_red(),
            title=t(_p(
                'cmd:room_delete|confirm|title',
                "Delete Private Room?"
            )),
            description=t(_p(
                'cmd:room_delete|confirm|desc',
                "Are you sure you want to permanently close your private room?\n\n"
                "**This cannot be undone.** The voice channel will be deleted "
                "and all members will lose access.\n\n"
                "Remaining balance: {coin}**{balance}** (will be refunded to you)"
            )).format(coin=coin, balance=balance)
        )
        try:
            result = await Confirm(confirm_embed, ephemeral=True).ask(
                ctx.interaction.followup.send, args=(ctx.author.id,), timeout=30
            )
        except ResponseTimedOut:
            return

        if not result:
            return

        if balance > 0:
            await ctx.alion.data.update(coins=CoreData.Member.coins + balance)

        room.lguild.log_event(
            title=t(_p(
                'room|eventlog|event:room_owner_deleted|title',
                "Private Room Closed by Owner"
            )),
            description=t(_p(
                'room|eventlog|event:room_owner_deleted|desc',
                "{owner} closed their private room. {coin}**{balance}** was refunded."
            )).format(
                owner=f"<@{ctx.author.id}>",
                coin=coin,
                balance=balance,
            ),
            fields=room.eventlog_fields()
        )

        await room.destroy(reason="Owner deleted room")

        await ctx.reply(
            embed=discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:room_delete|success',
                    "Your private room has been closed.{refund_msg}"
                )).format(
                    refund_msg=(
                        " " + t(_p(
                            'cmd:room_delete|success:refund',
                            "{coin}**{balance}** has been refunded to your wallet."
                        )).format(coin=coin, balance=balance)
                        if balance > 0 else ""
                    )
                )
            ),
            ephemeral=True
        )
    # --- END AI-MODIFIED ---

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
    @high_management_ward
    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Add all room setting parameters including 6 newly-wired settings
    async def configure_rooms_cmd(self, ctx: LionContext,
                                  rooms_category: Optional[discord.CategoryChannel] = None,
                                  rooms_price: Optional[Range[int, 0, MAX_COINS]] = None,
                                  rooms_slots: Optional[Range[int, 1, MAX_COINS]] = None,
                                  rooms_visible: Optional[bool] = None,
                                  rooms_role: Optional[discord.Role] = None,
                                  rooms_sync_perms: Optional[bool] = None,
                                  rooms_max_per_user: Optional[Range[int, 1, 100]] = None,
                                  rooms_name_limit: Optional[Range[int, 1, 100]] = None,
                                  rooms_min_deposit: Optional[Range[int, 0, MAX_COINS]] = None,
                                  rooms_auto_extend: Optional[bool] = None,
                                  rooms_cooldown: Optional[Range[int, 0, 10080]] = None):
    # --- END AI-MODIFIED ---
        # t = self.bot.translator.t

        # Type checking guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # TODO: Value verification on the category channel for permissions
        await ctx.interaction.response.defer(thinking=True)

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Include all room settings in the provided dict
        provided = {
            'rooms_category': rooms_category,
            'rooms_price': rooms_price,
            'rooms_slots': rooms_slots,
            'rooms_visible': rooms_visible,
            'rooms_role': rooms_role,
            'rooms_sync_perms': rooms_sync_perms,
            'rooms_max_per_user': rooms_max_per_user,
            'rooms_name_limit': rooms_name_limit,
            'rooms_min_deposit': rooms_min_deposit,
            'rooms_auto_extend': rooms_auto_extend,
            'rooms_cooldown': rooms_cooldown,
        }
        # --- END AI-MODIFIED ---
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
            # --- AI-MODIFIED (2026-03-22) ---
            # Purpose: Add "Room Admin Panel" dashboard link button to config response
            admin_url = ROOM_ADMIN_URL_TEMPLATE.format(guild_id=ctx.guild.id)
            link_view = discord.ui.View()
            link_view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=admin_url,
                label="Room Admin Panel"
            ))
            await ctx.reply(embed=embed, view=link_view)
            # --- END AI-MODIFIED ---

        if ctx.channel.id not in RoomSettingUI._listening or not modified:
            ui = RoomSettingUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()

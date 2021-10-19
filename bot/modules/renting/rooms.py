import discord
import asyncio
import datetime

from cmdClient.lib import SafeCancellation

from meta import client
from settings import GuildSettings

from .data import rented, rented_members
from .module import module


class Room:
    __slots__ = ('key', 'map_key', '_task')

    everyone_overwrite = discord.PermissionOverwrite(
        view_channel=False
    )
    owner_overwrite = discord.PermissionOverwrite(
        view_channel=True,
        connect=True,
        priority_speaker=True
    )
    member_overwrite = discord.PermissionOverwrite(
        view_channel=True,
        connect=True,
    )

    _table = rented

    _rooms = {}  # map (guildid, userid) -> Room

    def __init__(self, channelid):
        self.key = channelid
        self.map_key = (self.data.guildid, self.data.ownerid)

        self._task = None

    @classmethod
    async def create(cls, owner: discord.Member, initial_members):
        ownerid = owner.id
        guild = owner.guild
        guildid = guild.id
        guild_settings = GuildSettings(guildid)

        category = guild_settings.rent_category.value
        if not category:
            # This should never happen
            return SafeCancellation("Rent category not set up!")

        # First create the channel, with the needed overrides
        overwrites = {
            guild.default_role: cls.everyone_overwrite,
            owner: cls.owner_overwrite
        }
        overwrites.update(
            {member: cls.member_overwrite for member in initial_members}
        )
        try:
            channel = await guild.create_voice_channel(
                name="{}'s private channel".format(owner.name),
                overwrites=overwrites,
                category=category
            )
            channelid = channel.id
        except discord.HTTPException:
            guild_settings.event_log.log(
                description="Failed to create a private room for {}!".format(owner.mention),
                colour=discord.Colour.red()
            )
            raise SafeCancellation("Couldn't create the private channel! Please try again later.")

        # Add the new room to data
        cls._table.create_row(
            channelid=channelid,
            guildid=guildid,
            ownerid=ownerid
        )

        # Add the members to data, if any
        if initial_members:
            rented_members.insert_many(
                *((channelid, member.id) for member in initial_members)
            )

        # Log the creation
        guild_settings.event_log.log(
            title="New private study room!",
            description="Created a private study room for {} with:\n{}".format(
                owner.mention,
                ', '.join(member.mention for member in initial_members)
            )
        )

        # Create the room, schedule its expiry, and return
        room = cls(channelid)
        room.schedule()
        return room

    @classmethod
    def fetch(cls, guildid, userid):
        """
        Fetch a Room owned by a given member.
        """
        return cls._rooms.get((guildid, userid), None)

    @property
    def data(self):
        return self._table.fetch(self.key)

    @property
    def owner(self):
        """
        The Member owning the room, if we can find them
        """
        guild = client.get_guild(self.data.guildid)
        if guild:
            return guild.get_member(self.data.ownerid)

    @property
    def channel(self):
        """
        The Channel corresponding to this rented room.
        """
        guild = client.get_guild(self.data.guildid)
        if guild:
            return guild.get_channel(self.key)

    @property
    def memberids(self):
        """
        The list of memberids in the channel.
        """
        return [row['userid'] for row in rented_members.select_where(channelid=self.key)]

    @property
    def timestamp(self):
        """
        True unix timestamp for the room expiry time.
        """
        return int(self.data.expires_at.replace(tzinfo=datetime.timezone.utc).timestamp())

    def delete(self):
        """
        Delete the room in an idempotent way.
        """
        if self._task and not self._task.done():
            self._task.cancel()
        self._rooms.pop(self.map_key, None)
        self._table.delete_where(channelid=self.key)

    def schedule(self):
        """
        Schedule this room to be expired.
        """
        asyncio.create_task(self._schedule())
        self._rooms[self.map_key] = self

    async def _schedule(self):
        """
        Expire the room after a sleep period.
        """
        # Calculate time left
        remaining = (self.data.expires_at - datetime.datetime.utcnow()).total_seconds()

        # Create the waiting task and wait for it, accepting cancellation
        self._task = asyncio.create_task(asyncio.sleep(remaining))
        try:
            await self._task
        except asyncio.CancelledError:
            return
        await self._execute()

    async def _execute(self):
        """
        Expire the room.
        """
        owner = self.owner
        guild_settings = GuildSettings(owner.guild.id)

        if self.channel:
            # Delete the discord channel
            try:
                await self.channel.delete()
            except discord.HTTPException:
                pass

        # Delete the room from data (cascades to member deletion)
        self.delete()

        guild_settings.event_log.log(
            title="Private study room expired!",
            description="{}'s private study room expired.".format(owner.mention)
        )

    async def add_members(self, *members):
        guild_settings = GuildSettings(self.data.guildid)

        # Update overwrites
        overwrites = self.channel.overwrites
        overwrites.update({member: self.member_overwrite for member in members})
        try:
            await self.channel.edit(overwrites=overwrites)
        except discord.HTTPException:
            guild_settings.event_log.log(
                title="Failed to update study room permissions!",
                description="An error occurred while adding the following users to the private room {}.\n{}".format(
                    self.channel.mention,
                    ', '.join(member.mention for member in members)
                ),
                colour=discord.Colour.red()
            )
            raise SafeCancellation("Sorry, something went wrong while adding the members!")

        # Update data
        rented_members.insert_many(
            *((self.key, member.id) for member in members)
        )

        # Log
        guild_settings.event_log.log(
            title="New members added to private study room",
            description="The following were added to {}.\n{}".format(
                self.channel.mention,
                ', '.join(member.mention for member in members)
            )
        )

    async def remove_members(self, *members):
        guild_settings = GuildSettings(self.data.guildid)

        if self.channel:
            # Update overwrites
            try:
                await asyncio.gather(
                    *(self.channel.set_permissions(
                        member,
                        overwrite=None,
                        reason="Removing members from private channel.") for member in members)
                )
            except discord.HTTPException:
                guild_settings.event_log.log(
                    title="Failed to update study room permissions!",
                    description=("An error occured while removing the "
                                 "following members from the private room {}.\n{}").format(
                                    self.channel.mention,
                                    ', '.join(member.mention for member in members)
                                ),
                    colour=discord.Colour.red()
                )
                raise SafeCancellation("Sorry, something went wrong while removing those members!")

            # Disconnect members if possible:
            to_disconnect = set(self.channel.members).intersection(members)
            try:
                await asyncio.gather(
                    *(member.edit(voice_channel=None) for member in to_disconnect)
                )
            except discord.HTTPException:
                pass

        # Update data
        rented_members.delete_where(channelid=self.key, userid=[member.id for member in members])

        # Log
        guild_settings.event_log.log(
            title="Members removed from a private study room",
            description="The following were removed from {}.\n{}".format(
                self.channel.mention if self.channel else "`{}`".format(self.key),
                ', '.join(member.mention for member in members)
            )
        )


@module.launch_task
async def load_rented_rooms(client):
    rows = rented.fetch_rows_where()
    for row in rows:
        Room(row.channelid).schedule()
    client.log(
        "Loaded {} private study channels.".format(len(rows)),
        context="LOAD_RENTED_ROOMS"
    )


@client.add_after_event('member_join')
async def restore_room_permission(client, member):
    """
    If a member has, or is part of, a private room when they rejoin, restore their permissions.
    """
    # First check whether they own a room
    owned = Room.fetch(member.guild.id, member.id)
    if owned and owned.channel:
        # Restore their room permissions
        try:
            await owned.channel.set_permissions(
                member,
                overwrite=Room.owner_overwrite
            )
        except discord.HTTPException:
            pass

    # Then check if they are in any other rooms
    in_room_rows = rented_members.select_where(
        _extra="LEFT JOIN rented USING (channelid) WHERE userid={} AND guildid={}".format(
            member.id, member.guild.id
        )
    )
    for row in in_room_rows:
        room = Room.fetch(member.guild.id, row['ownerid'])
        if room and row['ownerid'] != member.id and room.channel:
            try:
                await room.channel.set_permissions(
                    member,
                    overwrite=Room.member_overwrite
                )
            except discord.HTTPException:
                pass

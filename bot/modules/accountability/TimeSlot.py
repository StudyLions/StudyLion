from typing import List, Dict
import datetime
import discord
import asyncio

from settings import GuildSettings
from utils.lib import tick, cross
from core import Lion

from .lib import utc_now
from .data import accountability_members, accountability_rooms


class SlotMember:
    """
    Class representing a member booked into an accountability room.
    Mostly acts as an interface to the corresponding TableRow.
    But also stores the discord.Member associated, and has several computed properties.
    The member may be None.
    """
    ___slots__ = ('slotid', 'userid', 'guild')

    def __init__(self, slotid, userid, guild):
        self.slotid = slotid
        self.userid = userid
        self.guild = guild

        self._member = None

    @property
    def key(self):
        return (self.slotid, self.userid)

    @property
    def data(self):
        return accountability_members.fetch(self.key)

    @property
    def member(self):
        return self.guild.get_member(self.data.userid)

    @property
    def has_attended(self):
        return self.data.duration > 0 or self.data.last_joined_at


class TimeSlot:
    """
    Class representing an accountability slot.
    """
    __slots__ = (
        'guild',
        'start_time',
        'data',
        'lobby',
        'category',
        'channel',
        'message',
        'members'
    )

    slots = {}
    channel_slots = {}

    _member_overwrite = discord.PermissionOverwrite(
        view_channel=True,
        connect=True
    )

    _everyone_overwrite = discord.PermissionOverwrite(
        view_channel=False
    )

    def __init__(self, guild, start_time, data=None):
        self.guild: discord.Guild = guild
        self.start_time: datetime.datetime = start_time
        self.data = data

        self.lobby: discord.TextChannel = None  # Text channel to post the slot status
        self.category: discord.CategoryChannel = None  # Category to create the voice rooms in
        self.channel: discord.VoiceChannel = None  # Text channel associated with this time slot
        self.message: discord.Message = None  # Status message in lobby channel

        self.members: Dict[int, SlotMember] = {}  # memberid -> SlotMember

    @property
    def open_embed(self):
        # TODO Consider adding hint to footer
        timestamp = int(self.start_time.timestamp())

        embed = discord.Embed(
            title="Session <t:{}:t> - <t:{}:t>".format(
                timestamp, timestamp + 3600
            ),
            colour=discord.Colour.orange(),
            timestamp=self.start_time
        ).set_footer(text="About to start!")

        if self.members:
            embed.description = "Starting <t:{}:R>.".format(timestamp)
            embed.add_field(
                name="Members",
                value=(
                    ', '.join('<@{}>'.format(key) for key in self.members.keys())
                )
            )
        else:
            embed.description = "No members booked for this session!"

        return embed

    @property
    def status_embed(self):
        timestamp = int(self.start_time.timestamp())
        embed = discord.Embed(
            title="Session <t:{}:t> - <t:{}:t>".format(
                timestamp, timestamp + 3600
            ),
            description="Finishing <t:{}:R>.".format(timestamp + 3600),
            colour=discord.Colour.orange(),
            timestamp=self.start_time
        ).set_footer(text="Running")

        if self.members:
            classifications = {
                "Attended": [],
                "Studying Now": [],
                "Waiting for": []
            }
            for memid, mem in self.members.items():
                mention = '<@{}>'.format(memid)
                if not mem.has_attended:
                    classifications["Waiting for"].append(mention)
                elif mem.member in self.channel.members:
                    classifications["Studying Now"].append(mention)
                else:
                    classifications["Attended"].append(mention)

            bonus_line = (
                "{tick} All members attended, and will get a `{bonus} LC` completion bonus!".format(
                    tick=tick,
                    bonus=GuildSettings(self.guild.id).accountability_bonus.value
                )
                if all(mem.has_attended for mem in self.members.values()) else ""
            )

            embed.description += "\n" + bonus_line
            for field, value in classifications.items():
                if value:
                    embed.add_field(name=field, value='\n'.join(value))
        else:
            embed.description = "No members booked for this session!"

        return embed

    @property
    def summary_embed(self):
        timestamp = int(self.start_time.timestamp())
        embed = discord.Embed(
            title="Session <t:{}:t> - <t:{}:t>".format(
                timestamp, timestamp + 3600
            ),
            description="Finished <t:{}:R>.".format(timestamp + 3600),
            colour=discord.Colour.orange(),
            timestamp=self.start_time
        ).set_footer(text="Completed!")

        if self.members:
            classifications = {
                "Attended": [],
                "Missing": []
            }
            for memid, mem in sorted(self.members.items(), key=lambda mem: mem[1].data.duration, reverse=True):
                mention = '<@{}>'.format(memid)
                if mem.has_attended:
                    classifications["Attended"].append(
                        "{} ({}%)".format(mention, (mem.data.duration * 100) // 3600)
                    )
                else:
                    classifications["Missing"].append(mention)

            bonus_line = (
                "{tick} All members attended, and received a `{bonus} LC` completion bonus!".format(
                    tick=tick,
                    bonus=GuildSettings(self.guild.id).accountability_bonus.value
                )
                if all(mem.has_attended for mem in self.members.values()) else
                "{cross} Some members missed the session, so everyone missed out on the bonus!".format(
                    cross=cross
                )
            )

            embed.description += "\n" + bonus_line
            for field, value in classifications.items():
                if value:
                    embed.add_field(name=field, value='\n'.join(value))
        else:
            embed.description = "No members booked this session!"

        return embed

    def load(self, memberids: List[int] = None):
        """
        Load data and update applicable caches.
        """
        # Load setting data
        self.category = GuildSettings(self.guild.id).accountability_category.value
        self.lobby = GuildSettings(self.guild.id).accountability_lobby.value

        if self.data:
            # Load channel
            if self.data.channelid:
                self.channel = self.guild.get_channel(self.data.channelid)

            # Load message
            if self.data.messageid:
                self.message = discord.PartialMessage(
                    channel=self.lobby,
                    id=self.data.messageid
                )

            # Load members
            if memberids:
                self.members = {
                    memberid: SlotMember(self.data.slotid, memberid, self.guild)
                    for memberid in memberids
                }

        return self

    def _refresh(self):
        """
        Refresh the stored data row and reload.
        """
        self.data = next(accountability_rooms.fetch_rows_where(
            guildid=self.guild.id,
            open_at=self.start_time
        ), None)
        self.load()

    async def open(self):
        """
        Open the accountability room.
        Creates a new voice channel, and sends the status message.
        Event logs any issues.
        Adds the TimeSlot to cache.
        Returns the (channelid, messageid).
        """
        # Calculate overwrites
        overwrites = {
            mem.member: self._member_overwrite
            for mem in self.members.values()
        }
        overwrites[self.guild.default_role] = self._everyone_overwrite

        # Create the channel. Log and bail if something went wrong.
        if self.data and not self.channel:
            try:
                self.channel = await self.guild.create_voice_channel(
                    "Upcoming Accountability Study Room",
                    overwrites=overwrites,
                    category=self.category
                )
            except discord.HTTPException:
                GuildSettings(self.guild.id).event_log.log(
                    "Failed to create the accountability voice channel. Skipping this session.",
                    colour=discord.Colour.red()
                )
                return None
        elif not self.data:
            self.channel = None

        # Send the inital status message. Log and bail if something goes wrong.
        if not self.message:
            try:
                self.message = await self.lobby.send(
                    embed=self.open_embed
                )
            except discord.HTTPException as e:
                print(e)
                GuildSettings(self.guild.id).event_log.log(
                    "Failed to post the status message in the accountability lobby {}.\n"
                    "Skipping this session.".format(self.lobby.mention),
                    colour=discord.Colour.red()
                )
                return None
            if self.members:
                await self.channel_notify()
        return (self.channel.id if self.channel else None, self.message.id)

    async def channel_notify(self, content=None):
        """
        Ghost pings the session members in the lobby channel.
        """
        if self.members:
            content = content or "Your accountability session has opened! Please join!"
            out = "{}\n\n{}".format(
                content,
                ' '.join('<@{}>'.format(memid) for memid, mem in self.members.items() if not mem.has_attended)
            )
            out_msg = await self.lobby.send(out)
            await out_msg.delete()

    async def start(self):
        """
        Start the accountability room slot.
        Update the status message, and launch the DM reminder.
        """
        if self.channel:
            await self.channel.edit(name="Accountability Study Room")
            await self.channel.set_permissions(self.guild.default_role, view_channel=True)
            asyncio.create_task(self.dm_reminder(delay=60))
        await self.message.edit(embed=self.status_embed)

    async def dm_reminder(self, delay=60):
        """
        Notifies missing members with a direct message after 1 minute.
        """
        await asyncio.sleep(delay)

        embed = discord.Embed(
            title="Your accountability session has started!",
            description="Please join {}.".format(self.channel.mention),
            colour=discord.Colour.orange()
        ).set_footer(
            text=self.guild.name,
            icon_url=self.guild.icon_url
        )

        members = (mem.member for mem in self.members.values() if not mem.has_attended)
        members = (member for member in members if member)
        await asyncio.gather(
            *(member.send(embed=embed) for member in members),
            return_exceptions=True
        )

    async def close(self):
        """
        Delete the channel and update the status message to display a session summary.
        Unloads the TimeSlot from cache.
        """
        if self.channel:
            try:
                await self.channel.delete()
            except discord.HTTPException:
                pass
        if self.message:
            try:
                await self.message.edit(embed=self.summary_embed)
            except discord.HTTPException:
                pass

        # Reward members appropriately
        guild_settings = GuildSettings(self.guild.id)
        reward = guild_settings.accountability_reward.value
        if all(mem.has_attended for mem in self.members.values()):
            reward += guild_settings.accountability_bonus.value

        for memid in self.members:
            Lion.fetch(self.guild.id, memid).addCoins(reward)

    async def cancel(self):
        """
        Cancel the slot, generally due to missing data.
        Updates the message and channel if possible, removes slot from cache, and also updates data.
        # TODO: Refund members
        """
        if self.data:
            self.data.closed_at = utc_now()

        if self.channel:
            try:
                await self.channel.delete()
            except discord.HTTPException:
                pass

        if self.message:
            try:
                timestamp = self.start_time.timestamp()
                embed = discord.Embed(
                    title="Session <t:{}:t> - <t:{}:t>".format(
                        timestamp, timestamp + 3600
                    ),
                    description="Session canceled!",
                    colour=discord.Colour.red()
                )
                await self.message.edit(embed=embed)
            except discord.HTTPException:
                pass

    async def update_status(self):
        """
        Intelligently update the status message.
        """
        if self.message:
            if utc_now() < self.start_time:
                await self.message.edit(embed=self.open_embed)
            elif utc_now() < self.start_time + datetime.timedelta(hours=1):
                await self.message.edit(embed=self.status_embed)
            else:
                await self.message.edit(embed=self.summary_embed)

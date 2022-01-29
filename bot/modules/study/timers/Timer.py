import math
import asyncio
import discord
from collections import namedtuple
from datetime import timedelta

from utils.lib import utc_now
from utils.interactive import discord_shield
from meta import client
from settings import GuildSettings
from data.conditions import THIS_SHARD


from ..module import module

from .data import timers as timer_table


Stage = namedtuple('Stage', ['name', 'start', 'duration', 'end'])


class Timer:
    timers = {}  # channelid -> Timer

    def __init__(self, channelid):
        self.channelid = channelid
        self.last_seen = {
        }  # Memberid -> timestamps

        self.reaction_message = None

        self._state = None
        self._last_voice_update = None

        self._voice_update_task = None
        self._run_task = None
        self._runloop_task = None

    @classmethod
    def create(cls, channel, focus_length, break_length, **kwargs):
        timer_table.create_row(
            channelid=channel.id,
            guildid=channel.guild.id,
            focus_length=focus_length,
            break_length=break_length,
            last_started=kwargs.pop('last_started', utc_now()),
            **kwargs
        )
        return cls(channel.id)

    @classmethod
    def fetch_timer(cls, channelid):
        return cls.timers.get(channelid, None)

    @classmethod
    def fetch_guild_timers(cls, guildid):
        timers = []
        guild = client.get_guild(guildid)
        if guild:
            for channel in guild.voice_channels:
                if (timer := cls.timers.get(channel.id, None)):
                    timers.append(timer)

        return timers

    @property
    def data(self):
        return timer_table.fetch(self.channelid)

    @property
    def focus_length(self):
        return self.data.focus_length

    @property
    def break_length(self):
        return self.data.break_length

    @property
    def inactivity_threshold(self):
        return self.data.inactivity_threshold or 3

    @property
    def current_stage(self):
        if (last_start := self.data.last_started) is None:
            # Timer hasn't been started
            return None
        now = utc_now()
        diff = (now - last_start).total_seconds()
        diff %= (self.focus_length + self.break_length)
        if diff > self.focus_length:
            return Stage(
                'BREAK',
                now - timedelta(seconds=(diff - self.focus_length)),
                self.break_length,
                now + timedelta(seconds=(- diff + self.focus_length + self.break_length))
            )
        else:
            return Stage(
                'FOCUS',
                now - timedelta(seconds=diff),
                self.focus_length,
                now + timedelta(seconds=(self.focus_length - diff))
            )

    @property
    def guild(self):
        return client.get_guild(self.data.guildid)

    @property
    def channel(self):
        return client.get_channel(self.channelid)

    @property
    def text_channel(self):
        if (channelid := self.data.text_channelid) and (channel := self.guild.get_channel(channelid)):
            return channel
        else:
            return GuildSettings(self.data.guildid).pomodoro_channel.value

    @property
    def members(self):
        if (channel := self.channel):
            return [member for member in channel.members if not member.bot]
        else:
            return []

    @property
    def channel_name(self):
        """
        Current name for the voice channel
        """
        stage = self.current_stage
        name_format = self.data.channel_name or "{remaining} {stage} -- {name}"
        name = name_format.replace(
            '{remaining}', "{}m".format(
                int(5 * math.ceil((stage.end - utc_now()).total_seconds() / 300)),
            )
        ).replace(
            '{stage}', stage.name.lower()
        ).replace(
            '{members}', str(len(self.channel.members))
        ).replace(
            '{name}', self.data.pretty_name or "WORK ROOM"
        ).replace(
            '{pattern}',
            "{}/{}".format(
                int(self.focus_length // 60), int(self.break_length // 60)
            )
        )
        return name[:100]

    async def notify_change_stage(self, old_stage, new_stage):
        # Update channel name
        asyncio.create_task(self._update_channel_name())

        # Kick people if they need kicking
        to_warn = []
        to_kick = []
        warn_threshold = (self.inactivity_threshold - 1) * (self.break_length + self.focus_length)
        kick_threshold = self.inactivity_threshold * (self.break_length + self.focus_length)
        for member in self.members:
            if member.id in self.last_seen:
                diff = (utc_now() - self.last_seen[member.id]).total_seconds()
                if diff >= kick_threshold:
                    to_kick.append(member)
                elif diff > warn_threshold:
                    to_warn.append(member)
            else:
                # Shouldn't really happen, but
                self.last_seen[member.id] = utc_now()

        content = []
        if to_kick:
            # Do kick
            await asyncio.gather(
                *(member.edit(voice_channel=None) for member in to_kick),
                return_exceptions=True
            )
            kick_string = (
                "**Kicked due to inactivity:** {}".format(', '.join(member.mention for member in to_kick))
            )
            content.append(kick_string)

        if to_warn:
            warn_string = (
                "**Please react to avoid being kicked:** {}".format(
                    ', '.join(member.mention for member in to_warn)
                )
            )
            content.append(warn_string)

        # Send a new status/reaction message
        if self.text_channel and self.members:
            old_reaction_message = self.reaction_message

            # Send status image, add reaction
            self.reaction_message = await self.text_channel.send(
                content='\n'.join(content),
                **(await self.status())
            )
            await self.reaction_message.add_reaction('✅')

            if old_reaction_message:
                asyncio.create_task(discord_shield(old_reaction_message.delete()))

            # Ping people
            members = self.members
            blocks = [
                ''.join(member.mention for member in members[i:i+90])
                for i in range(0, len(members), 90)
            ]
            await asyncio.gather(
                *(self.text_channel.send(block, delete_after=0.5) for block in blocks),
                return_exceptions=True
            )
        elif not self.members:
            await self.update_last_status()
        # TODO: DM task if anyone has notifications on

        # Mute or unmute everyone in the channel as needed
        # Not possible, due to Discord restrictions
        # overwrite = self.channel.overwrites_for(self.channel.guild.default_role)
        # overwrite.speak = (new_stage.name == 'BREAK')
        # try:
        #     await self.channel.set_permissions(
        #         self.channel.guild.default_role,
        #         overwrite=overwrite
        #     )
        # except discord.HTTPException:
        #     pass

        # Run the notify hook
        await self.notify_hook(old_stage, new_stage)

    async def notify_hook(self, old_stage, new_stage):
        """
        May be overridden to provide custom actions during notification.
        For example, for voice alerts.
        """
        ...

    async def _update_channel_name(self):
        # Attempt to update the voice channel name
        # Ensures that only one update is pending at any time
        # Attempts to wait until the next viable channel update
        if self._voice_update_task:
            self._voice_update_task.cancel()

        if not self.channel:
            return

        if self.channel.name == self.channel_name:
            return

        if not self.channel.permissions_for(self.channel.guild.me).manage_channels:
            return

        if self._last_voice_update:
            to_wait = ((self._last_voice_update + timedelta(minutes=5)) - utc_now()).total_seconds()
            if to_wait > 0:
                self._voice_update_task = asyncio.create_task(asyncio.sleep(to_wait))
                try:
                    await self._voice_update_task
                except asyncio.CancelledError:
                    return
        self._voice_update_task = asyncio.create_task(
            self.channel.edit(name=self.channel_name)
        )
        try:
            await self._voice_update_task
            self._last_voice_update = utc_now()
        except asyncio.CancelledError:
            return

    async def status(self):
        """
        Returns argument dictionary compatible with `discord.Channel.send`.
        """
        # Generate status message
        stage = self.current_stage
        stage_str = "**{}** minutes focus with **{}** minutes break".format(
            self.focus_length // 60,
            self.break_length // 60
        )
        remaining = (stage.end - utc_now()).total_seconds()

        memberstr = ', '.join(member.mention for member in self.members[:20])
        if len(self.members) > 20:
            memberstr += '...'

        description = (
            ("{}: {}\n"
             "Currently in `{}`, with `{:02}:{:02}` remaining.\n"
             "{}").format(
                 self.channel.mention,
                 stage_str,
                 stage.name,
                 int(remaining // 3600),
                 int((remaining // 60) % 60),
                 memberstr
             )
        )
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            description=description
        )
        return {'embed': embed}

    async def update_last_status(self):
        """
        Update the last posted status message, if it exists.
        """
        args = await self.status()
        repost = True
        if self.reaction_message:
            try:
                await self.reaction_message.edit(**args)
            except discord.HTTPException:
                pass
            else:
                repost = False

        if repost and self.text_channel:
            try:
                self.reaction_message = await self.text_channel.send(**args)
                await self.reaction_message.add_reaction('✅')
            except discord.HTTPException:
                pass

        return

    async def destroy(self):
        """
        Remove the timer.
        """
        # Remove timer from cache
        self.timers.pop(self.channelid, None)

        # Cancel the loop
        if self._run_task:
            self._run_task.cancel()

        # Delete the reaction message
        if self.reaction_message:
            try:
                await self.reaction_message.delete()
            except discord.HTTPException:
                pass

        # Remove the timer from data
        timer_table.delete_where(channelid=self.channelid)

    async def run(self):
        """
        Runloop
        """
        timer = self.timers.pop(self.channelid, None)
        if timer and timer._run_task:
            timer._run_task.cancel()
        self.timers[self.channelid] = self

        if not self.data.last_started:
            self.data.last_started = utc_now()
            asyncio.create_task(self.notify_change_stage(None, self.current_stage))

        while True:
            stage = self._state = self.current_stage
            to_next_stage = (stage.end - utc_now()).total_seconds()

            # Allow updating with 10 seconds of drift to stage change
            if to_next_stage > 10 * 60 - 10:
                time_to_sleep = 5 * 60
            else:
                time_to_sleep = to_next_stage

            self._run_task = asyncio.create_task(asyncio.sleep(time_to_sleep))
            try:
                await self._run_task
            except asyncio.CancelledError:
                break

            # Destroy the timer if our voice channel no longer exists
            if not self.channel:
                await self.destroy()
                break

            if self._state.end < utc_now():
                asyncio.create_task(self.notify_change_stage(self._state, self.current_stage))
            else:
                asyncio.create_task(self._update_channel_name())
                asyncio.create_task(self.update_last_status())

    def runloop(self):
        self._runloop_task = asyncio.create_task(self.run())


# Loading logic
@module.launch_task
async def load_timers(client):
    timer_rows = timer_table.fetch_rows_where(
        guildid=THIS_SHARD
    )
    count = 0
    for row in timer_rows:
        if client.get_channel(row.channelid):
            # Channel exists
            # Create the timer
            timer = Timer(row.channelid)

            # Populate the members
            timer.last_seen = {
                member.id: utc_now()
                for member in timer.members
            }

            # Start the timer
            timer.runloop()
            count += 1

    client.log(
        "Loaded and start '{}' timers!".format(count),
        context="TIMERS"
    )


# Hooks
@client.add_after_event('raw_reaction_add')
async def reaction_tracker(client, payload):
    if payload.guild_id and payload.member and not payload.member.bot and payload.member.voice:
        if (channel := payload.member.voice.channel) and (timer := Timer.fetch_timer(channel.id)):
            if timer.reaction_message and payload.message_id == timer.reaction_message.id:
                timer.last_seen[payload.member.id] = utc_now()


@client.add_after_event('voice_state_update')
async def touch_member(client, member, before, after):
    if not member.bot and after.channel != before.channel:
        if after.channel and (timer := Timer.fetch_timer(after.channel.id)):
            timer.last_seen[member.id] = utc_now()
            await timer.update_last_status()

        if before.channel and (timer := Timer.fetch_timer(before.channel.id)):
            timer.last_seen.pop(member.id, None)
            await timer.update_last_status()

import asyncio
import time
import logging
import traceback
from collections import defaultdict

import discord
from utils.lib import utc_now
from core import Lion
from meta import client

from modules.study.timers.Timer import Timer

from ...cards import FocusTimerCard, BreakTimerCard

from ...utils import get_avatar_key, image_as_file, edit_files, asset_path


async def status(self):
    stage = self.current_stage

    name = self.data.pretty_name
    remaining = int((stage.end - utc_now()).total_seconds())
    duration = int(stage.duration)
    next_starts = int(stage.end.timestamp())
    users = [
        (get_avatar_key(client, member.id),
         session.duration if (session := Lion.fetch(member.guild.id, member.id).session) else 0,
         session.data.tag if session else None)
        for member in self.members
    ]
    if stage.name == 'FOCUS':
        card_class = FocusTimerCard
        content = f"**Focus!** Session ends <t:{next_starts}:R>."
    else:
        card_class = BreakTimerCard
        content = f"**Have a rest!** Break finishes <t:{next_starts}:R>."

    page = await card_class.request(
        name,
        remaining,
        duration,
        users=users,
        skin=card_class.skin_args_for(guildid=self.data.guildid)
    )

    return {
        'content': content,
        'files': [image_as_file(page, name="timer.png")]
    }


_guard_delay = 60
_guarded = {}  # timer channel id -> (last_executed_time, currently_waiting)


async def guard_request(id):
    if (result := _guarded.get(id, None)):
        last, currently = result
        if currently:
            return False
        else:
            _guarded[id] = (last, True)
            await asyncio.sleep(_guard_delay - (time.time() - last))
            _guarded[id] = (time.time(), False)
            return True
    else:
        _guarded[id] = (time.time(), False)
        return True


async def update_last_status(self):
    """
    Update the last posted status message, if it exists.
    """
    old_message = self.reaction_message

    if not await guard_request(self.channelid):
        return
    if old_message != self.reaction_message:
        return

    args = await self.status()
    repost = True
    if self.reaction_message:
        try:
            await edit_files(
                client._connection.http,
                self.reaction_message.channel.id,
                self.reaction_message.id,
                **args
            )
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


guild_locks = defaultdict(asyncio.Lock)


async def play_alert(channel: discord.VoiceChannel, alert_file):
    if not channel.members:
        # Don't notify an empty channel
        return

    async with guild_locks[channel.guild.id]:
        try:
            vc = channel.guild.voice_client
            if not vc:
                vc = await asyncio.wait_for(
                    channel.connect(timeout=10, reconnect=False),
                    20
                )
            elif vc.channel != channel:
                await vc.move_to(channel)
        except asyncio.TimeoutError:
            client.log(
                f"Timed out while attempting to connect to '{channel.name}' (cid:{channel.id}) "
                f"in '{channel.guild.name}' (gid:{channel.guild.id}).",
                context="TIMER_ALERT",
                level=logging.WARNING
            )
            vc = channel.guild.voice_client
            if vc:
                await vc.disconnect(force=True)
            return

        audio_stream = open(alert_file, 'rb')
        try:
            vc.play(discord.PCMAudio(audio_stream), after=lambda e: audio_stream.close())
        except discord.HTTPException:
            pass

        count = 0
        while vc.is_playing() and count < 10:
            await asyncio.sleep(1)
            count += 1

        await vc.disconnect(force=True)


async def notify_hook(self, old_stage, new_stage):
    try:
        if new_stage.name == 'BREAK':
            await play_alert(self.channel, asset_path('timer/voice/break_alert.wav'))
        else:
            await play_alert(self.channel, asset_path('timer/voice/focus_alert.wav'))
    except Exception:
        full_traceback = traceback.format_exc()
        client.log(
            f"Caught an unhandled exception while playing timer alert in '{self.channel.name}' (cid:{self.channel.id})"
            f" in '{self.channel.guild.name}' (gid:{self.channel.guild.id}).\n"
            f"{full_traceback}",
            context="TIMER_ALERT",
            level=logging.ERROR
        )

Timer.status = status
Timer.update_last_status = update_last_status
Timer.notify_hook = notify_hook

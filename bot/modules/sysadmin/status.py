import time
import asyncio
import discord
from meta import client

from .module import module


_last_update = 0


async def update_status():
    # TODO: Make globally configurable and saveable
    global _last_update

    if time.time() - _last_update < 60:
        return

    _last_update = time.time()

    student_count, room_count = client.data.current_sessions.select_one_where(
        select_columns=("COUNT(*) AS studying_count", "COUNT(DISTINCT(channelid)) AS channel_count"),
    )
    status = "{} students in {} study rooms!".format(student_count, room_count)

    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=status
        )
    )


@client.add_after_event("voice_state_update")
async def trigger_status_update(client, member, before, after):
    if before.channel != after.channel:
        await update_status()


async def _status_loop():
    while not client.is_ready():
        await asyncio.sleep(5)
    while True:
        try:
            await update_status()
        except discord.HTTPException:
            pass
        await asyncio.sleep(300)


@module.launch_task
async def launch_status_update(client):
    asyncio.create_task(_status_loop())

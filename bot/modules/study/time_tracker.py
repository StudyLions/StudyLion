import itertools
import traceback
import logging
import asyncio
from time import time

from meta import client
from core import Lion

from .module import module
from . import admin


last_scan = {}  # guildid -> timestamp


def _scan(guild):
    """
    Scan the tracked voice channels and add time and coins to each user.
    """
    # Current timestamp
    now = time()

    # Get last scan timestamp
    try:
        last = last_scan[guild.id]
    except KeyError:
        return
    finally:
        last_scan[guild.id] = now

    # Calculate time since last scan
    interval = now - last

    # Discard if it has been more than 20 minutes (discord outage?)
    if interval > 60 * 20:
        return

    untracked = admin.untracked_channels.get(guild.id).data
    hourly_reward = admin.hourly_reward.get(guild.id).data
    hourly_live_bonus = admin.hourly_live_bonus.get(guild.id).data

    channel_members = (
        channel.members for channel in guild.voice_channels if channel.id not in untracked
    )

    members = itertools.chain(*channel_members)
    # TODO filter out blacklisted users

    for member in members:
        if member.bot:
            continue
        lion = Lion.fetch(guild.id, member.id)

        # Add time
        lion.addTime(interval, flush=False)

        # Add coins
        hour_reward = hourly_reward
        if member.voice.self_stream or member.voice.self_video:
            hour_reward += hourly_live_bonus

        lion.addCoins(hour_reward * interval / (3600), flush=False)


async def _study_tracker():
    """
    Scanner launch loop.
    """
    while True:
        while not client.is_ready():
            await asyncio.sleep(1)

        await asyncio.sleep(5)

        # Launch scanners on each guild
        for guild in client.guilds:
            # Short wait to pass control to other asyncio tasks if they need it
            await asyncio.sleep(0)
            try:
                # Scan the guild
                _scan(guild)
            except Exception:
                # Unknown exception. Catch it so the loop doesn't die.
                client.log(
                    "Error while scanning guild '{}'(gid:{})! "
                    "Exception traceback follows.\n{}".format(
                        guild.name,
                        guild.id,
                        traceback.format_exc()
                    ),
                    context="VOICE_ACTIVITY_SCANNER",
                    level=logging.ERROR
                )


@module.launch_task
async def launch_study_tracker(client):
    asyncio.create_task(_study_tracker())


# TODO: Logout handler, sync

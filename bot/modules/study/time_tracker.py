import itertools
import traceback
import logging
import asyncio
from time import time

from meta import client
from core import Lion

from .module import module
from . import admin

from settings import GuildSettings
from data import NULL, tables
import datetime

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

    blacklist = client.objects['blacklisted_users']
    guild_blacklist = client.objects['ignored_members'][guild.id]

    for member in members:
        if member.bot:
            continue
        if member.id in blacklist or member.id in guild_blacklist:
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
    # First pre-load the untracked channels
    await admin.untracked_channels.launch_task(client)
    asyncio.create_task(_study_tracker())

# only whitelisted non-bot member
def member_joined_voice_channel(user, member, joinedchannel):

    # Check if last_study_session_start is unset in data
    if user.data.last_study_session_start is not None or user.data.session_start_coins is not 0:
        GuildSettings(member.guild.id).event_log.log(
            "{} has joined `#{}` but last_study_session_start is {} and session_start_coins is {}".format(
                member.mention,
                joinedchannel,
                user.data.last_study_session_start,
                user.data.session_start_coins
            ), title="Member Session Data Inconsistent"
        )

    # set Start Study session timestamp, coins data
    user.data.last_study_session_start = datetime.datetime.utcnow()
    user.data.session_start_coins = user.coins

    GuildSettings(member.guild.id).event_log.log(
        "{} has joined `#{}`".format(
                member.mention,
                joinedchannel,
            ), title="Member joined Channel"
    )

# only whitelisted non-bot member
def member_left_voice_channel(user, member, channelleft):

    last_study_session_start = user.data.last_study_session_start
    session_start_coins = user.data.session_start_coins

    # reset Start Study session timestamp
    user.data.last_study_session_start = None
    user.data.session_start_coins = 0 # Default 0 not None

    now = datetime.datetime.utcnow()
    
    # Just show the coin alert when the user had atleast earned 1 coin
    if (user.coins - session_start_coins) > 0:
        GuildSettings(member.guild.id).coin_alert_channel.log(
            "{} has left `#{}` and spent a total time of `{:.2f}` mins and earned reward of `{}` coins".format(
                    member.mention,
                    channelleft,
                    (now - last_study_session_start).total_seconds() / 60,
                    (user.coins - session_start_coins)
                ), title="Hourly Reward"
        )
    
    GuildSettings(member.guild.id).event_log.log(
        "{} has left `#{}` and spent a total time of `{:.2f}` mins".format(
                member.mention,
                channelleft,
                (now - last_study_session_start).total_seconds() / 60
            ), title="Member Left Channel"
    )

@client.add_after_event("voice_state_update")
async def voice_state_log_updater(client, member, before, after):
    if not client.is_ready():
        # The poll loop will pick it up
        return

    if member.bot:
        return
    if member.id in client.objects['blacklisted_users']:
        return
    if member.id in client.objects['ignored_members'][member.guild.id]:
        return
    
    # Ensure guild row exists
    tables.guild_config.fetch_or_create(member.guild.id)
    
    # Fetch guild user
    user = Lion.fetch(member.guild.id, member.id)

    if after.channel and not before.channel:
        # Client joined a voice channel
        member_joined_voice_channel(user, member, after.channel)

    if before.channel and not after.channel:
        # client left a Voice Channel
        member_left_voice_channel(user, member, before.channel)

# TODO: Logout handler, sync

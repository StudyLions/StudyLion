import asyncio
import logging
import datetime as dt
import discord

from core import Lion
from settings import GuildSettings
from meta import client
from data import NULL, tables

from .module import module
from .data import workout_sessions
from . import admin


leave_tasks = {}


async def on_workout_join(member):
    key = (member.guild.id, member.id)

    # Cancel a leave task if the member rejoined in time
    if member.id in leave_tasks:
        leave_tasks[key].cancel()
        leave_tasks.pop(key)
        return

    # Create a started workout entry
    workout = workout_sessions.create_row(
        guildid=member.guild.id,
        userid=member.id,
        channelid=member.voice.channel.id
    )

    # Add to current workouts
    client.objects['current_workouts'][key] = workout

    # Log
    client.log(
        "User '{m.name}'(uid:{m.id}) started a workout in channel "
        "'{m.voice.channel.name}' (cid:{m.voice.channel.id}) "
        "of guild '{m.guild.name}' (gid:{m.guild.id}).".format(m=member),
        context="WORKOUT_STARTED"
    )
    GuildSettings(member.guild.id).event_log.log(
        "{} started a workout in {}".format(
            member.mention,
            member.voice.channel.mention
        ), title="Workout Started"
    )


async def on_workout_leave(member):
    key = (member.guild.id, member.id)

    # Create leave task in case of temporary disconnect
    task = asyncio.create_task(asyncio.sleep(3))
    leave_tasks[key] = task

    # Wait for the leave task, abort if it gets cancelled
    try:
        await task
        if member.id in leave_tasks:
            if leave_tasks[key] == task:
                leave_tasks.pop(key)
            else:
                return
    except asyncio.CancelledError:
        # Task was cancelled by rejoining
        if key in leave_tasks and leave_tasks[key] == task:
            leave_tasks.pop(key)
        return

    # Retrieve workout row and remove from current workouts
    workout = client.objects['current_workouts'].pop(key)

    await workout_left(member, workout)


async def workout_left(member, workout):
    time_diff = (dt.datetime.utcnow() - workout.start_time).total_seconds()
    min_length = GuildSettings(member.guild.id).min_workout_length.value
    if time_diff < 60 * min_length:
        # Left workout before it was finished. Log and delete
        client.log(
            "User '{m.name}'(uid:{m.id}) left their workout in guild '{m.guild.name}' (gid:{m.guild.id}) "
            "before it was complete! ({diff:.2f} minutes). Deleting workout.\n"
            "{workout}".format(
                m=member,
                diff=time_diff / 60,
                workout=workout
            ),
            context="WORKOUT_ABORTED",
            post=True
        )
        GuildSettings(member.guild.id).event_log.log(
            "{} left their workout before it was complete! (`{:.2f}` minutes)".format(
                member.mention,
                time_diff / 60,
            ), title="Workout Left"
        )
        workout_sessions.delete_where(sessionid=workout.sessionid)
    else:
        # Completed the workout
        client.log(
            "User '{m.name}'(uid:{m.id}) completed their daily workout in guild '{m.guild.name}' (gid:{m.guild.id}) "
            "({diff:.2f} minutes). Saving workout and notifying user.\n"
            "{workout}".format(
                m=member,
                diff=time_diff / 60,
                workout=workout
            ),
            context="WORKOUT_COMPLETED",
            post=True
        )
        workout.duration = time_diff
        await workout_complete(member, workout)


async def workout_complete(member, workout):
    key = (member.guild.id, member.id)

    # update and notify
    user = Lion.fetch(*key)
    user_data = user.data
    with user_data.batch_update():
        user_data.workout_count = user_data.workout_count + 1
        user_data.last_workout_start = workout.start_time

    settings = GuildSettings(member.guild.id)
    reward = settings.workout_reward.value
    user.addCoins(reward)

    settings.event_log.log(
        "{} completed their daily workout and was rewarded `{}` coins! (`{:.2f}` minutes)".format(
            member.mention,
            reward,
            workout.duration / 60,
        ), title="Workout Completed"
    )

    embed = discord.Embed(
        description=(
            "Congratulations on completing your daily workout!\n"
            "You have been rewarded with `{}` LionCoins. Good job!".format(reward)
        ),
        timestamp=dt.datetime.utcnow(),
        colour=discord.Color.orange()
    )
    embed.set_footer(
        text=member.guild.name,
        icon_url=member.guild.icon_url
    )
    try:
        await member.send(embed=embed)
    except discord.Forbidden:
        client.log(
            "Couldn't notify user '{m.name}'(uid:{m.id}) about their completed workout! "
            "They might have me blocked.".format(m=member),
            context="WORKOUT_COMPLETED",
            post=True
        )


@client.add_after_event("voice_state_update")
async def workout_voice_tracker(client, member, before, after):
    # Wait until launch tasks are complete
    while not module.ready:
        await asyncio.sleep(0.1)

    if member.bot:
        return

    # Check whether we are moving to/from a workout channel
    settings = GuildSettings(member.guild.id)
    channels = settings.workout_channels.value
    from_workout = before.channel in channels
    to_workout = after.channel in channels

    if to_workout ^ from_workout:
        # Ensure guild row exists
        tables.guild_config.fetch_or_create(member.guild.id)

        # Fetch workout user
        user = Lion.fetch(member.guild.id, member.id)

        # Ignore all workout events from users who have already completed their workout today
        if user.data.last_workout_start is not None:
            last_date = user.localize(user.data.last_workout_start).date()
            today = user.localize(dt.datetime.utcnow()).date()
            if last_date == today:
                return

        # TODO: Check if they have completed a workout today, if so, ignore
        if to_workout and not from_workout:
            await on_workout_join(member)
        elif from_workout and not to_workout:
            if (member.guild.id, member.id) in client.objects['current_workouts']:
                await on_workout_leave(member)
            else:
                client.log(
                    "Possible missed workout!\n"
                    "Member '{m.name}'(uid:{m.id}) left the workout channel '{c.name}'(cid:{c.id}) "
                    "in guild '{m.guild.name}'(gid:{m.guild.id}), but we never saw them join!".format(
                        m=member,
                        c=before.channel
                    ),
                    context="WORKOUT_TRACKER",
                    level=logging.ERROR,
                    post=True
                )
                settings.event_log.log(
                    "{} left the workout channel {}, but I never saw them join!".format(
                        member.mention,
                        before.channel.mention,
                    ), title="Possible Missed Workout!"
                )


@module.launch_task
async def load_workouts(client):
    client.objects['current_workouts'] = {}  # (guildid, userid) -> Row
    # Process any incomplete workouts
    workouts = workout_sessions.fetch_rows_where(
        duration=NULL
    )
    count = 0
    for workout in workouts:
        channelids = admin.workout_channels_setting.get(workout.guildid).data
        member = Lion.fetch(workout.guildid, workout.userid).member
        if member:
            if member.voice and (member.voice.channel.id in channelids):
                client.objects['current_workouts'][(workout.guildid, workout.userid)] = workout
                count += 1
            else:
                asyncio.create_task(workout_left(member, workout))
        else:
            client.log(
                "Removing incomplete workout from "
                "non-existent member (mid:{}) in guild (gid:{})".format(
                    workout.userid,
                    workout.guildid
                ),
                context="WORKOUT_LAUNCH",
                post=True
            )
    if count > 0:
        client.log(
            "Loaded {} in-progress workouts.".format(count), context="WORKOUT_LAUNCH", post=True
        )

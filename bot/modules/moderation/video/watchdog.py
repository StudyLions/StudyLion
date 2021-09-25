"""
Implements a tracker to warn, kick, and studyban members in video channels without video enabled.
"""
import asyncio
import logging
import datetime
import discord

from meta import client
from core import Lion
from utils.lib import strfdelta
from settings import GuildSettings

from ..tickets import StudyBanTicket
from ..module import module


_tasks = {}  # (guildid, userid) -> Task


async def _send_alert(member, embed, alert_channel):
    """
    Sends an embed to the member.
    If we can't reach the member, send it via alert_channel, if it exists.
    Returns the message, if it was sent, otherwise None.
    """
    try:
        return await member.send(embed=embed)
    except discord.Forbidden:
        if alert_channel:
            try:
                return await alert_channel.send(
                    content=(
                        "{} (Please enable your DMs with me to get alerts privately!)"
                    ).format(member.mention),
                    embed=embed
                )
            except discord.HTTPException:
                pass


async def _join_video_channel(member, channel):
    # Sanity checks
    if not member.voice and member.voice.channel:
        # Not in a voice channel
        return
    if member.voice.self_video:
        # Already have video on
        return

    # First wait for 15 seconds for them to turn their video on
    try:
        await asyncio.sleep(15)
    except asyncio.CancelledError:
        # They left the channel or turned their video on
        return

    # Fetch the relevant settings and build embeds
    guild_settings = GuildSettings(member.guild.id)
    grace_period = guild_settings.video_grace_period.value
    studyban = guild_settings.video_studyban.value
    studyban_role = guild_settings.studyban_role.value
    alert_channel = guild_settings.alert_channel.value

    lion = Lion.fetch(member.guild.id, member.id)
    previously_warned = lion.data.video_warned

    request_embed = discord.Embed(
        title="Please enable your video!",
        description=(
            "**You have joined the video-only channel {}!**\n"
            "Please **enable your video** or **leave the channel** in the next `{}` seconds, "
            "otherwise you will be **disconnected** and "
            "potentially **banned** from using this server's study facilities."
        ).format(
            channel.mention,
            grace_period
        ),
        colour=discord.Colour.orange(),
        timestamp=datetime.datetime.utcnow()
    ).set_footer(
        text=member.guild.name,
        icon_url=member.guild.icon_url
    )

    thanks_embed = discord.Embed(
        title="Thanks for enabling your video! Best of luck with your study.",
        colour=discord.Colour.green(),
        timestamp=datetime.datetime.utcnow()
    ).set_footer(
        text=member.guild.name,
        icon_url=member.guild.icon_url
    )

    bye_embed = discord.Embed(
        title="Thanks for leaving the channel promptly!",
        colour=discord.Colour.green(),
        timestamp=datetime.datetime.utcnow()
    ).set_footer(
        text=member.guild.name,
        icon_url=member.guild.icon_url
    )

    # Send the notification message and wait for the grace period
    out_msg = None
    alert_task = asyncio.create_task(_send_alert(
        member,
        request_embed,
        alert_channel
    ))
    try:
        out_msg = await asyncio.shield(alert_task)
        await asyncio.sleep(grace_period)
    except asyncio.CancelledError:
        # They left the channel or turned their video on

        # Finish the message task if it wasn't complete
        if not alert_task.done():
            out_msg = await alert_task

        # Update the notification message
        # The out_msg may be None here, if we have no way of reaching the member
        if out_msg is not None:
            try:
                if not member.voice or not (member.voice.channel == channel):
                    await out_msg.edit(embed=bye_embed)
                elif member.voice.self_video:
                    await out_msg.edit(embed=thanks_embed)
            except discord.HTTPException:
                pass
        return

    # Disconnect, notify, warn, and potentially study ban
    # Don't allow this to be cancelled any more
    _tasks.pop((member.guild.id, member.id), None)

    # First disconnect
    client.log(
        ("Disconnecting member {} (uid: {}) in guild {} (gid: {}) from video channel {} (cid:{}) "
         "for not enabling their video.").format(
             member.name,
             member.id,
             member.guild.name,
             member.guild.id,
             channel.name,
             channel.id
         ),
        context="VIDEO_WATCHDOG"
    )
    try:
        await member.edit(
            voice_channel=None,
            reason="Member in video-only channel did not enable video."
        )
    except discord.HTTPException:
        # TODO: Add it to the moderation ticket
        # Error log?
        ...

    # Then warn or study ban, with appropriate notification
    only_warn = not previously_warned or not studyban or not studyban_role

    if only_warn:
        # Give them an official warning
        embed = discord.Embed(
            title="You have received a warning!",
            description=(
                "You must enable your camera in camera-only rooms."
            ),
            colour=discord.Colour.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(
            name="Info",
            value=(
                "*Warnings appear in your moderation history. "
                "Failure to comply, or repeated warnings, "
                "may result in muting, studybanning, or server banning.*"
            )
        )
        embed.set_footer(
            icon_url=member.guild.icon_url,
            text=member.guild.name
        )
        await _send_alert(member, embed, alert_channel)
        # TODO: Warning ticket and related embed.
        lion.data.video_warned = True
    else:
        # Apply an automatic studyban
        ticket = await StudyBanTicket.autoban(
            member.guild,
            member,
            "Failed to enable their video in time in the video channel {}.".format(channel.mention)
        )
        if ticket:
            tip = "TIP: When joining a video only study room, always be ready to enable your video immediately!"
            embed = discord.Embed(
                title="You have been studybanned!",
                description=(
                    "You have been banned from studying in **{}**.\n"
                    "Study features, including **study voice channels** and **study text channels**, "
                    "will ***not be available to you until this ban is lifted.***".format(
                        member.guild.name,
                    )
                ),
                colour=discord.Colour.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(
                name="Reason",
                value="Failure to enable your video in time in a video-only channel.\n\n*{}*".format(tip)
            )
            if ticket.data.duration:
                embed.add_field(
                    name="Duration",
                    value="`{}` (Expires <t:{:.0f}>)".format(
                        strfdelta(datetime.timedelta(seconds=ticket.data.duration)),
                        ticket.data.expiry.timestamp()
                    ),
                    inline=False
                )
            embed.set_footer(
                text=member.guild.name,
                icon_url=member.guild.icon_url
            )
            await _send_alert(member, embed, alert_channel)
        else:
            # This should be impossible
            # TODO: Cautionary error logging
            pass


@client.add_after_event("voice_state_update")
async def video_watchdog(client, member, before, after):
    if member.bot:
        return

    task_key = (member.guild.id, member.id)

    if after.channel != before.channel:
        # Channel change, cancel any running tasks for the member
        task = _tasks.pop(task_key, None)
        if task and not task.done():
            task.cancel()

        # Check whether they are joining a video channel, run join logic if so
        if after.channel and not after.self_video:
            video_channel_ids = GuildSettings(member.guild.id).video_channels.data
            if after.channel.id in video_channel_ids:
                client.log(
                    ("Launching join task for member {} (uid: {}) "
                     "in guild {} (gid: {}) and video channel {} (cid:{}).").format(
                         member.name,
                         member.id,
                         member.guild.name,
                         member.guild.id,
                         after.channel.name,
                         after.channel.id
                    ),
                    context="VIDEO_WATCHDOG",
                    level=logging.DEBUG
                )
                _tasks[task_key] = asyncio.create_task(_join_video_channel(member, after.channel))
    else:
        video_channel_ids = GuildSettings(member.guild.id).video_channels.data
        if after.channel and after.channel.id in video_channel_ids:
            channel = after.channel
            if after.self_video:
                # If they have their video on, cancel any running tasks
                task = _tasks.pop(task_key, None)
                if task and not task.done():
                    task.cancel()
            else:
                # They have their video off
                # Don't do anything if there are running tasks, the tasks will handle it
                task = _tasks.get(task_key, None)
                if task and not task.done():
                    return

                # Otherwise, give them 10 seconds
                _tasks[task_key] = task = asyncio.create_task(asyncio.sleep(10))
                try:
                    await task
                except asyncio.CancelledError:
                    # Task was cancelled, they left the channel or turned their video on
                    return

                # Then kick them out, alert them, and event log it
                client.log(
                    ("Disconnecting member {} (uid: {}) in guild {} (gid: {}) from video channel {} (cid:{}) "
                     "for disabling their video.").format(
                         member.name,
                         member.id,
                         member.guild.name,
                         member.guild.id,
                         channel.name,
                         channel.id
                     ),
                    context="VIDEO_WATCHDOG"
                )
                try:
                    await member.edit(
                        voice_channel=None,
                        reason="Removing non-video member from video-only channel."
                    )
                    await _send_alert(
                        member,
                        discord.Embed(
                            title="You have been kicked from the video channel.",
                            description=(
                                "You were disconnected from the video-only channel {} for disabling your video.\n"
                                "Please keep your video on at all times, and leave the channel if you need "
                                "to make adjustments!"
                            ).format(
                                    channel.mention,
                            ),
                            colour=discord.Colour.red(),
                            timestamp=datetime.datetime.utcnow()
                        ).set_footer(
                            text=member.guild.name,
                            icon_url=member.guild.icon_url
                        ),
                        GuildSettings(member.guild.id).alert_channel.value
                    )
                except discord.Forbidden:
                    GuildSettings(member.guild.id).event_log.log(
                        "I attempted to disconnect {} from the video-only channel {} "
                        "because they disabled their video, but I didn't have the required permissions!\n".format(
                            member.mention,
                            channel.mention
                        )
                    )
                else:
                    GuildSettings(member.guild.id).event_log.log(
                        "{} was disconnected from the video-only channel {} "
                        "because they disabled their video.".format(
                            member.mention,
                            channel.mention
                        )
                    )


@module.launch_task
async def load_video_channels(client):
    """
    Process existing video channel members.
    Pre-fills the video channel cache by running the setting launch task.

    Treats members without video on as having just joined.
    """
    # Run the video channel initialisation to populate the setting cache
    await GuildSettings.settings.video_channels.launch_task(client)

    # Launch join tasks for all members in video channels without video enabled
    video_channels = (
        channel
        for guild in client.guilds
        for channel in guild.voice_channels
        if channel.members and channel.id in GuildSettings.settings.video_channels.get(guild.id).data
    )
    to_task = [
        (member, channel)
        for channel in video_channels
        for member in channel.members
        if not member.voice.self_video
    ]
    for member, channel in to_task:
        _tasks[(member.guild.id, member.id)] = asyncio.create_task(_join_video_channel(member, channel))

    if to_task:
        client.log(
            "Launched {} join tasks for members who need to enable their video.".format(len(to_task)),
            context="VIDEO_CHANNEL_LAUNCH"
        )

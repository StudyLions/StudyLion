import asyncio
import discord
from cmdClient import Context
from cmdClient.checks import in_guild
from cmdClient.lib import SafeCancellation

from wards import guild_admin
from utils.lib import utc_now, tick

from ..module import module

from .Timer import Timer


config_flags = ('name==', 'threshold=', 'channelname==', 'text==')
MAX_TIMERS_PER_GUILD = 10


@module.cmd(
    "timer",
    group="Productivity",
    desc="View your study room timer.",
    flags=config_flags
)
@in_guild()
async def cmd_timer(ctx: Context, flags):
    """
    Usage``:
        {prefix}timer
    Description:
        Display your current study room timer status.
        If you aren't in a study room, instead shows a list of timers you can join.
    """
    channel = ctx.author.voice.channel if ctx.author.voice else None
    if ctx.args:
        if len(ctx.args.split()) > 1:
            # Multiple arguments provided
            # Assume configuration attempt
            return await _pomo_admin(ctx, flags)
        else:
            # Single argument provided, assume channel reference
            channel = await ctx.find_channel(
                ctx.args,
                interactive=True,
                chan_type=discord.ChannelType.voice,
            )
            if channel is None:
                return
    if channel is None:
        # Author is not in a voice channel, and they did not select a channel
        # Display the server timers they can see
        # TODO: Write UI
        timers = Timer.fetch_guild_timers(ctx.guild.id)
        timers = [
            timer for timer in timers
            if timer.channel and timer.channel.permissions_for(ctx.author).view_channel
        ]
        if not timers:
            return await ctx.error_reply(
                "There are no available timers!"
            )
        # Build a summary list
        timer_strings = []
        for timer in timers:
            stage = timer.current_stage
            stage_str = "**{}** minutes focus with **{}** minutes break".format(
                timer.focus_length // 60, timer.break_length // 60
            )
            remaining = (stage.end - utc_now()).total_seconds()

            memberstr = ', '.join(member.mention for member in timer.members[:20])
            if len(timer.members) > 20:
                memberstr += '...'

            timer_strings.append(
                ("{}: {}\n"
                 "Currently in `{}`, with `{:02}:{:02}` remaining.\n"
                 "{}").format(
                     timer.channel.mention,
                     stage_str,
                     stage.name,
                     int(remaining // 3600),
                     int((remaining // 60) % 60),
                     memberstr
                 )
            )

        blocks = [
            '\n\n'.join(timer_strings[i:i+4])
            for i in range(0, len(timer_strings), 4)
        ]
        embeds = [
            discord.Embed(
                title="Pomodoro Timers",
                description=block,
                colour=discord.Colour.orange()
            )
            for block in blocks
        ]
        await ctx.pager(embeds)
    else:
        # We have a channel
        # Get the associated timer
        timer = Timer.fetch_timer(channel.id)
        if timer is None:
            # No timer in this channel
            return await ctx.error_reply(
                f"{channel.mention} doesn't have a timer!"
            )
        else:
            # We have a timer
            # Show the timer status
            await ctx.reply(**await timer.status())


@module.cmd(
    "pomodoro",
    group="Guild Admin",
    desc="Add and configure timers for your study rooms.",
    flags=config_flags
)
async def cmd_pomodoro(ctx, flags):
    """
    Usage``:
        {prefix}pomodoro [channelid] <focus time>, <break time> [channel name]
        {prefix}pomodoro [channelid] [options]
        {prefix}pomodoro [channelid] delete
    Description:
        Get started by joining a study voice channel and writing e.g. `{prefix}pomodoro 50, 10`.
        The timer will start automatically and continue forever.
        See the options and examples below for configuration.
    Options::
        --name: The timer name (as shown in alerts and `{prefix}timer`).
        --channelname: The name of the voice channel, see below for substitutions.
        --threshold: How many focus+break cycles before a member is kicked.
        --text: Text channel to send timer alerts in (defaults to value of `{prefix}config pomodoro_channel`).
    Channel name substitutions::
        {{remaining}}: The time left in the current focus or break session, e.g. `10m left`.
        {{stage}}: The name of the current stage (`FOCUS` or `BREAK`).
        {{name}}: The configured timer name.
        {{pattern}}: The timer pattern in the form `focus/break` (e.g. `50/10`).
    Examples:
        Add a timer to your study room with `50` minutes focus, `10` minutes break.
        > `{prefix}pomodoro 50, 10`
        Add a timer with a custom updating channel name
        > `{prefix}pomodoro 50, 10 {{stage}} {{remaining}} -- {{pattern}} room`
        Change the name on the `{prefix}timer` status
        > `{prefix}pomodoro --name 50/10 study room`
        Change the updating channel name
        > `{prefix}pomodoro --channelname {{remaining}} -- {{name}}`
    """
    await _pomo_admin(ctx, flags)


async def _pomo_admin(ctx, flags):
    # Extract target channel
    if ctx.author.voice:
        channel = ctx.author.voice.channel
    else:
        channel = None

    args = ctx.args
    if ctx.args:
        splits = ctx.args.split(maxsplit=1)
        assume_channel = not splits[0].endswith(',')
        assume_channel = assume_channel and not (channel and len(splits[0]) < 5)
        assume_channel = assume_channel and (splits[0].strip('#<>').isdigit() or len(splits[0]) > 10)
        if assume_channel:
            # Assume first argument is a channel specifier
            channel = await ctx.find_channel(
                splits[0], interactive=True, chan_type=discord.ChannelType.voice
            )
            if not channel:
                # Invalid channel provided
                # find_channel already gave a message, just return silently
                return
            args = splits[1] if len(splits) > 1 else ""

    if not args and not any(flags.values()):
        # No arguments given to the `pomodoro` command.
        # TODO: If we have a channel, replace this with timer setting information
        return await ctx.error_reply(
            f"See `{ctx.best_prefix}help pomodoro` for usage and examples."
        )

    if not channel:
        return await ctx.error_reply(
            f"No channel specified!\n"
            "Please join a voice channel or pass the channel id as the first argument.\n"
            f"See `{ctx.best_prefix}help pomodoro` for usage and examples."
        )

    # Now we have a channel and configuration arguments
    # Next check the user has authority to modify the timer
    if not await guild_admin.run(ctx):
        # TODO: The channel is a room they own?
        return await ctx.error_reply(
            "You need to be a guild admin to set up the pomodoro timers!"
        )

    # Get the associated timer, if it exists
    timer = Timer.fetch_timer(channel.id)

    # Parse required action
    if args.lower() == 'delete':
        if timer:
            await timer.destroy()
            await ctx.embed_reply(
                "Destroyed the timer in {}.".format(channel.mention)
            )
        else:
            await ctx.error_reply(
                "{} doesn't have a timer to delete!".format(channel.mention)
            )
    elif args or timer:
        if args:
            # Any provided arguments should be for setting up a new timer pattern
            # Check the pomodoro channel exists
            if not (timer and timer.text_channel) and not ctx.guild_settings.pomodoro_channel.value:
                return await ctx.error_reply(
                    "Please set the pomodoro alerts channel first, "
                    f"with `{ctx.best_prefix}config pomodoro_channel <channel>`.\n"
                    f"For example: {ctx.best_prefix}config pomodoro_channel {ctx.ch.mention}"
                )
            # First validate input
            try:
                # Ensure no trailing commas
                args = args.strip(',')
                if ',' not in args:
                    raise SafeCancellation("Couldn't parse work and break times!")

                timesplits = args.split(',', maxsplit=1)
                if not timesplits[0].isdigit() or len(timesplits[0]) > 3:
                    raise SafeCancellation(f"Couldn't parse the provided work period length `{timesplits[0]}`.")

                breaksplits = timesplits[1].split(maxsplit=1)
                if not breaksplits[0].isdigit() or len(breaksplits[0]) > 3:
                    raise SafeCancellation(f"Couldn't parse the provided break period length `{breaksplits[0]}`.")
            except SafeCancellation as e:
                usage = discord.Embed(
                    title="Couldn't understand arguments!",
                    colour=discord.Colour.red()
                )
                usage.add_field(
                    name="Usage",
                    value=(
                        f"`{ctx.best_prefix}{ctx.alias} [channelid] <work time>, <break time> [channel name template]"
                    )
                )
                usage.add_field(
                    name="Examples",
                    value=(
                        f"`{ctx.best_prefix}{ctx.alias} 50, 10`\n"
                        f"`{ctx.best_prefix}{ctx.alias} {channel.id} 50, 10`\n"
                        f"`{ctx.best_prefix}{ctx.alias} {channel.id} 50, 10 {{remaining}} - {channel.name}`\n"
                    ),
                    inline=False
                )
                usage.set_footer(
                    text=f"For detailed usage and examples see {ctx.best_prefix}help pomodoro"
                )
                if e.msg:
                    usage.description = e.msg
                return ctx.reply(embed=usage)

            # Input validation complete, assign values
            focus_length = int(timesplits[0])
            break_length = int(breaksplits[0])
            channelname = breaksplits[1].strip() if len(breaksplits) > 1 else None

            # Create or update the timer
            if not timer:
                # Create timer
                # First check number of timers
                timers = Timer.fetch_guild_timers(ctx.guild.id)
                if len(timers) >= MAX_TIMERS_PER_GUILD:
                    return ctx.error_reply(
                        "Cannot create another timer!\n"
                        "This server already has the maximum of `{}` timers.".format(MAX_TIMERS_PER_GUILD)
                    )
                # First check permissions
                if not channel.permissions_for(ctx.guild.me).send_messages:
                    embed = discord.Embed(
                        title="Could not create timer!",
                        description=f"I do not have sufficient guild permissions to join {channel.mention}!",
                        colour=discord.Colour.red()
                    )
                    return await ctx.reply(embed=embed)

                # Create timer
                timer = Timer.create(
                    channel,
                    focus_length * 60,
                    break_length * 60,
                    channel_name=channelname or None,
                    pretty_name=channel.name
                )
                timer.last_seen = {
                    member.id: utc_now()
                    for member in timer.members
                }
                timer.runloop()

                # Post a new status message
                await timer.update_last_status()

                await ctx.embed_reply(
                    f"Started a timer in {channel.mention} with **{focus_length}** minutes focus "
                    f"and **{break_length}** minutes break."
                )
            else:
                # Update timer and restart
                stage = timer.current_stage

                timer.last_seen = {
                    member.id: utc_now()
                    for member in timer.members
                }

                with timer.data.batch_update():
                    timer.data.focus_length = focus_length * 60
                    timer.data.break_length = break_length * 60
                    timer.data.last_started = utc_now()
                    if channelname:
                        timer.data.channel_name = channelname

                await timer.notify_change_stage(stage, timer.current_stage)
                timer.runloop()

                await ctx.embed_reply(
                    f"Started a timer in {channel.mention} with **{focus_length}** "
                    f"minutes focus and **{break_length}** minutes break."
                )

        to_set = []
        if flags['name']:
            # Handle name update
            to_set.append((
                'pretty_name',
                flags['name'],
                f"The timer will now appear as `{flags['name']}` in the status."
            ))
        if flags['threshold']:
            # Handle threshold update
            if not flags['threshold'].isdigit():
                return await ctx.error_reply(
                    "The provided threshold must be a number!"
                )
            to_set.append((
                'inactivity_threshold',
                int(flags['threshold']),
                "Members will be unsubscribed after being inactive for more than `{}` focus+break stages.".format(
                    flags['threshold']
                )
            ))
        if flags['channelname']:
            # Handle channel name update
            to_set.append((
                'channel_name',
                flags['channelname'],
                f"The voice channel name template is now `{flags['channelname']}`."
            ))
        if flags['text']:
            # Handle text channel update
            flag = flags['text']
            if flag.lower() == 'none':
                # Check if there is a default channel
                channel = ctx.guild_settings.pomodoro_channel.value
                if channel:
                    # Unset the channel to the default
                    msg = f"The custom text channel has been unset! (Alerts will be sent to {channel.mention})"
                    to_set.append((
                        'text_channelid',
                        None,
                        msg
                    ))
                    # Remove the last reaction message and send a new one
                    timer.reaction_message = None
                    # Ensure this happens after the data update
                    asyncio.create_task(timer.update_last_status())
                else:
                    return await ctx.error_reply(
                        "The text channel cannot be unset because there is no `pomodoro_channel` set up!\n"
                        f"See `{ctx.best_prefix}config pomodoro_channel` for setting a default pomodoro channel."
                    )
            else:
                # Attempt to parse the provided channel
                channel = await ctx.find_channel(flag, interactive=True, chan_type=discord.ChannelType.text)
                if channel:
                    if not channel.permissions_for(ctx.guild.me.send_messages):
                        return await ctx.error_reply(
                            f"Cannot send pomodoro alerts to {channel.mention}! "
                            "I don't have permission to send messages there."
                        )
                    to_set.append((
                        'text_channelid',
                        channel.id,
                        f"Timer alerts and updates will now be sent to {channel.mention}."
                    ))
                    # Remove the last reaction message and send a new one
                    timer.reaction_message = None
                    # Ensure this happens after the data update
                    asyncio.create_task(timer.update_last_status())
                else:
                    # Ack has already been sent, just ignore
                    return

        if to_set:
            to_update = {item[0]: item[1] for item in to_set}
            timer.data.update(**to_update)
            desc = '\n'.join(f"{tick} {item[2]}" for item in to_set)
            embed = discord.Embed(
                title=f"Timer option{'s' if len(to_update) > 1 else ''} updated!",
                description=desc,
                colour=discord.Colour.green()
            )
            await ctx.reply(embed=embed)
    else:
        # Flags were provided, but there is no timer, and no timer was created
        await ctx.error_reply(
            f"No timer exists in {channel.mention} to set up!\n"
            f"Create one with, for example, ```{ctx.best_prefix}pomodoro {channel.id} 50, 10```"
            f"See `{ctx.best_prefix}help pomodoro` for more examples and usage."
        )

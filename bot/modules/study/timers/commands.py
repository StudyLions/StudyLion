import discord
from cmdClient import Context
from cmdClient.checks import in_guild
from cmdClient.lib import SafeCancellation

from datetime import timedelta

from wards import guild_admin
from utils.lib import utc_now, tick

from ..module import module

from .Timer import Timer


config_flags = ('name==', 'threshold=', 'channelname==')

@module.cmd(
    "timer",
    group="Productivity",
    desc="Display your study room pomodoro timer.",
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
        if len(splits := ctx.args.split()) > 1:
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
    desc="Create and modify the voice channel pomodoro timers.",
    flags=config_flags
)
async def ctx_pomodoro(ctx, flags):
    """
    Usage``:
        {prefix}pomodoro [channelid] <work time>, <break time> [channel name] [options]
        {prefix}pomodoro [channelid] [options]
        {prefix}pomodoro [channelid] delete
    Description:
        ...
    Options::
        --name: The name of the timer as shown in the timer status.
        --channelname: The voice channel name template.
        --threshold: How many work+break sessions before a user is removed.
    Examples``:
        {prefix}pomodoro 50, 10
        ...
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
        if splits[0].strip('#<>').isdigit() or len(splits[0]) > 10:
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
            "Please join a voice channel or pass the id as the first argument.\n"
            f"See `{ctx.best_prefix}help pomodoro` for more usage information."
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
                    f"Started a new `{focus_length}, {break_length}` pomodoro timer in {channel.mention}."
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
                    f"Restarted the pomodoro timer in {channel.mention} as `{focus_length}, {break_length}`."
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


import re
import asyncio
import datetime
import discord

from utils.lib import parse_dur, parse_ranges, multiselect_regex

from .module import module
from .data import reminders
from .reminder import Reminder


reminder_regex = re.compile(
    r"""
    (^)?(?P<type> (?: \b in) | (?: every))
    \s*(?P<duration> (?: day| hour| (?:\d+\s*(?:(?:d|h|m|s)[a-zA-Z]*)?(?:\s|and)*)+))
    (?:(?(1) (?:, | ; | : | \. | to)? | $))
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL
)

reminder_limit = 20


@module.cmd(
    name="remindme",
    desc="Ask me to remind you about important tasks.",
    group="Productivity",
    aliases=('reminders', 'reminder'),
    flags=('remove', 'clear')
)
async def cmd_remindme(ctx, flags):
    """
    Usage``:
        {prefix}remindme in <duration> to <task>
        {prefix}remindme every <duration> to <task>
        {prefix}reminders
        {prefix}reminders --clear
        {prefix}reminders --remove
    Description:
        Ask {ctx.client.user.name} to remind you about important tasks.
    Examples``:
        {prefix}remindme in 2h 20m, Revise chapter 1
        {prefix}remindme every hour, Drink water!
        {prefix}remindme Anatomy class in 8h 20m
    """
    # TODO: (FUTURE) every day at 9:00

    if flags['remove']:
        # Do removal stuff
        rows = reminders.fetch_rows_where(
            userid=ctx.author.id,
            _extra="ORDER BY remind_at ASC"
        )
        if not rows:
            return await ctx.reply("You have no reminders to remove!")

        live = Reminder.fetch(*(row.reminderid for row in rows))

        if not ctx.args:
            lines = []
            num_field = len(str(len(live) - 1))
            for i, reminder in enumerate(live):
                lines.append(
                    "`[{:{}}]` | {}".format(
                        i,
                        num_field,
                        reminder.formatted
                    )
                )

            description = '\n'.join(lines)
            description += (
                "\n\nPlease select the reminders to remove, or type `c` to cancel.\n"
                "(For example, respond with `1, 2, 3` or `1-3`.)"
            )
            embed = discord.Embed(
                description=description,
                colour=discord.Colour.orange(),
                timestamp=datetime.datetime.utcnow()
            ).set_author(
                name="Reminders for {}".format(ctx.author.display_name),
                icon_url=ctx.author.avatar_url
            )

            out_msg = await ctx.reply(embed=embed)

            def check(msg):
                valid = msg.channel == ctx.ch and msg.author == ctx.author
                valid = valid and (re.search(multiselect_regex, msg.content) or msg.content.lower() == 'c')
                return valid

            try:
                message = await ctx.client.wait_for('message', check=check, timeout=60)
            except asyncio.TimeoutError:
                await out_msg.delete()
                await ctx.error_reply("Session timed out. No reminders were deleted.")
                return

            try:
                await out_msg.delete()
                await message.delete()
            except discord.HTTPException:
                pass

            if message.content.lower() == 'c':
                return

            to_delete = [
                live[index].reminderid
                for index in parse_ranges(message.content) if index < len(live)
            ]
        else:
            to_delete = [
                live[index].reminderid
                for index in parse_ranges(ctx.args) if index < len(live)
            ]

        if not to_delete:
            return await ctx.error_reply("Nothing to delete!")

        # Delete the selected reminders
        Reminder.delete(*to_delete)

        # Ack
        await ctx.embed_reply(
            "{tick} Reminder{plural} deleted.".format(
                tick='✅',
                plural='s' if len(to_delete) > 1 else ''
            )
        )
    elif flags['clear']:
        # Do clear stuff
        rows = reminders.fetch_rows_where(
            userid=ctx.author.id,
        )
        if not rows:
            return await ctx.reply("You have no reminders to remove!")

        Reminder.delete(*(row.reminderid for row in rows))
        await ctx.embed_reply(
            "{tick} Reminders cleared.".format(
                tick='✅',
            )
        )
    elif ctx.args:
        # Add a new reminder

        content = None
        duration = None
        repeating = None

        # First parse it
        match = re.search(reminder_regex, ctx.args)
        if match:
            repeating = match.group('type').lower() == 'every'

            duration_str = match.group('duration').lower()
            if duration_str.isdigit():
                duration = int(duration_str)
            elif duration_str == 'day':
                duration = 24 * 60 * 60
            elif duration_str == 'hour':
                duration = 60 * 60
            else:
                duration = parse_dur(duration_str)

            content = (ctx.args[:match.start()] + ctx.args[match.end():]).strip()
            if content.startswith('to '):
                content = content[3:].strip()
        else:
            # Legacy parsing, without requiring "in" at the front
            splits = ctx.args.split(maxsplit=1)
            if len(splits) == 2 and splits[0].isdigit():
                repeating = False
                duration = int(splits[0]) * 60
                content = splits[1].strip()

        # Sanity checking
        if not duration or not content:
            return await ctx.error_reply(
                "Sorry, I didn't understand your reminder!\n"
                "See `{prefix}help remindme` for usage and examples.".format(prefix=ctx.best_prefix)
            )

        # Don't allow rapid repeating reminders
        if repeating and duration < 10 * 60:
            return await ctx.error_reply(
                "You can't have a repeating reminder shorter than `10` minutes!"
            )

        # Check the user doesn't have too many reminders already
        count = reminders.select_one_where(
            userid=ctx.author.id,
            select_columns=("COUNT(*)",)
        )[0]
        if count > reminder_limit:
            return await ctx.error_reply(
                "Sorry, you have reached your maximum of `{}` reminders!".format(reminder_limit)
            )

        # Create reminder
        reminder = Reminder.create(
            userid=ctx.author.id,
            content=content,
            message_link=ctx.msg.jump_url,
            interval=duration if repeating else None,
            remind_at=datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)
        )

        # Schedule reminder
        reminder.schedule()

        # Ack
        embed = discord.Embed(
            title="Reminder Created!",
            colour=discord.Colour.orange(),
            description="Got it! I will remind you <t:{}:R>.".format(reminder.timestamp),
            timestamp=datetime.datetime.utcnow()
        )
        await ctx.reply(embed=embed)
    elif ctx.alias.lower() == 'remindme':
        # Show hints about adding reminders
        ...
    else:
        # Show formatted list of reminders
        rows = reminders.fetch_rows_where(
            userid=ctx.author.id,
            _extra="ORDER BY remind_at ASC"
        )
        if not rows:
            return await ctx.reply("You have no reminders!")

        live = Reminder.fetch(*(row.reminderid for row in rows))

        lines = []
        num_field = len(str(len(live) - 1))
        for i, reminder in enumerate(live):
            lines.append(
                "`[{:{}}]` | {}".format(
                    i,
                    num_field,
                    reminder.formatted
                )
            )

        description = '\n'.join(lines)
        embed = discord.Embed(
            description=description,
            colour=discord.Colour.orange(),
            timestamp=datetime.datetime.utcnow()
        ).set_author(
            name="{}'s reminders".format(ctx.author.display_name),
            icon_url=ctx.author.avatar_url
        ).set_footer(
            text=(
                "Click a reminder twice to jump to the context!\n"
                "For more usage and examples see {}help reminders"
            ).format(ctx.best_prefix)
        )

        await ctx.reply(embed=embed)

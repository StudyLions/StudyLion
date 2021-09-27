import re
import asyncio
import discord
import datetime

from cmdClient.checks import in_guild
from cmdClient.lib import SafeCancellation

from data import NULL
from utils.lib import parse_dur, strfdur, parse_ranges
from wards import is_guild_admin
from core.data import lions
from settings import GuildSettings

from .module import module
from .data import study_badges, guild_role_cache, new_study_badges
from .badge_tracker import _update_guild_badges


_multiselect_regex = re.compile(
    r"^([0-9, -]+)$",
    re.DOTALL | re.IGNORECASE | re.VERBOSE
)


@module.cmd(
    "studybadges",
    group="Guild Configuration",
    desc="View or configure the server study badges.",
    aliases=('studyroles', 'studylevels'),
    flags=('add', 'remove', 'clear', 'refresh')
)
@in_guild()
async def cmd_studybadges(ctx, flags):
    """
    Usage``:
        {prefix}studybadges
        {prefix}studybadges [--add] <role>, <duration>
        {prefix}studybadges --remove
        {prefix}studybadges --remove <role>
        {prefix}studybadges --remove <badge index>
        {prefix}studybadges --clear
        {prefix}studybadges --refresh
    Description:
        View or modify the study badges in this guild.

        *Modification requires administrator permissions.*
    Flags::
        add: Add new studybadges (each line is added as a separate badge).
        remove: Remove badges. With no arguments, opens a selection menu.
        clear: Remove all study badges.
        refresh: Make sure everyone's study badges are up to date.
    Examples``:
        {prefix}studybadges Lion Cub, 100h
        {prefix}studybadges --remove Lion Cub
    """
    if flags['refresh']:
        await ensure_admin(ctx)

        # Count members who need updating.
        # Note that we don't get the rows here in order to avoid clashing with the auto-updater
        update_count = new_study_badges.select_one_where(
            guildid=ctx.guild.id,
            select_columns=('COUNT(*)',)
        )[0]

        if not update_count:
            # No-one needs updating
            await ctx.reply("All study badges are up to date!")
            return
        else:
            out_msg = await ctx.reply("Updating `{}` members (this may take a while)...".format(update_count))

        # Fetch actual update rows
        update_rows = new_study_badges.select_where(
            guildid=ctx.guild.id
        )

        # Update data first
        lions.update_many(
            *((row['current_study_badgeid'], ctx.guild.id, row['userid']) for row in update_rows),
            set_keys=('last_study_badgeid',),
            where_keys=('guildid', 'userid')
        )

        # Then apply the role updates and send notifications as usual
        await _update_guild_badges(ctx.guild, update_rows)

        await out_msg.edit("Refresh complete! All study badges are up to date.")
    elif flags['clear'] or flags['remove']:
        # Make sure that the author is an admin before modifying the roles
        await ensure_admin(ctx)

        # Pre-fetch the list of roles
        guild_roles = study_badges.fetch_rows_where(guildid=ctx.guild.id, _extra="ORDER BY required_time ASC")

        # Input handling, parse or get the list of rows to delete
        to_delete = []
        if flags['remove']:
            if ctx.args:
                if ctx.args.isdigit() and 0 < int(ctx.args) <= len(guild_roles):
                    # Assume it is a badge index
                    row = guild_roles[int(ctx.args) - 1]
                else:
                    # Assume the input is a role string
                    # Get the collection of roles to search
                    roleids = (row.roleid for row in guild_roles)
                    roles = (ctx.guild.get_role(roleid) for roleid in roleids)
                    roles = [role for role in roles if role is not None]
                    role = await ctx.find_role(ctx.args, interactive=True, collection=roles, allow_notfound=False)
                    index = roles.index(role)
                    row = guild_roles[index]

                # We now have a row to delete
                to_delete = [row]
            else:
                # Multi-select the badges to remove
                out_msg = await show_badge_list(
                    ctx,
                    desc="Please select the badge(s) to delete, or type `c` to cancel.",
                    guild_roles=guild_roles
                )

                def check(msg):
                    valid = msg.channel == ctx.ch and msg.author == ctx.author
                    valid = valid and (re.search(_multiselect_regex, msg.content) or msg.content.lower() == 'c')
                    return valid

                try:
                    message = await ctx.client.wait_for('message', check=check, timeout=60)
                except asyncio.TimeoutError:
                    await out_msg.delete()
                    await ctx.error_reply("Session timed out. No study badges were deleted.")
                    return

                try:
                    await out_msg.delete()
                    await message.delete()
                except discord.HTTPException:
                    pass

                if message.content.lower() == 'c':
                    return

                to_delete = [
                    guild_roles[index-1]
                    for index in parse_ranges(message.content) if index <= len(guild_roles)
                ]
        elif flags['clear']:
            if not await ctx.ask("Are you sure you want to delete **all** study badges in this server?"):
                return
            to_delete = guild_roles

        # In some cases we may come out with no valid rows, in this case cancel.
        if not to_delete:
            return await ctx.error_reply("No matching badges, nothing to do!")

        # Count the affected users
        affected_count = lions.select_one_where(
            guildid=ctx.guild.id,
            last_study_badgeid=[row.badgeid for row in to_delete],
            select_columns=('COUNT(*)',)
        )[0]

        # Delete the rows
        study_badges.delete_where(badgeid=[row.badgeid for row in to_delete])

        # Also update the cached guild roles
        guild_role_cache.pop((ctx.guild.id, ), None)
        study_badges.queries.for_guild(ctx.guild.id)

        # Immediately refresh the member data, only for members with NULL badgeid
        update_rows = new_study_badges.select_where(
            guildid=ctx.guild.id,
            last_study_badgeid=NULL
        )

        if update_rows:
            lions.update_many(
                *((row['current_study_badgeid'], ctx.guild.id, row['userid']) for row in update_rows),
                set_keys=('last_study_badgeid',),
                where_keys=('guildid', 'userid')
            )

            # Launch the update task for these members, so that they get the correct new roles
            asyncio.create_task(_update_guild_badges(ctx.guild, update_rows, notify=False, log=False))

        # Ack the deletion
        count = len(to_delete)
        roles = [ctx.guild.get_role(row.roleid) for row in to_delete]
        if count == len(guild_roles):
            await ctx.embed_reply("All study badges deleted.")
            log_embed = discord.Embed(
                title="Study badges cleared!",
                description="{} cleared the guild study badges. `{}` members affected.".format(
                    ctx.author.mention,
                    affected_count
                )
            )
        elif count == 1:
            badge_name = roles[0].name if roles[0] else strfdur(to_delete[0].required_time)
            await show_badge_list(
                ctx,
                desc="✅ Removed the **{}** badge.".format(badge_name)
            )
            log_embed = discord.Embed(
                title="Study badge removed!",
                description="{} removed the badge **{}**. `{}` members affected.".format(
                    ctx.author.mention,
                    badge_name,
                    affected_count
                )
            )
        else:
            await show_badge_list(
                ctx,
                desc="✅ `{}` badges removed.".format(count)
            )
            log_embed = discord.Embed(
                title="Study badges removed!",
                description="{} removed `{}` badges. `{}` members affected.".format(
                    ctx.author.mention,
                    count,
                    affected_count
                )
            )

        # Post to the event log
        event_log = GuildSettings(ctx.guild.id).event_log.value
        if event_log:
            # TODO Error handling? Or improve the post method?
            log_embed.timestamp = datetime.datetime.utcnow()
            log_embed.colour = discord.Colour.orange()
            await event_log.send(embed=log_embed)

        # Delete the roles (after asking first)
        roles = [role for role in roles if role is not None]
        if roles:
            if await ctx.ask("Do you also want to remove the associated guild roles?"):
                tasks = [
                    asyncio.create_task(role.delete()) for role in roles
                ]
                results = await asyncio.gather(
                    *tasks,
                    return_exceptions=True
                )
                bad_roles = [role for role, task in zip(roles, tasks) if task.exception()]
                if bad_roles:
                    await ctx.embed_reply(
                        "Couldn't delete the following roles:\n{}".format(
                            '\n'.join(bad_role.mention for bad_role in bad_roles)
                        )
                    )
                else:
                    await ctx.embed_reply("Deleted `{}` roles.".format(len(roles)))
    elif ctx.args:
        # Ensure admin perms for modification
        await ensure_admin(ctx)

        guild_roles = study_badges.fetch_rows_where(guildid=ctx.guild.id, _extra="ORDER BY required_time ASC")

        # Parse the input
        lines = ctx.args.splitlines()
        results = [await parse_level(ctx, line) for line in lines]
        current_times = set(row.required_time for row in guild_roles)

        # Split up the provided lines into levels to add and levels to edit
        to_add = [result for result in results if result[0] not in current_times]
        to_edit = [result for result in results if result[0] in current_times]

        # Apply changes to database
        if to_add:
            study_badges.insert_many(
                *((ctx.guild.id, time, role.id) for time, role in to_add),
                insert_keys=('guildid', 'required_time', 'roleid')
            )
        if to_edit:
            study_badges.update_many(
                *((role.id, ctx.guild.id, time) for time, role in to_edit),
                set_keys=('roleid',),
                where_keys=('guildid', 'required_time')
            )

        # Also update the cached guild roles
        guild_role_cache.pop((ctx.guild.id, ), None)
        study_badges.queries.for_guild(ctx.guild.id)

        # Ack changes
        if to_add and to_edit:
            desc = "{tick} `{num_add}` badges added and `{num_edit}` updated."
        elif to_add:
            desc = "{tick} `{num_add}` badges added."
        elif to_edit:
            desc = "{tick} `{num_edit}` badges updated."

        desc = desc.format(
            tick='✅',
            num_add=len(to_add),
            num_edit=len(to_edit)
        )

        await show_badge_list(ctx, desc)

        # Count members who need new study badges
        # Note that we don't get the rows here in order to avoid clashing with the auto-updater
        update_count = new_study_badges.select_one_where(
            guildid=ctx.guild.id,
            select_columns=('COUNT(*)',)
        )[0]

        if not update_count:
            # No-one needs updating
            return

        if update_count > 20:
            # Confirm whether we want to update now
            resp = await ctx.ask(
                "`{}` members need their study badge roles updated, "
                "which will occur automatically for each member when they next study.\n"
                "Do you want to refresh the roles immediately instead? This may take a while!"
            )
            if not resp:
                return

        # Fetch actual update rows
        update_rows = new_study_badges.select_where(
            guildid=ctx.guild.id
        )

        # Update data first
        lions.update_many(
            *((row['current_study_badgeid'], ctx.guild.id, row['userid']) for row in update_rows),
            set_keys=('last_study_badgeid',),
            where_keys=('guildid', 'userid')
        )

        # Then apply the role updates and send notifications as usual
        await _update_guild_badges(ctx.guild, update_rows)

        # TODO: Progress bar? Probably not needed since we have the event log
        # TODO: Ask about notifications?
    else:
        guild_roles = study_badges.fetch_rows_where(guildid=ctx.guild.id, _extra="ORDER BY required_time ASC")

        # Just view the current study levels
        if not guild_roles:
            return await ctx.reply("There are no study badges set up!")

        # TODO: You are at... this much to next level..
        await show_badge_list(ctx, guild_roles=guild_roles)


async def parse_level(ctx, line):
    line = line.strip()

    if ',' in line:
        splits = [split.strip() for split in line.split(',', maxsplit=1)]
    elif line.startswith('"') and '"' in line[1:]:
        splits = [split.strip() for split in line[1:].split('"', maxsplit=1)]
    else:
        splits = [split.strip() for split in line.split(maxsplit=1)]

    if not line or len(splits) != 2 or not splits[1][0].isdigit():
        raise SafeCancellation(
            "**Level Syntax:** `<role>, <required_time>`, for example `Lion Cub, 200h`."
        )

    if splits[1].isdigit():
        # No units! Assume hours
        time = int(splits[1]) * 3600
    else:
        time = parse_dur(splits[1])

    role_str = splits[0]
    # TODO maybe add Y.. yes to all
    role = await ctx.find_role(role_str, create=True, interactive=True, allow_notfound=False)
    return time, role


async def ensure_admin(ctx):
    if not is_guild_admin(ctx.author):
        raise SafeCancellation("Only guild admins can modify the server study badges!")


async def show_badge_list(ctx, desc=None, guild_roles=None):
    if guild_roles is None:
        guild_roles = study_badges.fetch_rows_where(guildid=ctx.guild.id, _extra="ORDER BY required_time ASC")

    # Generate the time range strings
    time_strings = []
    first_time = guild_roles[0].required_time
    if first_time == 0:
        prev_time_str = '0'
        prev_time_hour = False
    else:
        prev_time_str = strfdur(guild_roles[0].required_time)
        prev_time_hour = not (guild_roles[0].required_time % 3600)
    for row in guild_roles[1:]:
        time = row.required_time
        time_str = strfdur(time)
        time_hour = not (time % 3600)
        if time_hour and prev_time_hour:
            time_strings.append(
                "{} - {}".format(prev_time_str[:-1], time_str)
            )
        else:
            time_strings.append(
                "{} - {}".format(prev_time_str, time_str)
            )
        prev_time_str = time_str
        prev_time_hour = time_hour
    time_strings.append(
        "≥ {}".format(prev_time_str)
    )

    # Pair the time strings with their roles
    pairs = [
        (time_string, row.roleid)
        for time_string, row in zip(time_strings, guild_roles)
    ]

    # pairs = [
    #     (strfdur(row.required_time), row.study_role)
    #     for row in guild_roles
    # ]

    # Split the pairs into blocks
    pair_blocks = [pairs[i:i+10] for i in range(0, len(pairs), 10)]

    # Format the blocks into strings
    blocks = []
    for i, pair_block in enumerate(pair_blocks):
        dig_len = (i * 10 + len(pair_block)) // 10 + 1
        blocks.append('\n'.join(
            "`[{:<{}}]` | <@&{}> **({})**".format(
                i * 10 + j + 1,
                dig_len,
                role,
                time_string,
            ) for j, (time_string, role) in enumerate(pair_block)
        ))

    # Compile the strings into pages
    pages = [
        discord.Embed(
            title="Study Badges in {}! \nStudy more to rank up!".format(ctx.guild.name),
            description="{}\n\n{}".format(desc, block) if desc else block
        ) for block in blocks
    ]

    # Output and page the pages
    return await ctx.pager(pages)

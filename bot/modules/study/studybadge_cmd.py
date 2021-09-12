import re
import asyncio
import discord

from cmdClient.checks import in_guild
from cmdClient.lib import SafeCancellation

from utils.lib import parse_dur, strfdur, parse_ranges
from wards import is_guild_admin
from core.data import lions

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
        {prefix}studybadges --clear
        {prefix}studybadges --refresh
    Description:
        View or modify the study badges in this guild.

        *Modification requires administrator permissions.*
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
    elif flags['clear']:
        await ensure_admin(ctx)
        if not await ctx.input("Are you sure you want to delete **all** study badges in this server?"):
            return
        study_badges.delete_where(guildid=ctx.guild.id)
        await ctx.reply("All study badges have been removed.")
        # TODO: Offer to delete roles
    elif flags['remove']:
        await ensure_admin(ctx)
        guild_roles = study_badges.fetch_rows_where(guildid=ctx.guild.id, _extra="ORDER BY required_time ASC")
        if ctx.args:
            # TODO: Handle role input
            ...
        else:
            # TODO: Interactive multi-selector
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

            try:
                await out_msg.delete()
                await message.delete()
            except discord.HTTPException:
                pass

            if message.content.lower() == 'c':
                return

            rows = [guild_roles[index-1] for index in parse_ranges(message.content) if index <= len(guild_roles)]
            if rows:
                study_badges.delete_where(badgeid=[row.badgeid for row in rows])
            else:
                return await ctx.error_reply("Nothing to delete!")

            if len(rows) == len(guild_roles):
                await ctx.reply("All study badges deleted.")
            else:
                await show_badge_list(
                    ctx,
                    desc="`{}` badge{} removed.".format(len(rows), 's' if len(rows) > 1 else '')
                )
            # TODO: Offer to delete roles
            # TODO: Offer to refresh
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
        guild_role_cache.pop(ctx.guild.id, None)
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
            resp = await ctx.input(
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

    # if line.startswith('"') and '"' in line[1:]:
    #     splits = [split.strip() for split in line[1:].split('"', maxsplit=1)]
    # else:
    #     splits = [split.strip() for split in line.split(maxsplit=1)]
    # if not line or len(splits) != 2 or not splits[1][0].isdigit():
    #     raise SafeCancellation(
    #         "**Level Syntax:** `<role> <required_time>`, for example `Cub 200h`."
    #     )
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

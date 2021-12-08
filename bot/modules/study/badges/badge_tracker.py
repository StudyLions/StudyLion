import datetime
import traceback
import logging
import asyncio
import contextlib

import discord

from meta import client
from data.conditions import GEQ
from core.data import lions
from utils.lib import strfdur
from settings import GuildSettings

from ..module import module
from .data import new_study_badges, study_badges


guild_locks = {}  # guildid -> Lock


@contextlib.asynccontextmanager
async def guild_lock(guildid):
    """
    Per-guild lock held while the study badges are being updated.
    This should not be used to lock the data modifications, as those are synchronous.
    Primarily for reporting and so that the member information (e.g. roles) stays consistent
    through reading and manipulation.
    """
    # Create the lock if it hasn't been registered already
    if guildid in guild_locks:
        lock = guild_locks[guildid]
    else:
        lock = guild_locks[guildid] = asyncio.Lock()

    await lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


async def update_study_badges(full=False):
    while not client.is_ready():
        await asyncio.sleep(1)

    client.log(
        "Running global study badge update.".format(
        ),
        context="STUDY_BADGE_UPDATE",
        level=logging.DEBUG
    )
    # TODO: Consider db procedure for doing the update and returning rows

    # Retrieve member rows with out of date study badges
    if not full and client.appdata.last_study_badge_scan is not None:
        update_rows = new_study_badges.select_where(
            _timestamp=GEQ(client.appdata.last_study_badge_scan or 0),
            _extra="OR session_start IS NOT NULL"
        )
    else:
        update_rows = new_study_badges.select_where()

    if not update_rows:
        client.appdata.last_study_badge_scan = datetime.datetime.utcnow()
        return

    # Batch and fire guild updates
    current_guildid = None
    current_guild = None
    guild_buffer = []
    updated_guilds = set()
    for row in update_rows:
        if row['guildid'] != current_guildid:
            if current_guild:
                # Fire guild updater
                asyncio.create_task(_update_guild_badges(current_guild, guild_buffer))
                updated_guilds.add(current_guild.id)

            guild_buffer = []
            current_guildid = row['guildid']
            current_guild = client.get_guild(row['guildid'])

        if current_guild:
            guild_buffer.append(row)

    if current_guild:
        # Fire guild updater
        asyncio.create_task(_update_guild_badges(current_guild, guild_buffer))
        updated_guilds.add(current_guild.id)

    # Update the member study badges in data
    lions.update_many(
        *((row['current_study_badgeid'], row['guildid'], row['userid'])
          for row in update_rows if row['guildid'] in updated_guilds),
        set_keys=('last_study_badgeid',),
        where_keys=('guildid', 'userid'),
        cast_row='(NULL::int, NULL::int, NULL::int)'
    )

    # Update the app scan time
    client.appdata.last_study_badge_scan = datetime.datetime.utcnow()


async def _update_guild_badges(guild, member_rows, notify=True, log=True):
    """
    Notify, update, and log role changes for a single guild.
    Expects a valid `guild` and a list of Rows of `new_study_badges`.
    """
    async with guild_lock(guild.id):
        client.log(
            "Running guild badge update for guild '{guild.name}' (gid:{guild.id}) "
            "with `{count}` rows to update.".format(
                guild=guild,
                count=len(member_rows)
            ),
            context="STUDY_BADGE_UPDATE",
            level=logging.DEBUG,
            post=False
        )

        # Set of study role ids in this guild, usually from cache
        guild_roles = {
            roleid: guild.get_role(roleid)
            for roleid in study_badges.queries.for_guild(guild.id)
        }

        log_lines = []
        flags_used = set()
        tasks = []
        for row in member_rows:
            # Fetch member
            # TODO: Potential verification issue
            member = guild.get_member(row['userid'])

            if member:
                tasks.append(
                    asyncio.create_task(
                        _update_member_roles(row, member, guild_roles, log_lines, flags_used, notify)
                    )
                )

        # Post to the event log, in multiple pages if required
        event_log = GuildSettings(guild.id).event_log.value
        if tasks:
            task_blocks = (tasks[i:i+20] for i in range(0, len(tasks), 20))
            for task_block in task_blocks:
                # Execute the tasks
                await asyncio.gather(*task_block)

                # Post to the log if needed
                if log and event_log:
                    desc = "\n".join(log_lines)
                    embed = discord.Embed(
                        title="Study badge{} earned!".format('s' if len(log_lines) > 1 else ''),
                        description=desc,
                        colour=discord.Colour.orange(),
                        timestamp=datetime.datetime.utcnow()
                    )
                    if flags_used:
                        flag_desc = {
                            '!': "`!` Could not add/remove badge role. **Check permissions!**",
                            '*': "`*` Could not message member.",
                            'x': "`x` Couldn't find role to add/remove!"
                        }
                        flag_lines = '\n'.join(desc for flag, desc in flag_desc.items() if flag in flags_used)
                        embed.add_field(
                            name="Legend",
                            value=flag_lines
                        )
                    try:
                        await event_log.send(embed=embed)
                    except discord.HTTPException:
                        # Nothing we can really do
                        pass

                # Flush the log collection pointers
                log_lines.clear()
                flags_used.clear()

                # Wait so we don't get ratelimited
                await asyncio.sleep(0.5)

    # Debug log completion
    client.log(
        "Completed guild badge update for guild '{guild.name}' (gid:{guild.id})".format(
            guild=guild,
        ),
        context="STUDY_BADGE_UPDATE",
        level=logging.DEBUG,
        post=False
    )


async def _update_member_roles(row, member, guild_roles, log_lines, flags_used, notify):
    guild = member.guild

    # Logging flag chars
    flags = []

    # Add new study role
    # First fetch the roleid using the current_study_badgeid
    new_row = study_badges.fetch(row['current_study_badgeid']) if row['current_study_badgeid'] else None

    # Fetch actual role from the precomputed guild roles
    to_add = guild_roles.get(new_row.roleid, None) if new_row else None
    if to_add:
        # Actually add the role
        try:
            await member.add_roles(
                to_add,
                atomic=True,
                reason="Updating study badge."
            )
        except discord.HTTPException:
            flags.append('!')
    elif new_row:
        flags.append('x')

    # Remove other roles, start by trying the last badge role
    old_row = study_badges.fetch(row['last_study_badgeid']) if row['last_study_badgeid'] else None

    member_roleids = set(role.id for role in member.roles)
    if old_row and old_row.roleid in member_roleids:
        # The last level role exists, try to remove it
        try:
            await member.remove_roles(
                guild_roles.get(old_row.roleid),
                atomic=True
            )
        except discord.HTTPException:
            # Couldn't remove the role
            flags.append('!')
    else:
        # The last level role doesn't exist or the member doesn't have it
        # Remove all leveled roles they have
        current_roles = (
            role for roleid, role in guild_roles.items()
            if roleid in member_roleids and (not to_add or roleid != to_add.id)
        )
        if current_roles:
            try:
                await member.remove_roles(
                    *current_roles,
                    atomic=True,
                    reason="Updating study badge."
                )
            except discord.HTTPException:
                # Couldn't remove one or more of the leveled roles
                flags.append('!')

    # Send notification to member
    # TODO: Config customisation
    if notify and new_row and (old_row is None or new_row.required_time > old_row.required_time):
        embed = discord.Embed(
            title="New Study Badge!",
            description="Congratulations! You have earned {}!".format(
                "**{}**".format(to_add.name) if to_add else "a new study badge!"
            ),
            timestamp=datetime.datetime.utcnow(),
            colour=discord.Colour.orange()
        ).set_footer(text=guild.name, icon_url=guild.icon_url)
        try:
            await member.send(embed=embed)
        except discord.HTTPException:
            flags.append('*')

    # Add to event log message
    if new_row:
        new_role_str = "earned <@&{}> **({})**".format(new_row.roleid, strfdur(new_row.required_time))
    else:
        new_role_str = "lost their study badge!"
    log_lines.append(
        "<@{}> {} {}".format(
            row['userid'],
            new_role_str,
            "`[{}]`".format(''.join(flags)) if flags else "",
        )
    )
    if flags:
        flags_used.update(flags)


async def study_badge_tracker():
    """
    Runloop for the study badge updater.
    """
    while True:
        try:
            await update_study_badges()
        except Exception:
            # Unknown exception. Catch it so the loop doesn't die.
            client.log(
                "Error while updating study badges! "
                "Exception traceback follows.\n{}".format(
                    traceback.format_exc()
                ),
                context="STUDY_BADGE_TRACKER",
                level=logging.ERROR
            )
        # Long delay since this is primarily needed for external modifications
        # or badge updates while studying
        await asyncio.sleep(60)


async def update_member_studybadge(member):
    """
    Checks and (if required) updates the study badge for a single member.
    """
    update_rows = new_study_badges.select_where(
        guildid=member.guild.id,
        userid=member.id
    )
    if update_rows:
        # Debug log the update
        client.log(
            "Updating study badge for user '{member.name}' (uid:{member.id}) "
            "in guild '{member.guild.name}' (gid:{member.guild.id}).".format(
                member=member
            ),
            context="STUDY_BADGE_UPDATE",
            level=logging.DEBUG
        )

        # Update the data first
        lions.update_where({'last_study_badgeid': update_rows[0]['current_study_badgeid']},
                           guildid=member.guild.id, userid=member.id)

        # Run the update task
        await _update_guild_badges(member.guild, update_rows)


@module.launch_task
async def launch_study_badge_tracker(client):
    asyncio.create_task(study_badge_tracker())

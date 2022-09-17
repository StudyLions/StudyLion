import asyncio
import discord
from collections import defaultdict

from meta import client
from core import Lion
from settings import GuildSettings

from .settings import autoroles, bot_autoroles, role_persistence
from .data import past_member_roles


# Locks to avoid storing the roles while adding them
# The locking is cautious, leaving data unchanged upon collision
locks = defaultdict(asyncio.Lock)


@client.add_after_event('member_join')
async def join_role_tracker(client, member):
    """
    Add autoroles or saved roles as needed.
    """
    guild = member.guild
    if not guild.me.guild_permissions.manage_roles:
        # We can't manage the roles here, don't try to give/restore the member roles
        return

    async with locks[(guild.id, member.id)]:
        if role_persistence.get(guild.id).value and client.data.lions.fetch((guild.id, member.id)):
            # Lookup stored roles
            role_rows = past_member_roles.select_where(
                guildid=guild.id,
                userid=member.id
            )
            # Identify roles from roleids
            roles = (guild.get_role(row['roleid']) for row in role_rows)
            # Remove non-existent roles
            roles = (role for role in roles if role is not None)
            # Remove roles the client can't add
            roles = [role for role in roles if role < guild.me.top_role]
            if roles:
                try:
                    await member.add_roles(
                        *roles,
                        reason="Restoring saved roles.",
                    )
                except discord.HTTPException:
                    # This shouldn't ususally happen, but there are valid cases where it can
                    # E.g. the user left while we were restoring their roles
                    pass
                # Event log!
                GuildSettings(guild.id).event_log.log(
                    "Restored the following roles for returning member {}:\n{}".format(
                        member.mention,
                        ', '.join(role.mention for role in roles)
                    ),
                    title="Saved roles restored"
                )
        else:
            # Add autoroles
            roles = bot_autoroles.get(guild.id).value if member.bot else autoroles.get(guild.id).value
            # Remove roles the client can't add
            roles = [role for role in roles if role < guild.me.top_role]
            if roles:
                try:
                    await member.add_roles(
                        *roles,
                        reason="Adding autoroles.",
                    )
                except discord.HTTPException:
                    # This shouldn't ususally happen, but there are valid cases where it can
                    # E.g. the user left while we were adding autoroles
                    pass
                # Event log!
                GuildSettings(guild.id).event_log.log(
                    "Gave {} the guild autoroles:\n{}".format(
                        member.mention,
                        ', '.join(role.mention for role in roles)
                    ),
                    titles="Autoroles added"
                )


@client.add_after_event('member_remove')
async def left_role_tracker(client, member):
    """
    Delete and re-store member roles when they leave the server.
    """
    if (member.guild.id, member.id) in locks and locks[(member.guild.id, member.id)].locked():
        # Currently processing a join event
        # Which means the member left while we were adding their roles
        # Cautiously return, not modifying the saved role data
        return

    # Delete existing member roles for this user
    # NOTE: Not concurrency-safe
    past_member_roles.delete_where(
        guildid=member.guild.id,
        userid=member.id,
    )
    if role_persistence.get(member.guild.id).value:
        # Make sure the user has an associated lion, so we can detect when they rejoin
        Lion.fetch(member.guild.id, member.id)

        # Then insert the current member roles
        values = [
            (member.guild.id, member.id, role.id)
            for role in member.roles
            if not role.is_bot_managed() and not role.is_integration() and not role.is_default()
        ]
        if values:
            past_member_roles.insert_many(
                *values,
                insert_keys=('guildid', 'userid', 'roleid')
            )

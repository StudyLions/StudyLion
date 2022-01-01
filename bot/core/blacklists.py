"""
Guild, user, and member blacklists.
"""
from collections import defaultdict
import cachetools.func

from data import tables
from meta import client

from .module import module


@cachetools.func.ttl_cache(ttl=300)
def guild_blacklist():
    """
    Get the guild blacklist
    """
    rows = tables.global_guild_blacklist.select_where()
    return set(row['guildid'] for row in rows)


@cachetools.func.ttl_cache(ttl=300)
def user_blacklist():
    """
    Get the global user blacklist.
    """
    rows = tables.global_user_blacklist.select_where()
    return set(row['userid'] for row in rows)


@module.init_task
def load_ignored_members(client):
    """
    Load the ignored members.
    """
    ignored = defaultdict(set)
    rows = tables.ignored_members.select_where()

    for row in rows:
        ignored[row['guildid']].add(row['userid'])

    client.objects['ignored_members'] = ignored

    if rows:
        client.log(
            "Loaded {} ignored members across {} guilds.".format(
                len(rows),
                len(ignored)
            ),
            context="MEMBER_BLACKLIST"
        )


@module.init_task
def attach_client_blacklists(client):
    client.guild_blacklist = guild_blacklist
    client.user_blacklist = user_blacklist


@module.launch_task
async def leave_blacklisted_guilds(client):
    """
    Launch task to leave any blacklisted guilds we are in.
    """
    to_leave = [
        guild for guild in client.guilds
        if guild.id in guild_blacklist()
    ]

    for guild in to_leave:
        await guild.leave()

    if to_leave:
        client.log(
            "Left {} blacklisted guilds!".format(len(to_leave)),
            context="GUILD_BLACKLIST"
        )


@client.add_after_event('guild_join')
async def check_guild_blacklist(client, guild):
    """
    Guild join event handler to check whether the guild is blacklisted.
    If so, leaves the guild.
    """
    # First refresh the blacklist cache
    if guild.id in guild_blacklist():
        await guild.leave()
        client.log(
            "Automatically left blacklisted guild '{}' (gid:{}) upon join.".format(guild.name, guild.id),
            context="GUILD_BLACKLIST"
        )

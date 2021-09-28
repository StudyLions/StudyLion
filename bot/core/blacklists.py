"""
Guild, user, and member blacklists.

NOTE: The pre-loading methods are not shard-optimised.
"""
from collections import defaultdict

from data import tables
from meta import client

from .module import module


@module.init_task
def load_guild_blacklist(client):
    """
    Load the blacklisted guilds.
    """
    rows = tables.global_guild_blacklist.select_where()
    client.objects['blacklisted_guilds'] = set(row['guildid'] for row in rows)
    if rows:
        client.log(
            "Loaded {} blacklisted guilds.".format(len(rows)),
            context="GUILD_BLACKLIST"
        )


@module.init_task
def load_user_blacklist(client):
    """
    Load the blacklisted users.
    """
    rows = tables.global_user_blacklist.select_where()
    client.objects['blacklisted_users'] = set(row['userid'] for row in rows)
    if rows:
        client.log(
            "Loaded {} globally blacklisted users.".format(len(rows)),
            context="USER_BLACKLIST"
        )


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


@module.launch_task
async def leave_blacklisted_guilds(client):
    """
    Launch task to leave any blacklisted guilds we are in.
    Assumes that the blacklisted guild list has been initialised.
    """
    # Cache to avoic repeated lookups
    blacklisted = client.objects['blacklisted_guilds']

    to_leave = [
        guild for guild in client.guilds
        if guild.id in blacklisted
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
    if guild.id in client.objects['blacklisted_guilds']:
        await guild.leave()
        client.log(
            "Automatically left blacklisted guild '{}' (gid:{}) upon join.".format(guild.name, guild.id),
            context="GUILD_BLACKLIST"
        )

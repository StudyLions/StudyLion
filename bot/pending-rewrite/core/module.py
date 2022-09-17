import logging
import asyncio

from meta import client, conf
from settings import GuildSettings, UserSettings

from LionModule import LionModule

from .lion import Lion


module = LionModule("Core")


async def _lion_sync_loop():
    while True:
        while not client.is_ready():
            await asyncio.sleep(1)

        client.log(
            "Running lion data sync.",
            context="CORE",
            level=logging.DEBUG,
            post=False
        )

        Lion.sync()
        await asyncio.sleep(conf.bot.getint("lion_sync_period"))


@module.init_task
def setting_initialisation(client):
    """
    Execute all Setting initialisation tasks from GuildSettings and UserSettings.
    """
    for setting in GuildSettings.settings.values():
        setting.init_task(client)

    for setting in UserSettings.settings.values():
        setting.init_task(client)


@module.launch_task
async def preload_guild_configuration(client):
    """
    Loads the plain guild configuration for all guilds the client is part of into data.
    """
    guildids = [guild.id for guild in client.guilds]
    if guildids:
        rows = client.data.guild_config.fetch_rows_where(guildid=guildids)
        client.log(
            "Preloaded guild configuration for {} guilds.".format(len(rows)),
            context="CORE_LOADING"
        )


@module.launch_task
async def preload_studying_members(client):
    """
    Loads the member data for all members who are currently in voice channels.
    """
    userids = list(set(member.id for guild in client.guilds for ch in guild.voice_channels for member in ch.members))
    if userids:
        users = client.data.user_config.fetch_rows_where(userid=userids)
        members = client.data.lions.fetch_rows_where(userid=userids)
        client.log(
            "Preloaded data for {} user with {} members.".format(len(users), len(members)),
            context="CORE_LOADING"
        )


# Removing the sync loop in favour of the studybadge sync.
# @module.launch_task
# async def launch_lion_sync_loop(client):
#     asyncio.create_task(_lion_sync_loop())


@module.unload_task
async def final_lion_sync(client):
    Lion.sync()

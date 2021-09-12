import logging
import asyncio

from meta import client, conf
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


@module.launch_task
async def launch_lion_sync_loop(client):
    asyncio.create_task(_lion_sync_loop())


@module.unload_task
async def final_lion_sync(client):
    Lion.sync()

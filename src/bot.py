import asyncio
import logging

import aiohttp
import discord
from discord.ext import commands

from meta import LionBot, conf, sharding, appname, shard_talk
from meta.app import shardname
from meta.logger import log_context, log_action_stack, logging_context, setup_main_logger
from meta.context import ctx_bot

from data import Database

from babel.translator import LeoBabel, ctx_translator

from constants import DATA_VERSION


for name in conf.config.options('LOGGING_LEVELS', no_defaults=True):
    logging.getLogger(name).setLevel(conf.logging_levels[name])


setup_main_logger()


logger = logging.getLogger(__name__)

db = Database(conf.data['args'])


async def main():
    log_action_stack.set(["Initialising"])
    logger.info("Initialising StudyLion")

    intents = discord.Intents.all()
    intents.members = True
    intents.message_content = True
    intents.presences = False

    async with await db.connect():
        version = await db.version()
        if version.version != DATA_VERSION:
            error = f"Data model version is {version}, required version is {DATA_VERSION}! Please migrate."
            logger.critical(error)
            raise RuntimeError(error)

        translator = LeoBabel()
        ctx_translator.set(translator)

        async with aiohttp.ClientSession() as session:
            async with LionBot(
                command_prefix=commands.when_mentioned,
                intents=intents,
                appname=appname,
                shardname=shardname,
                db=db,
                config=conf,
                initial_extensions=[
                    'utils', 'core', 'analytics',
                    'modules',
                    'babel',
                    'tracking.voice', 'tracking.text',
                ],
                web_client=session,
                app_ipc=shard_talk,
                testing_guilds=conf.bot.getintlist('admin_guilds'),
                shard_id=sharding.shard_number,
                shard_count=sharding.shard_count,
                help_command=None,
                translator=translator
            ) as lionbot:
                ctx_bot.set(lionbot)
                try:
                    with logging_context(context=f"APP: {appname}"):
                        logger.info("StudyLion initialised, starting!", extra={'action': 'Starting'})
                        await lionbot.start(conf.bot['TOKEN'])
                except asyncio.CancelledError:
                    with logging_context(context=f"APP: {appname}", action="Shutting Down"):
                        logger.info("StudyLion closed, shutting down.", exc_info=True)


def _main():
    from signal import SIGINT, SIGTERM

    loop = asyncio.get_event_loop()
    main_task = asyncio.ensure_future(main())
    for signal in [SIGINT, SIGTERM]:
        loop.add_signal_handler(signal, main_task.cancel)
    try:
        loop.run_until_complete(main_task)
    finally:
        loop.close()
        logging.shutdown()


if __name__ == '__main__':
    _main()

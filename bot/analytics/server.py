import asyncio
import logging

from meta import conf, appname
from meta.logger import log_context, log_action_stack, logging_context, log_app
from meta.ipc import AppClient

from data import Database

from .events import command_event_handler, guild_event_handler, voice_event_handler
from .data import AnalyticsData


logger = logging.getLogger(__name__)

for name in conf.config.options('LOGGING_LEVELS', no_defaults=True):
    logging.getLogger(name).setLevel(conf.logging_levels[name])


db = Database(conf.data['args'])


async def main():
    log_action_stack.set(['Analytics'])
    log_app.set(conf.analytics['appname'])

    async with await db.connect():
        db.load_registry(AnalyticsData())
        analytic_talk = AppClient(
            conf.analytics['appname'],
            appname,
            {'host': conf.analytics['server_host'], 'port': int(conf.analytics['server_port'])},
            {'host': conf.appipc['server_host'], 'port': int(conf.appipc['server_port'])}
        )
        await analytic_talk.connect()
        cmd = await command_event_handler.attach(analytic_talk)
        guild = await guild_event_handler.attach(analytic_talk)
        voice = await voice_event_handler.attach(analytic_talk)
        logger.info("Finished initialising, waiting for events.")
        await asyncio.gather(cmd._consumer_task, guild._consumer_task, voice._consumer_task)


if __name__ == '__main__':
    asyncio.run(main())

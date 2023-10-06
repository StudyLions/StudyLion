import asyncio
import logging
from typing import Optional

from meta import conf, appname
from meta.logger import log_context, log_action_stack, logging_context, log_app, log_wrap, setup_main_logger
from meta.ipc import AppClient
from meta.app import appname_from_shard
from meta.sharding import shard_count

from data import Database

from .events import command_event_handler, guild_event_handler, voice_event_handler
from .snapshot import shard_snapshot, ShardSnapshot
from .data import AnalyticsData


logger = logging.getLogger(__name__)

for name in conf.config.options('LOGGING_LEVELS', no_defaults=True):
    logging.getLogger(name).setLevel(conf.logging_levels[name])


class AnalyticsServer:
    # TODO: Move these to the config
    # How often to request snapshots
    snap_period = 900
    # How soon after a snapshot failure (e.g. not all shards online) to retry
    snap_retry_period = 60

    def __init__(self) -> None:
        self.db = Database(conf.data['args'])
        self.data = self.db.load_registry(AnalyticsData())

        self.event_handlers = [
            command_event_handler,
            guild_event_handler,
            voice_event_handler
        ]

        self.talk = AppClient(
            conf.analytics['appname'],
            appname,
            {'host': conf.analytics['server_host'], 'port': int(conf.analytics['server_port'])},
            {'host': conf.appipc['server_host'], 'port': int(conf.appipc['server_port'])}
        )
        self.talk_shard_snapshot = self.talk.register_route()(shard_snapshot)

        self._snap_task: Optional[asyncio.Task] = None

    async def attach_event_handlers(self):
        for handler in self.event_handlers:
            await handler.attach(self.talk)

    @log_wrap(action='Snap')
    async def take_snapshot(self):
        # Check if all the shards are registered on shard_talk
        expected_peers = [appname_from_shard(i) for i in range(0, shard_count)]
        if missing := [peer for peer in expected_peers if peer not in self.talk.peers]:
            # We are missing peer(s)!
            logger.warning(
                f"Analytics could not take snapshot because peers are missing: {', '.join(missing)}"
            )
            return False

        # Everyone is here, ask for shard snapshots
        results = await self.talk_shard_snapshot().broadcast()

        # Make sure everyone sent results and there were no exceptions (e.g. concurrency)
        failed = not isinstance(results, dict)
        failed = failed or any(
            result is None or isinstance(result, Exception) for result in results.values()
        )
        if failed:
            # This should essentially never happen
            # Either some of the shards could not make a snapshot (e.g. Discord client issues)
            # or they disconnected in the process.
            logger.warning(
                f"Analytics could not take snapshot because some peers failed! Partial snapshot: {results}"
            )
            return False

        logger.debug(f"Creating snapshot from: {results}")

        # Now we have a dictionary of shard snapshots, aggregate, pull in remaining data, and store.
        # TODO Possibly move this out into snapshots.py?
        aggregate = {field: 0 for field in ShardSnapshot._fields}
        for result in results.values():
            for field, num in result._asdict().items():
                aggregate[field] += num

        row = await self.data.Snapshots.create(
            appname=appname,
            guild_count=aggregate['guild_count'],
            member_count=aggregate['member_count'],
            user_count=aggregate['user_count'],
            in_voice=aggregate['voice_count'],
        )
        logger.info(f"Created snapshot: {row.data!r}")
        return True

    @log_wrap(action='SnapLoop')
    async def snapshot_loop(self):
        while True:
            try:
                result = await self.take_snapshot()
                if result:
                    await asyncio.sleep(self.snap_period)
                else:
                    logger.info("Snapshot failed, retrying after %d seconds", self.snap_retry_period)
                    await asyncio.sleep(self.snap_retry_period)
            except asyncio.CancelledError:
                logger.info("Snapshot loop cancelled, closing.")
                return
            except Exception:
                logger.exception(
                    "Unhandled exception during snapshot loop. Ignoring and continuing cautiously."
                )
                await asyncio.sleep(self.snap_retry_period)

    async def run(self):
        setup_main_logger()
        log_action_stack.set(['Analytics'])
        log_app.set(conf.analytics['appname'])

        async with self.db.open():
            await self.talk.connect()
            await self.attach_event_handlers()
            self._snap_task = asyncio.create_task(self.snapshot_loop())
            await asyncio.gather(*(handler._consumer_task for handler in self.event_handlers))


if __name__ == '__main__':
    server = AnalyticsServer()
    asyncio.run(server.run())

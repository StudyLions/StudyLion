"""
appname: str
    The base identifer for this application.
    This identifies which services the app offers.
shardname: str
    The specific name of the running application.
    Only one process should be connecteded with a given appname.
    For the bot apps, usually specifies the shard id and shard number.
"""
# TODO: Find a better schema for these. We use appname for shard_talk, do we need it for data?

from . import sharding, conf
from .logger import log_app
from .ipc.client import AppClient
from .args import args


appname = conf.data['appid']
appid = appname  # backwards compatibility


def appname_from_shard(shardid):
    appname = f"{conf.data['appid']}_{sharding.shard_count:02}_{shardid:02}"
    return appname


def shard_from_appname(appname: str):
    return int(appname.rsplit('_', maxsplit=1)[-1])


shardname = appname_from_shard(sharding.shard_number)

log_app.set(shardname)


shard_talk = AppClient(
    shardname,
    {'host': args.host, 'port': args.port},
    {'host': conf.appipc['server_host'], 'port': int(conf.appipc['server_port'])}
)


@shard_talk.register_route()
async def ping():
    return "Pong!"

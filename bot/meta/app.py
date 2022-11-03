from . import sharding, conf
from .logger import log_app
from .ipc.client import AppClient
from .args import args


def appname_from_shard(shardid):
    appname = f"{conf.data['appid']}_{sharding.shard_count:02}_{shardid:02}"
    return appname


def shard_from_appname(appname: str):
    return int(appname.rsplit('_', maxsplit=1)[-1])


if sharding.sharded:
    appname = appname_from_shard(sharding.shard_number)
else:
    appname = conf.data['appid']

log_app.set(appname)


shard_talk = AppClient(
    appname,
    {'host': args.host, 'port': args.port},
    {'host': conf.appipc['server_host'], 'port': int(conf.appipc['server_port'])}
)


@shard_talk.register_route()
async def ping():
    return "Pong!"

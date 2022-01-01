from meta import client, conf, log, sharding

from data import tables

import core # noqa

import modules  # noqa

# Load and attach app specific data
if sharding.sharded:
    appname = f"{conf.bot['data_appid']}_{sharding.shard_count}_{sharding.shard_number}"
else:
    appname = conf.bot['data_appid']
client.appdata = core.data.meta.fetch_or_create(appname)

client.data = tables

# Initialise all modules
client.initialise_modules()

# Log readyness and execute
log("Initial setup complete, logging in", context='SETUP')
client.run(conf.bot['TOKEN'])

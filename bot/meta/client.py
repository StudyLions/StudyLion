from discord import Intents
from cmdClient.cmdClient import cmdClient

from .config import conf
from .sharding import shard_number, shard_count
from LionContext import LionContext

# Initialise client
owners = [int(owner) for owner in conf.bot.getlist('owners')]
intents = Intents.all()
intents.presences = False
client = cmdClient(
    prefix=conf.bot['prefix'],
    owners=owners,
    intents=intents,
    shard_id=shard_number,
    shard_count=shard_count,
    baseContext=LionContext
)
client.conf = conf

from discord import Intents
from cmdClient.cmdClient import cmdClient

from .config import Conf

from constants import CONFIG_FILE

# Initialise config
conf = Conf(CONFIG_FILE)

# Initialise client
owners = [int(owner) for owner in conf.bot.getlist('owners')]
intents = Intents.all()
intents.presences = False
client = cmdClient(prefix=conf.bot['prefix'], owners=owners, intents=intents)
client.conf = conf

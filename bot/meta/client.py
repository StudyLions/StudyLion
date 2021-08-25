from cmdClient.cmdClient import cmdClient

from .config import Conf

from constants import CONFIG_FILE

# Initialise config
conf = Conf(CONFIG_FILE)

# Initialise client
owners = [int(owner) for owner in conf.bot.getlist('owners')]
client = cmdClient(prefix=conf.bot['prefix'], owners=owners)
client.conf = conf

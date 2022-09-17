from discord import Intents
from cmdClient.cmdClient import cmdClient

from . import patches
from .interactions import InteractionType
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


# TODO: Could include client id here, or app id, to avoid multiple handling.
NOOP_ID = 'NOOP'


@client.add_after_event('interaction_create')
async def handle_noop_interaction(client, interaction):
    if interaction.interaction_type in (InteractionType.MESSAGE_COMPONENT, InteractionType.MODAL_SUBMIT):
        if interaction.custom_id == NOOP_ID:
            interaction.ack()

from meta.client import client
from settings.user_settings import UserSettings
from utils.lib import utc_now
from meta.config import conf

import topgg
from .utils import *

@client.event
async def on_dbl_vote(data):
    """An event that is called whenever someone votes for the bot on Top.gg."""
    client.log(f"Received a vote: \n{data}", context='Topgg')

    db.topggvotes.insert(
        userid=data['user'],
        boostedTimestamp = utc_now()
    )

    await send_user_dm(data['user'])
    
    if UserSettings.settings.vote_remainder.value:
        create_remainder(data['user'])

    if data["type"] == "test":
        return client.dispatch("dbl_test", data)
    

@client.event
async def on_dbl_test(data):
    """An event that is called whenever someone tests the webhook system for your bot on Top.gg."""
    client.log(f"Received a test vote:\n{data}", context='Topgg')


def init_webhook():
    client.topgg_webhook = topgg.WebhookManager(client).dbl_webhook(conf.bot.get("topgg_route"), conf.bot.get("topgg_password"))
    client.topgg_webhook.run(conf.bot.get("topgg_port"))    

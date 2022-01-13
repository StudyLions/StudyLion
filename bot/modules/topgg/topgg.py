from meta import client
import discord
import topgg

# client.log("test")

import topgg

# This example uses topggpy's webhook system.
client.topgg_webhook = topgg.WebhookManager(client).dbl_webhook("/dblwebhook", "nopassword123")

# The port must be a number between 1024 and 49151.
client.topgg_webhook.run(5000)  # this method can be awaited as well


@client.event
async def on_dbl_vote(data):
    """An event that is called whenever someone votes for the bot on Top.gg."""
    client.log(f"Received a vote:\n{data}")
    if data["type"] == "test":
        # this is roughly equivalent to
        # `return await on_dbl_test(data)` in this case
        return client.dispatch("dbl_test", data)


@client.event
async def on_dbl_test(data):
    """An event that is called whenever someone tests the webhook system for your bot on Top.gg."""
    client.log(f"Received a test vote:\n{data}")
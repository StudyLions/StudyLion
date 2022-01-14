from meta import client
import discord
import topgg
import datetime

from .module import module
from wards import guild_admin
from cmdClient.Context import Context
from . import data as db

# This example uses topggpy's webhook system.
client.topgg_webhook = topgg.WebhookManager(client).dbl_webhook("/dblwebhook", "nopassword123")

# The port must be a number between 1024 and 49151.
client.topgg_webhook.run(5000)  # this method can be awaited as well


@client.event
async def on_dbl_vote(data):
    """An event that is called whenever someone votes for the bot on Top.gg."""
    client.log(f"Received a vote: \n{data}")

    db.topggvotes.insert(
        userid=data['user'],
        boostedTimestamp = datetime.datetime.utcnow()
    )

    await send_user_dm(data['user'])

    if data["type"] == "test":
        return client.dispatch("dbl_test", data)
    

@client.event
async def on_dbl_test(data):
    """An event that is called whenever someone tests the webhook system for your bot on Top.gg."""
    client.log(f"Received a test vote:\n{data}")


async def send_user_dm(userid):
    # Send the message, if possible
    if not (user := client.get_user(userid)):
        try:
            user = await client.fetch_user(userid)
        except discord.HTTPException:
            pass
    if user:
        try:
            await user.send("Thankyou for upvoting.\n https://cdn.discordapp.com/attachments/908283085999706153/930559064323268618/unknown.png")
        except discord.HTTPException:
            # Nothing we can really do here. Maybe tell the user about their reminder next time?
            pass


from LionContext import register_reply_callback, unregister_reply_callback

@module.launch_task
async def register_hook(client):
    client.log("register_reply_hook " )

    register_reply_callback(reply)


@module.unload_task
async def unregister_hook(client):
    client.log("register_reply_hook " )

    unregister_reply_callback(reply)


def reply(util_func, *args, **kwargs):
    # *args will have LionContext
    # **kwargs should have the actual reply() call's extra arguments

    args = list(args)

    if 'embed' in kwargs:
        kwargs['embed'].add_field(
            name="\u200b",
            value=(
                f"Upvote me to get 🌟**+25% Economy Boost**🌟 - Use `!vote`"
            ),
            inline=False        
        )
    elif 'content' in args and args['content']:
        args['content'] += "\n\nUpvote me to get 🌟**+25% Economy Boost**🌟 - Use `!vote`"
    elif len(args) > 1:
        args[1] += "\n\nUpvote me to get 🌟**+25% Economy Boost**🌟 - Use `!vote`"
    else:
        args['content'] = "\n\nUpvote me to get 🌟**+25% Economy Boost**🌟 - Use `!vote`"

    args = tuple(args)
    client.log('test')

    return [args, kwargs]


@module.cmd(
    "forcevote",
    desc="Simulate Topgg Vote.",
    group="Guild Admin",
    aliases=('debugvote', 'topggvote')
)
@guild_admin()
async def cmd_forcevote(ctx):
    """
    Usage``:
        {prefix}forcevote
    Description:
        Simulate Topgg Vote without actually a confirmation from Topgg site.

        Can be used for force a vote for testing or if topgg has an error or production time bot error.
    """
    target = ctx.author
    # Identify the target
    if ctx.args:
        if not ctx.msg.mentions:
            return await ctx.error_reply("Please mention a user to simulate a vote!")
        target = ctx.msg.mentions[0]


    await on_dbl_vote({"user": target.id, "type": "test"})
    return await ctx.reply('Topgg vote simulation successful on {}'.format(target))
    
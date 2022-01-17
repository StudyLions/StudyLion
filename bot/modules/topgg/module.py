from LionModule import LionModule
from LionContext import register_reply_callback, unregister_reply_callback
from meta.client import client

from .utils import *
from .webhook import init_webhook

module = LionModule("Topgg")

@module.launch_task
async def register_hook(client):
    client.log("register_reply_hook " )

    init_webhook()
    register_reply_callback(reply)

@module.unload_task
async def unregister_hook(client):
    client.log("register_reply_hook " )

    unregister_reply_callback(reply)


def reply(util_func, *args, **kwargs):
    # *args will have LionContext
    # **kwargs should have the actual reply() call's extra arguments

    if not get_last_voted_timestamp(args[0].author.id):
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

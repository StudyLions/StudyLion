from multiprocessing import context
from LionModule import LionModule
from LionContext import register_reply_callback, unregister_reply_callback
from bot.data.conditions import NOT
from meta.client import client
from core.lion import register_addcoins_callback, unregister_addcoins_callback

from .utils import *
from .webhook import init_webhook

module = LionModule("Topgg")

upvote_info = "You have a boost available {}, to support our project and earn **25% more LionCoins** type `{}vote` {}"

@module.launch_task
async def register_hook(client):
    init_webhook()
    register_reply_callback(reply)
    register_addcoins_callback(cb_addCoins)

    client.log("Registered LionContext reply util hook.", context="Topgg" )

@module.unload_task
async def unregister_hook(client):
    unregister_reply_callback(reply)
    unregister_addcoins_callback(cb_addCoins)
    
    client.log("Unregistered LionContext reply util hook.", context="Topgg" )


def reply(util_func, *args, **kwargs):
    # *args will have LionContext
    # **kwargs should have the actual reply() call's extra arguments

    if not get_last_voted_timestamp(args[0].author.id):
        args = list(args)

        upvote_info_formatted = upvote_info.format(lion_yayemote, args[0].best_prefix, lion_loveemote)

        if 'embed' in kwargs:
            kwargs['embed'].add_field(
                name="\u200b",
                value=(
                    upvote_info_formatted
                ),
                inline=False        
            )
        elif 'content' in args and args['content']:
            args['content'] += '\n\n' + upvote_info_formatted
        elif len(args) > 1:
            args[1] += '\n\n' + upvote_info_formatted
        else:
            args['content'] = '\n\n' + upvote_info_formatted

        args = tuple(args)

    return [args, kwargs]


def cb_addCoins(self, amount, flush, ignorebonus):

    client.log('cb_addCoins hook with amount={} ignorebonux={}'.format(amount, ignorebonus), context='Topgg')

    if not ignorebonus and amount > 0 and get_last_voted_timestamp(self.userid):
        amount *= 1.25
        client.log('cb_addCoins with bonus={}'.format(amount), context='Topgg')

    return [self, amount, flush, ignorebonus]
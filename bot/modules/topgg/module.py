from LionModule import LionModule
from LionContext import LionContext
from core.lion import Lion

from .utils import get_last_voted_timestamp, lion_loveemote, lion_yayemote
from .webhook import init_webhook

module = LionModule("Topgg")

upvote_info = "You have a boost available {}, to support our project and earn **25% more LionCoins** type `{}vote` {}"


@module.launch_task
async def attach_topgg_webhook(client):
    if client.shard_id == 0:
        init_webhook()
        client.log("Attached top.gg voiting webhook.", context="TOPGG")

@module.launch_task
async def register_hook(client):
    LionContext.reply.add_wrapper(topgg_reply_wrapper)
    Lion.register_economy_bonus(economy_bonus)

    client.log("Loaded top.gg hooks.", context="TOPGG")


@module.unload_task
async def unregister_hook(client):
    Lion.unregister_economy_bonus(economy_bonus)
    LionContext.reply.remove_wrapper(topgg_reply_wrapper.__name__)

    client.log("Unloaded top.gg hooks.", context="TOPGG")


async def topgg_reply_wrapper(func, *args, suggest_vote=True, **kwargs):
    if suggest_vote and not get_last_voted_timestamp(args[0].author.id):
        upvote_info_formatted = upvote_info.format(lion_yayemote, args[0].best_prefix, lion_loveemote)

        if 'embed' in kwargs:
            # Add message as an extra embed field
            kwargs['embed'].add_field(
                name="\u200b",
                value=(
                    upvote_info_formatted
                ),
                inline=False
            )
        else:
            # Add message to content
            if 'content' in kwargs and kwargs['content'] and len(kwargs['content']) + len(upvote_info_formatted) < 1998:
                kwargs['content'] += '\n\n' + upvote_info_formatted
            elif len(args) > 1 and len(args[1]) + len(upvote_info_formatted) < 1998:
                args = list(args)
                args[1] += '\n\n' + upvote_info_formatted
            else:
                kwargs['content'] = upvote_info_formatted

    return await func(*args, **kwargs)


def economy_bonus(lion):
    return 1.25 if get_last_voted_timestamp(lion.userid) else 1

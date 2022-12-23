import logging
import time
import traceback
import discord

from LionModule import LionModule

from meta import client
from utils.ratelimits import RateLimit

from ..client import EmptyResponse, request


class PluginModule(LionModule):
    def cmd(self, name, **kwargs):
        # Remove any existing command with this name
        for module in client.modules:
            for i, cmd in enumerate(module.cmds):
                if cmd.name == name:
                    module.cmds.pop(i)

        return super().cmd(name, **kwargs)

    async def on_exception(self, ctx, exception):
        try:
            raise exception
        except (ConnectionError, EmptyResponse) as e:
            full_traceback = traceback.format_exc()
            only_error = "".join(traceback.TracebackException.from_exception(e).format_exception_only())

            client.log(
                ("Caught a communication exception while "
                 "executing command '{cmdname}' from module '{module}' "
                 "from user '{message.author}' (uid:{message.author.id}) "
                 "in guild '{message.guild}' (gid:{guildid}) "
                 "in channel '{message.channel}' (cid:{message.channel.id}).\n"
                 "Message Content:\n"
                 "{content}\n"
                 "{traceback}\n\n"
                 "{flat_ctx}").format(
                     cmdname=ctx.cmd.name,
                     module=ctx.cmd.module.name,
                     message=ctx.msg,
                     guildid=ctx.guild.id if ctx.guild else None,
                     content='\n'.join('\t' + line for line in ctx.msg.content.splitlines()),
                     traceback=full_traceback,
                     flat_ctx=ctx.flatten()
                 ),
                context="mid:{}".format(ctx.msg.id),
                level=logging.ERROR
            )
            error_embed = discord.Embed(title="Sorry, something went wrong!")
            error_embed.description = (
                "An unexpected error occurred while communicating with our rendering server!\n"
                "Our development team has been notified, and the issue should be fixed soon.\n"
            )
            if logging.getLogger().getEffectiveLevel() < logging.INFO:
                error_embed.add_field(
                    name="Exception",
                    value="`{}`".format(only_error)
                )

            await ctx.reply(embed=error_embed)
        except Exception:
            await super().on_exception(ctx, exception)


module = PluginModule("GUI")

ratelimit = RateLimit(5, 30)

logging.getLogger('PIL').setLevel(logging.WARNING)


@module.launch_task
async def ping_server(client):
    start = time.time()
    try:
        await request('ping')
    except Exception:
        logging.error(
            "Failed to ping the rendering server!",
            exc_info=True
        )
    else:
        end = time.time()
        client.log(
            f"Rendering server responded in {end-start:.6f} seconds!",
            context="GUI INIT",
        )

import asyncio
import traceback
import logging
import discord

from cmdClient import Command, Module, FailedCheck
from cmdClient.lib import SafeCancellation

from meta import log


class LionCommand(Command):
    """
    Subclass to allow easy attachment of custom hooks and structure to commands.
    """
    allow_before_ready = False


class LionModule(Module):
    """
    Custom module for Lion systems.

    Adds command wrappers and various event handlers.
    """
    name = "Base Lion Module"

    def __init__(self, name, baseCommand=LionCommand):
        super().__init__(name, baseCommand)

        self.unload_tasks = []

    def unload_task(self, func):
        """
        Decorator adding an unload task for deactivating the module.
        Should sync unsaved transactions and finalise user interaction.
        If possible, should also remove attached data and handlers.
        """
        self.unload_tasks.append(func)
        log("Adding unload task '{}'.".format(func.__name__), context=self.name)
        return func

    async def unload(self, client):
        """
        Run the unloading tasks.
        """
        log("Unloading module.", context=self.name, post=False)
        for task in self.unload_tasks:
            log("Running unload task '{}'".format(task.__name__),
                context=self.name, post=False)
            await task(client)

    async def launch(self, client):
        """
        Launch hook.
        Executed in `client.on_ready`.
        Must set `ready` to `True`, otherwise all commands will hang.
        Overrides the parent launcher to not post the log as a discord message.
        """
        if not self.ready:
            log("Running launch tasks.", context=self.name, post=False)

            for task in self.launch_tasks:
                log("Running launch task '{}'.".format(task.__name__),
                    context=self.name, post=False)
                await task(client)

            self.ready = True
        else:
            log("Already launched, skipping launch.", context=self.name, post=False)

    async def pre_command(self, ctx):
        """
        Lion pre-command hook.
        """
        if not self.ready and not ctx.cmd.allow_before_ready:
            try:
                await ctx.embed_reply(
                    "I am currently restarting! Please try again in a couple of minutes."
                )
            except discord.HTTPException:
                pass
            raise SafeCancellation(details="Module '{}' is not ready.".format(self.name))

        # Check global user blacklist
        if ctx.author.id in ctx.client.objects['blacklisted_users']:
            raise SafeCancellation(details='User is blacklisted.')

        if ctx.guild:
            # Check that the channel and guild still exists
            if not ctx.client.get_guild(ctx.guild.id) or not ctx.guild.get_channel(ctx.ch.id):
                raise SafeCancellation(details='Command channel is no longer reachable.')

            # Check global guild blacklist
            if ctx.guild.id in ctx.client.objects['blacklisted_guilds']:
                raise SafeCancellation(details='Guild is blacklisted.')

            # Check guild's own member blacklist
            if ctx.author.id in ctx.client.objects['ignored_members'][ctx.guild.id]:
                raise SafeCancellation(details='User is ignored in this guild.')

            # Check channel permissions are sane
            if not ctx.ch.permissions_for(ctx.guild.me).send_messages:
                raise SafeCancellation(details='I cannot send messages in this channel.')
            if not ctx.ch.permissions_for(ctx.guild.me).embed_links:
                await ctx.reply("I need permission to send embeds in this channel before I can run any commands!")
                raise SafeCancellation(details='I cannot send embeds in this channel.')

        # Start typing
        await ctx.ch.trigger_typing()

    async def on_exception(self, ctx, exception):
        try:
            raise exception
        except (FailedCheck, SafeCancellation):
            # cmdClient generated and handled exceptions
            raise exception
        except (asyncio.CancelledError, asyncio.TimeoutError):
            # Standard command and task exceptions, cmdClient will also handle these
            raise exception
        except discord.Forbidden:
            # Unknown uncaught Forbidden
            try:
                # Attempt a general error reply
                await ctx.reply("I don't have enough channel or server permissions to complete that command here!")
            except discord.Forbidden:
                # We can't send anything at all. Exit quietly, but log.
                full_traceback = traceback.format_exc()
                log(("Caught an unhandled 'Forbidden' while "
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
                    level=logging.WARNING)
        except Exception as e:
            # Unknown exception!
            full_traceback = traceback.format_exc()
            only_error = "".join(traceback.TracebackException.from_exception(e).format_exception_only())

            log(("Caught an unhandled exception while "
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
                level=logging.ERROR)

            error_embed = discord.Embed(title="Something went wrong!")
            error_embed.description = (
                "An unexpected error occurred while processing your command!\n"
                "Our development team has been notified, and the issue should be fixed soon.\n"
            )
            if logging.getLogger().getEffectiveLevel() < logging.INFO:
                error_embed.add_field(
                    name="Exception",
                    value="`{}`".format(only_error)
                )

            await ctx.reply(embed=error_embed)

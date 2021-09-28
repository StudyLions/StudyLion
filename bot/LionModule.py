from cmdClient import Command, Module
from cmdClient.lib import SafeCancellation

from meta import log


class LionCommand(Command):
    """
    Subclass to allow easy attachment of custom hooks and structure to commands.
    """
    ...


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
        # Check global guild blacklist
        if ctx.guild.id in ctx.client.objects['blacklisted_guilds']:
            raise SafeCancellation

        # Check global user blacklist
        if ctx.author.id in ctx.client.objects['blacklisted_users']:
            raise SafeCancellation

        if ctx.guild:
            # Check guild's own member blacklist
            if ctx.author.id in ctx.client.objects['ignored_members'][ctx.guild.id]:
                raise SafeCancellation

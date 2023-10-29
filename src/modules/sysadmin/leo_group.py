from discord.app_commands import Group, Command
from discord.ext.commands import HybridCommand

from meta import LionCog


class LeoGroup(Group, name='leo'):
    """
    Base command group for all Leo system admin commands.
    """
    ...


"""
TODO:
    This will take some work to get working.
    We want to be able to specify a command in a cog
    as a subcommand of a group command in a different cog,
    or even a different extension.
    Unfortunately, this really messes with the hotloading and unloading,
    and may require overriding LionCog.__new__.

    We also have to answer some implementation decisions,
    such as what happens when the child command cog gets unloaded/reloaded?
    What happens when the group command gets unloaded/reloaded?

    Well, if the child cog gets unloaded, it makes sense to detach the commands.
    The commands should keep their binding to the defining cog,
    the parent command is mainly relevant for the CommandTree, which we have control of anyway..

    If the parent cog gets unloaded, it makes sense to unload all the subcommands, if possible.

    Now technically, it shouldn't _matter_ where the child command is defined.
    The Tree is in charge (or should be) of arranging parent commands and subcommands.
    The Group class should just specify some optional extra properties or wrappers
    to apply to the subcommands.
    So perhaps we can just extend Hybrid command to actually pass in a parent...
    Or specify a _string_ as the parent, which gets mapped with a group class
    if it exists.. but it doesn't need to exist.
"""


class LeoCog(LionCog):
    """
    Abstract container cog acting as a manager for the LeoGroup above.
    """
    def __init__(self, bot):
        self.bot = bot
        self.commands = []
        self.group = LeoGroup()

    def attach(self, *commands):
        """
        Attach the given commands to the LeoGroup group.
        """
        for command in commands:
            if isinstance(command, Command):
                # Classic app command, attach as-is
                cmd = command
            elif isinstance(command, HybridCommand):
                cmd = command.app_command
            else:
                raise ValueError(
                    f"Command must by 'app_commands.Command' or 'commands.HybridCommand' not {cmd.__class_}"
                )
            self.group.add_command(cmd)

        self.commands.extend(commands)

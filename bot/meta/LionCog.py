from typing import Any

from discord.ext.commands import Cog
from discord.ext import commands as cmds


class LionCog(Cog):
    # A set of other cogs that this cog depends on
    depends_on: set['LionCog'] = set()
    _placeholder_groups_: set[str]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        cls._placeholder_groups_ = set()

        for base in reversed(cls.__mro__):
            for elem, value in base.__dict__.items():
                if isinstance(value, cmds.HybridGroup) and hasattr(value, '_placeholder_group_'):
                    cls._placeholder_groups_.add(value.name)

    def __new__(cls, *args: Any, **kwargs: Any):
        # Patch to ensure no placeholder groups are in the command list
        self = super().__new__(cls)
        self.__cog_commands__ = [
            command for command in self.__cog_commands__ if command.name not in cls._placeholder_groups_
        ]
        return self

    async def _inject(self, bot, *args, **kwargs):
        if self.depends_on:
            not_found = {cogname for cogname in self.depends_on if not bot.get_cog(cogname)}
            raise ValueError(f"Could not load cog '{self.__class__.__name__}', dependencies missing: {not_found}")

        return await super()._inject(bot, *args, *kwargs)

    @classmethod
    def placeholder_group(cls, group: cmds.HybridGroup):
        group._placeholder_group_ = True
        return group

    def crossload_group(self, placeholder_group: cmds.HybridGroup, target_group: cmds.HybridGroup):
        """
        Crossload a placeholder group's commands into the target group
        """
        if not isinstance(placeholder_group, cmds.HybridGroup) or not isinstance(target_group, cmds.HybridGroup):
            raise ValueError("Placeholder and target groups my be HypridGroups.")
        if placeholder_group.name not in self._placeholder_groups_:
            raise ValueError("Placeholder group was not registered! Stopping to avoid duplicates.")
        if target_group.app_command is None:
            raise ValueError("Target group has no app_command to crossload into.")

        for command in placeholder_group.commands:
            placeholder_group.remove_command(command.name)
            target_group.remove_command(command.name)
            acmd = command.app_command._copy_with(parent=target_group.app_command, binding=self)
            command.app_command = acmd
            target_group.add_command(command)

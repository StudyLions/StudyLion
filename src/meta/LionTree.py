import logging

from discord import Interaction
from discord.app_commands import CommandTree
from discord.app_commands.errors import AppCommandError, CommandInvokeError
from discord.enums import InteractionType
from discord.app_commands.namespace import Namespace

from .logger import logging_context, set_logging_context, log_wrap
from .errors import SafeCancellation

logger = logging.getLogger(__name__)


class LionTree(CommandTree):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._call_tasks = set()

    async def on_error(self, interaction, error) -> None:
        try:
            if isinstance(error, CommandInvokeError):
                raise error.original
            else:
                raise error
        except SafeCancellation:
            # Assume this has already been handled
            pass
        except Exception:
            logger.exception(f"Unhandled exception in interaction: {interaction}", extra={'action': 'TreeError'})

    def _from_interaction(self, interaction: Interaction) -> None:
        @log_wrap(context=f"iid: {interaction.id}", isolate=False)
        async def wrapper():
            try:
                await self._call(interaction)
            except AppCommandError as e:
                await self._dispatch_error(interaction, e)

        task = self.client.loop.create_task(wrapper(), name='CommandTree-invoker')
        self._call_tasks.add(task)
        task.add_done_callback(lambda fut: self._call_tasks.discard(fut))

    async def _call(self, interaction):
        if not await self.interaction_check(interaction):
            interaction.command_failed = True
            return

        data = interaction.data  # type: ignore
        type = data.get('type', 1)
        if type != 1:
            # Context menu command...
            await self._call_context_menu(interaction, data, type)
            return

        command, options = self._get_app_command_options(data)

        # Pre-fill the cached slot to prevent re-computation
        interaction._cs_command = command

        # At this point options refers to the arguments of the command
        # and command refers to the class type we care about
        namespace = Namespace(interaction, data.get('resolved', {}), options)

        # Same pre-fill as above
        interaction._cs_namespace = namespace

        # Auto complete handles the namespace differently... so at this point this is where we decide where that is.
        if interaction.type is InteractionType.autocomplete:
            set_logging_context(action=f"Acmp {command.qualified_name}")
            focused = next((opt['name'] for opt in options if opt.get('focused')), None)
            if focused is None:
                raise AppCommandError(
                    'This should not happen, but there is no focused element. This is a Discord bug.'
                )
            await command._invoke_autocomplete(interaction, focused, namespace)
            return

        set_logging_context(action=f"Run {command.qualified_name}")
        logger.debug(f"Running command '{command.qualified_name}': {command.to_dict()}")
        try:
            await command._invoke_with_namespace(interaction, namespace)
        except AppCommandError as e:
            interaction.command_failed = True
            await command._invoke_error_handlers(interaction, e)
            await self.on_error(interaction, e)
        else:
            if not interaction.command_failed:
                self.client.dispatch('app_command_completion', interaction, command)
        finally:
            if interaction.command_failed:
                logger.debug("Command completed with errors.")
            else:
                logger.debug("Command completed without errors.")

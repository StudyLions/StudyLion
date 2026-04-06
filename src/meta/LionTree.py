import logging

import discord
from discord import Interaction
from discord.app_commands import CommandTree
from discord.app_commands.errors import AppCommandError, CommandInvokeError
from discord.enums import InteractionType
from discord.app_commands.namespace import Namespace

from utils.lib import tabulate
from gui.errors import RenderingException
from babel.translator import ctx_locale

from .logger import logging_context, set_logging_context, log_wrap, log_action_stack
from .errors import SafeCancellation
from .config import conf

logger = logging.getLogger(__name__)


class LionTree(CommandTree):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._call_tasks = set()

    async def on_error(self, interaction: discord.Interaction, error) -> None:
        try:
            if isinstance(error, CommandInvokeError):
                raise error.original
            else:
                raise error
        except SafeCancellation:
            # Assume this has already been handled
            pass
        except RenderingException as e:
            logger.info(f"Tree interaction failed due to rendering exception: {repr(e)}")
            embed = self.rendersplat(e)
            await self.error_reply(interaction, embed)
        # --- AI-MODIFIED (2026-04-05) ---
        # Purpose: Show a specific, actionable embed for permission errors instead of the generic bugsplat
        except discord.Forbidden as e:
            logger.warning(
                f"Forbidden error in interaction: {interaction}",
                exc_info=True,
                extra={'action': 'TreeForbidden'}
            )
            if interaction.type is not InteractionType.autocomplete:
                embed = self.forbidden_embed(interaction, e)
                await self.error_reply(interaction, embed)
        # --- END AI-MODIFIED ---
        except Exception:
            logger.exception(f"Unhandled exception in interaction: {interaction}", extra={'action': 'TreeError'})
            if interaction.type is not InteractionType.autocomplete:
                embed = self.bugsplat(interaction, error)
                await self.error_reply(interaction, embed)

    async def error_reply(self, interaction, embed):
        if not interaction.is_expired():
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except discord.HTTPException:
                pass

    def rendersplat(self, e: RenderingException):
        embed = discord.Embed(
            title="Resource Currently Unavailable!",
            description=(
                "Sorry, the graphics service is currently unavailable!\n"
                "Please try again in a few minutes.\n"
                "If the error persists, please contact our [support team]({link})"
            ).format(link=conf.bot.support_guild),
            colour=discord.Colour.dark_red()
        )
        return embed

    # --- AI-MODIFIED (2026-04-05) ---
    # Purpose: Dedicated embed for discord.Forbidden errors with actionable guidance
    def forbidden_embed(self, interaction, e):
        error_embed = discord.Embed(
            title="Missing Permissions!",
            colour=discord.Colour.orange()
        )
        error_embed.description = (
            "I don't have the required permissions to complete this action!\n"
            "Please make sure my role has the necessary permissions in this server and channel.\n\n"
            "If this error persists, please join our [support server]({link}) so we can help you out!"
        ).format(link=interaction.client.config.bot.support_guild)

        details = {}
        details['error'] = f"`{e.text}`"
        if e.code:
            details['error_code'] = f"`{e.code}`"
        if interaction.command:
            details['cmd'] = f"`{interaction.command.qualified_name}`"
        if interaction.guild:
            details['guild'] = f"`{interaction.guild.id}` -- `{interaction.guild.name}`"
            details['my_guild_perms'] = f"`{interaction.guild.me.guild_permissions.value}`"
        if interaction.channel and interaction.channel.type is not discord.enums.ChannelType.private:
            details['my_channel_perms'] = f"`{interaction.channel.permissions_for(interaction.guild.me).value}`"
        details['shard'] = f"`{interaction.client.shardname}`"

        table = '\n'.join(tabulate(*details.items()))
        error_embed.add_field(name='Details', value=table)
        return error_embed
    # --- END AI-MODIFIED ---

    def bugsplat(self, interaction, e):
        error_embed = discord.Embed(title="Something went wrong!", colour=discord.Colour.red())
        error_embed.description = (
            "An unexpected error occurred during this interaction!\n"
            "Our development team has been notified, and the issue will be addressed soon.\n"
            "If the error persists, or you have any questions, please contact our [support team]({link}) "
            "and give them the extra details below."
        ).format(link=interaction.client.config.bot.support_guild)
        details = {}
        details['error'] = f"`{repr(e)}`"
        details['interactionid'] = f"`{interaction.id}`"
        details['interactiontype'] = f"`{interaction.type}`"
        if interaction.command:
            details['cmd'] = f"`{interaction.command.qualified_name}`"
        details['locale'] = f"`{ctx_locale.get()}`"
        if interaction.user:
            details['user'] = f"`{interaction.user.id}` -- `{interaction.user}`"
        if interaction.guild:
            details['guild'] = f"`{interaction.guild.id}` -- `{interaction.guild.name}`"
            details['my_guild_perms'] = f"`{interaction.guild.me.guild_permissions.value}`"
            if interaction.user:
                ownerstr = ' (owner)' if interaction.user.id == interaction.guild.owner_id else ''
                details['user_guild_perms'] = f"`{interaction.user.guild_permissions.value}{ownerstr}`"
        if interaction.channel.type is discord.enums.ChannelType.private:
            details['channel'] = "`Direct Message`"
        elif interaction.channel:
            details['channel'] = f"`{interaction.channel.id}` -- `{interaction.channel.name}`"
            details['my_channel_perms'] = f"`{interaction.channel.permissions_for(interaction.guild.me).value}`"
            if interaction.user:
                details['user_channel_perms'] = f"`{interaction.channel.permissions_for(interaction.user).value}`"
        details['shard'] = f"`{interaction.client.shardname}`"
        details['log_stack'] = f"`{log_action_stack.get()}`"

        table = '\n'.join(tabulate(*details.items()))
        error_embed.add_field(name='Details', value=table)
        return error_embed

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
            try:
                await command._invoke_autocomplete(interaction, focused, namespace)
            except Exception as e:
                await self.on_error(interaction, e)
            return

        set_logging_context(action=f"Run {command.qualified_name}")
        logger.debug(f"Running command '{command.qualified_name}': {command!r}")
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

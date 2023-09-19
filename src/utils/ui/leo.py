from typing import List, Optional, Any, Dict
import asyncio
import logging
import time
from contextvars import copy_context, Context

import discord
from discord.ui import Modal, View, Item

from meta.logger import log_action_stack, logging_context
from meta.errors import SafeCancellation

from gui.errors import RenderingException

from . import logger
from ..lib import MessageArgs, error_embed

__all__ = (
    'LeoUI',
    'MessageUI',
    'LeoModal',
    'error_handler_for'
)


class LeoUI(View):
    """
    View subclass for small-scale user interfaces.

    While a 'View' provides an interface for managing a collection of components,
    a `LeoUI` may also manage a message, and potentially slave Views or UIs.
    The `LeoUI` also exposes more advanced cleanup and timeout methods,
    and preserves the context.
    """

    def __init__(self, *args, ui_name=None, context=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        if context is None:
            self._context = copy_context()
        else:
            self._context = context

        self._name = ui_name or self.__class__.__name__
        self._context.run(log_action_stack.set, [*self._context[log_action_stack], self._name])

        # List of slaved views to stop when this view stops
        self._slaves: List[View] = []

        # TODO: Replace this with a substitutable ViewLayout class
        self._layout: Optional[tuple[tuple[Item, ...], ...]] = None

    @property
    def _stopped(self) -> asyncio.Future:
        """
        Return an future indicating whether the View has finished interacting.

        Currently exposes a hidden attribute of the underlying View.
        May be reimplemented in future.
        """
        return self._View__stopped

    def to_components(self) -> List[Dict[str, Any]]:
        """
        Extending component generator to apply the set _layout, if it exists.
        """
        if self._layout is not None:
            # Alternative rendering using layout
            components = []
            for i, row in enumerate(self._layout):
                # Skip empty rows
                if not row:
                    continue

                # Since we aren't relying on ViewWeights, manually check width here
                if sum(item.width for item in row) > 5:
                    raise ValueError(f"Row {i} of custom {self.__class__.__name__} is too wide!")

                # Create the component dict for this row
                components.append({
                    'type': 1,
                    'components': [item.to_component_dict() for item in row]
                })
        else:
            components = super().to_components()

        return components

    def set_layout(self, *rows: tuple[Item, ...]) -> None:
        """
        Set the layout of the rendered View as a matrix of items,
        or more precisely, a list of action rows.

        This acts independently of the existing sorting with `_ViewWeights`,
        and overrides the sorting if applied.
        """
        self._layout = rows

    async def cleanup(self):
        """
        Coroutine to run when timeing out, stopping, or cancelling.
        Generally cleans up any open resources, and removes any leftover components.
        """
        logging.debug(f"{self!r} running default cleanup.", extra={'action': 'cleanup'})
        return None

    def stop(self):
        """
        Extends View.stop() to also stop all the slave views.
        Note that stopping is idempotent, so it is okay if close() also calls stop().
        """
        for slave in self._slaves:
            slave.stop()
        super().stop()

    async def close(self, msg=None):
        self.stop()
        await self.cleanup()

    async def pre_timeout(self):
        """
        Task to execute before actually timing out.
        This may cancel the timeout by refreshing or rescheduling it.
        (E.g. to ask the user whether they want to keep going.)

        Default implementation does nothing.
        """
        return None

    async def on_timeout(self):
        """
        Task to execute after timeout is complete.
        Default implementation calls cleanup.
        """
        await self.cleanup()

    async def __dispatch_timeout(self):
        """
        This essentially extends View._dispatch_timeout,
        to include a pre_timeout task
        which may optionally refresh and hence cancel the timeout.
        """
        if self._View__stopped.done():
            # We are already stopped, nothing to do
            return

        with logging_context(action='Timeout'):
            try:
                await self.pre_timeout()
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                pass
            except Exception:
                await logger.exception(
                    "Unhandled error caught while dispatching timeout for {self!r}.",
                    extra={'with_ctx': True, 'action': 'Error'}
                )

            # Check if we still need to timeout
            if self.timeout is None:
                # The timeout was removed entirely, silently walk away
                return

            if self._View__stopped.done():
                # We stopped while waiting for the pre timeout.
                # Or maybe another thread timed us out
                # Either way, we are done here
                return

            now = time.monotonic()
            if self._View__timeout_expiry is not None and now < self._View__timeout_expiry:
                # The timeout was extended, make sure the timeout task is running then fade away
                if self._View__timeout_task is None or self._View__timeout_task.done():
                    self._View__timeout_task = asyncio.create_task(self._View__timeout_task_impl())
            else:
                # Actually timeout, and call the post-timeout task for cleanup.
                self._really_timeout()
                await self.on_timeout()

    def _dispatch_timeout(self):
        """
        Overriding timeout method completely, to support interactive flow during timeout,
        and optional refreshing of the timeout.
        """
        return self._context.run(asyncio.create_task, self.__dispatch_timeout())

    def _really_timeout(self):
        """
        Actuallly times out the View.
        This copies View._dispatch_timeout, apart from the `on_timeout` dispatch,
        which is now handled by `__dispatch_timeout`.
        """
        if self._View__stopped.done():
            return

        if self._View__cancel_callback:
            self._View__cancel_callback(self)
            self._View__cancel_callback = None

        self._View__stopped.set_result(True)

    def _dispatch_item(self, *args, **kwargs):
        """Extending event dispatch to run in the instantiation context."""
        return self._context.run(super()._dispatch_item, *args, **kwargs)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: Item):
        """
        Default LeoUI error handle.
        This may be tail extended by subclasses to preserve the exception stack.
        """
        try:
            raise error
        except SafeCancellation as e:
            if e.msg and not interaction.is_expired():
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(
                            embed=error_embed(e.msg),
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            embed=error_embed(e.msg),
                            ephemeral=True
                        )
                except discord.HTTPException:
                    pass
            logger.debug(
                f"Caught a safe cancellation from LeoUI: {e.details}",
                extra={'action': 'Cancel'}
            )
        except RenderingException as e:
            logger.info(
                f"UI interaction failed due to rendering exception: {repr(e)}"
            )
            embed = interaction.client.tree.rendersplat(e)
            await interaction.client.tree.error_reply(interaction, embed)
        except Exception:
            logger.exception(
                f"Unhandled interaction exception occurred in item {item!r} of LeoUI {self!r} from interaction: "
                f"{interaction.data}",
                extra={'with_ctx': True, 'action': 'UIError'}
            )
            # Explicitly handle the bugsplat ourselves
            splat = interaction.client.tree.bugsplat(interaction, error)
            await interaction.client.tree.error_reply(interaction, splat)


class MessageUI(LeoUI):
    """
    Simple single-message LeoUI, intended as a framework for UIs
    attached to a single interaction response.

    UIs may also be sent as regular messages by using `send(channel)` instead of `run(interaction)`.
    """

    def __init__(self, *args, callerid: Optional[int] = None, **kwargs):
        super().__init__(*args, **kwargs)

        # ----- UI state -----
        # User ID of the original caller (e.g. command author).
        # Mainly used for interaction usage checks and logging
        self._callerid = callerid

        # Original interaction, if this UI is sent as an interaction response
        self._original: discord.Interaction = None

        # Message holding the UI, when the UI is sent attached to a followup
        self._message: discord.Message = None

        # Refresh lock, to avoid cache collisions on refresh
        self._refresh_lock = asyncio.Lock()

    @property
    def channel(self):
        if self._original is not None:
            return self._original.channel
        else:
            return self._message.channel

    # ----- UI API -----
    async def run(self, interaction: discord.Interaction, **kwargs):
        """
        Run the UI as a response or followup to the given interaction.

        Should be extended if more complex run mechanics are needed
        (e.g. registering listeners or setting up caches).
        """
        await self.draw(interaction, **kwargs)

    async def refresh(self, *args, thinking: Optional[discord.Interaction] = None, **kwargs):
        """
        Reload and redraw this UI.

        Primarily a hook-method for use by parents and other controllers.
        Performs a full data and reload and refresh (maintaining UI state, e.g. page n).
        """
        async with self._refresh_lock:
            # Reload data
            await self.reload()
            # Redraw UI message
            await self.redraw(thinking=thinking)

    async def quit(self):
        """
        Quit the UI.

        This usually involves removing the original message,
        and stopping or closing the underlying View.
        """
        for child in self._slaves:
            # TODO: Better to use duck typing or interface typing
            if isinstance(child, MessageUI) and not child.is_finished():
                asyncio.create_task(child.quit())
        try:
            if self._original is not None and not self._original.is_expired():
                await self._original.delete_original_response()
                self._original = None
            if self._message is not None:
                await self._message.delete()
                self._message = None
        except discord.HTTPException:
            pass

        # Note close() also runs cleanup and stop
        await self.close()

    # ----- UI Flow -----
    async def interaction_check(self, interaction: discord.Interaction):
        """
        Check the given interaction is authorised to use this UI.

        Default implementation simply checks that the interaction is
        from the original caller.
        Extend for more complex logic.
        """
        return interaction.user.id == self._callerid

    async def make_message(self) -> MessageArgs:
        """
        Create the UI message body, depening on the current state.

        Called upon each redraw.
        Should handle caching if message construction is for some reason intensive.

        Must be implemented by concrete UI subclasses.
        """
        raise NotImplementedError

    async def refresh_layout(self):
        """
        Asynchronously refresh the message components,
        and explicitly set the message component layout.

        Called just before redrawing, before `make_message`.

        Must be implemented by concrete UI subclasses.
        """
        raise NotImplementedError

    async def reload(self):
        """
        Reload and recompute the underlying data for this UI.

        Must be implemented by concrete UI subclasses.
        """
        raise NotImplementedError

    async def draw(self, interaction, force_followup=False, **kwargs):
        """
        Send the UI as a response or followup to the given interaction.

        If the interaction has been responded to, or `force_followup` is set,
        creates a followup message instead of a response to the interaction.
        """
        # Initial data loading
        await self.reload()
        # Set the UI layout
        await self.refresh_layout()
        # Fetch message arguments
        args = await self.make_message()

        as_followup = force_followup or interaction.response.is_done()
        if as_followup:
            self._message = await interaction.followup.send(**args.send_args, **kwargs, view=self)
        else:
            self._original = interaction
            await interaction.response.send_message(**args.send_args, **kwargs, view=self)

    async def send(self, channel: discord.abc.Messageable, **kwargs):
        """
        Alternative to draw() which uses a discord.abc.Messageable.
        """
        await self.reload()
        await self.refresh_layout()
        args = await self.make_message()
        self._message = await channel.send(**args.send_args, view=self)

    async def _redraw(self, args):
        if self._original and not self._original.is_expired():
            await self._original.edit_original_response(**args.edit_args, view=self)
        elif self._message:
            await self._message.edit(**args.edit_args, view=self)
        else:
            # Interaction expired or already closed. Quietly cleanup.
            await self.close()

    async def redraw(self, thinking: Optional[discord.Interaction] = None):
        """
        Update the output message for this UI.

        If a thinking interaction is provided, deletes the response while redrawing.
        """
        await self.refresh_layout()
        args = await self.make_message()

        if thinking is not None and not thinking.is_expired() and thinking.response.is_done():
            asyncio.create_task(thinking.delete_original_response())

        try:
            await self._redraw(args)
        except discord.HTTPException as e:
            # Unknown communication error, nothing we can reliably do. Exit quietly.
            logger.warning(
                f"Unexpected UI redraw failure occurred in {self}: {repr(e)}",
            )
            await self.close()

    async def cleanup(self):
        """
        Remove message components from interaction response, if possible.

        Extend to remove listeners or clean up caches.
        `cleanup` is always called when the UI is exiting,
        through timeout or user-driven closure.
        """
        try:
            if self._original is not None and not self._original.is_expired():
                await self._original.edit_original_response(view=None)
                self._original = None
            if self._message is not None:
                await self._message.edit(view=None)
                self._message = None
        except discord.HTTPException:
            pass


class LeoModal(Modal):
    """
    Context-aware Modal class.
    """
    def __init__(self, *args, context: Optional[Context] = None, **kwargs):
        super().__init__(**kwargs)

        if context is None:
            self._context = copy_context()
        else:
            self._context = context
        self._context.run(log_action_stack.set, [*self._context[log_action_stack], self.__class__.__name__])

    def _dispatch_submit(self, *args, **kwargs):
        """
        Extending event dispatch to run in the instantiation context.
        """
        return self._context.run(super()._dispatch_submit, *args, **kwargs)

    def _dispatch_item(self, *args, **kwargs):
        """Extending event dispatch to run in the instantiation context."""
        return self._context.run(super()._dispatch_item, *args, **kwargs)

    async def on_error(self, interaction: discord.Interaction, error: Exception, *args):
        """
        Default LeoModal error handle.
        This may be tail extended by subclasses to preserve the exception stack.
        """
        try:
            raise error
        except RenderingException as e:
            logger.info(
                f"Modal submit failed due to rendering exception: {repr(e)}"
            )
            embed = interaction.client.tree.rendersplat(e)
            await interaction.client.tree.error_reply(interaction, embed)
        except Exception:
            logger.exception(
                f"Unhandled interaction exception occurred in {self!r}. Interaction: {interaction.data}",
                extra={'with_ctx': True, 'action': 'ModalError'}
            )
            # Explicitly handle the bugsplat ourselves
            splat = interaction.client.tree.bugsplat(interaction, error)
            await interaction.client.tree.error_reply(interaction, splat)


def error_handler_for(exc):
    def wrapper(coro):
        coro._ui_error_handler_for_ = exc
        return coro
    return wrapper

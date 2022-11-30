from typing import List, Optional, Any, Dict
import asyncio
import logging
import time
from contextvars import copy_context, Context

import discord
from discord.ui import Modal, View, Item

from meta.logger import log_action_stack, logging_context

from . import logger

__all__ = (
    'LeoUI',
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
        if self.__stopped.done():
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

            if self.__stopped.done():
                # We stopped while waiting for the pre timeout.
                # Or maybe another thread timed us out
                # Either way, we are done here
                return

            now = time.monotonic()
            if self.__timeout_expiry is not None and now < self._timeout_expiry:
                # The timeout was extended, make sure the timeout task is running then fade away
                if self.__timeout_task is None or self.__timeout_task.done():
                    self.__timeout_task = asyncio.create_task(self.__timeout_task_impl())
            else:
                # Actually timeout, and call the post-timeout task for cleanup.
                self._really_timeout()
                await self.on_timeout()

    def _dispatch_timeout(self):
        """
        Overriding timeout method completely, to support interactive flow during timeout,
        and optional refreshing of the timeout.
        """
        return self._context.run(asyncio.create_task, self.dispatch_timeout())

    def _really_timeout(self):
        """
        Actuallly times out the View.
        This copies View._dispatch_timeout, apart from the `on_timeout` dispatch,
        which is now handled by `__dispatch_timeout`.
        """
        if self.__stopped.done():
            return

        if self.__cancel_callback:
            self.__cancel_callback(self)
            self.__cancel_callback = None

        self.__stopped.set_result(True)

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
        except Exception:
            logger.exception(
                f"Unhandled interaction exception occurred in item {item!r} of LeoUI {self!r}",
                extra={'with_ctx': True, 'action': 'UIError'}
            )


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
        except Exception:
            logger.exception(
                f"Unhandled interaction exception occurred in {self!r}",
                extra={'with_ctx': True, 'action': 'ModalError'}
            )


def error_handler_for(exc):
    def wrapper(coro):
        coro._ui_error_handler_for_ = exc
        return coro
    return wrapper

from typing import List, Coroutine, Optional, Any, Type, TypeVar, Callable, Dict, TYPE_CHECKING
from typing_extensions import Annotated
import functools
import asyncio
import logging
import time
from enum import Enum
from contextvars import copy_context, Context
from itertools import groupby

import discord
from discord.ui import Modal, TextInput, View, Item
from discord.ui.button import Button, button
import discord.app_commands as appcmd
from discord.app_commands.transformers import AppCommandOptionType

from meta.logger import log_action_stack, logging_context


logger = logging.getLogger(__name__)


def create_task_in(coro, context: Context):
    """
    Transitional.
    Since py3.10 asyncio does not support context instantiation,
    this helper method runs `asyncio.create_task(coro)` inside the given context.
    """
    return context.run(asyncio.create_task, coro)


class HookedItem:
    """
    Mixin for Item classes allowing an instance to be used as a callback decorator.
    """
    def __init__(self, *args, pass_kwargs={}, **kwargs):
        super().__init__(*args, **kwargs)
        self.pass_kwargs = pass_kwargs

    def __call__(self, coro):
        async def wrapped(view, interaction, **kwargs):
            return await coro(view, interaction, self, **kwargs, **self.pass_kwargs)
        self.callback = wrapped
        return self


class AButton(HookedItem, Button):
    ...


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


class AsComponents(LeoUI):
    """
    Simple container class to accept a number of Items and turn them into an attachable View.
    """
    def __init__(self, *items, pass_kwargs={}, **kwargs):
        super().__init__(**kwargs)
        self.pass_kwargs = pass_kwargs

        for item in items:
            item.callback = self.wrap_callback(item.callback)
            self.add_item(item)

    def wrap_callback(self, coro):
        async def wrapped(*args, **kwargs):
            return await coro(self, *args, **kwargs, **self.pass_kwargs)
        return wrapped


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


class FastModal(LeoModal):
    __class_error_handlers__ = []

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        error_handlers = {}
        for base in reversed(cls.__mro__):
            for name, member in base.__dict__.items():
                if hasattr(member, '_ui_error_handler_for_'):
                    error_handlers[name] = member

        cls.__class_error_handlers__ = list(error_handlers.values())

    def __init__error_handlers__(self):
        handlers = {}
        for handler in self.__class_error_handlers__:
            handlers[handler._ui_error_handler_for_] = functools.partial(handler, self)
        return handlers

    def __init__(self, *items: TextInput, **kwargs):
        super().__init__(**kwargs)
        for item in items:
            self.add_item(item)
        self._result: asyncio.Future[discord.Interaction] = asyncio.get_event_loop().create_future()
        self._waiters: List[Callable[[discord.Interaction], Coroutine]] = []
        self._error_handlers = self.__init__error_handlers__()

    def error_handler(self, exception):
        def wrapper(coro):
            self._error_handlers[exception] = coro
            return coro
        return wrapper

    async def wait_for(self, check=None, timeout=None):
        # Wait for _result or timeout
        # If we timeout, or the view times out, raise TimeoutError
        # Otherwise, return the Interaction
        # This allows multiple listeners and callbacks to wait on
        while True:
            result = await asyncio.wait_for(asyncio.shield(self._result), timeout=timeout)
            if check is not None:
                if not check(result):
                    continue
            return result

    async def on_timeout(self):
        self._result.set_exception(asyncio.TimeoutError)

    def submit_callback(self, timeout=None, check=None, once=False, pass_args=(), pass_kwargs={}):
        def wrapper(coro):
            async def wrapped_callback(interaction):
                with logging_context(action=coro.__name__):
                    if check is not None:
                        if not check(interaction):
                            return
                    try:
                        await coro(interaction, *pass_args, **pass_kwargs)
                    except Exception as error:
                        await self.on_error(interaction, error)
                    finally:
                        if once:
                            self._waiters.remove(wrapped_callback)
            self._waiters.append(wrapped_callback)
        return wrapper

    async def on_error(self, interaction: discord.Interaction, error: Exception, *args):
        try:
            # First let our error handlers have a go
            # If there is no handler for this error, or the handlers themselves error,
            # drop to the superclass error handler implementation.
            try:
                raise error
            except tuple(self._error_handlers.keys()) as e:
                # If an error handler is registered for this exception, run it.
                for cls, handler in self._error_handlers.items():
                    if isinstance(e, cls):
                        await handler(interaction, e)
        except Exception as error:
            await super().on_error(interaction, error)

    async def on_submit(self, interaction):
        old_result = self._result
        self._result = asyncio.get_event_loop().create_future()
        old_result.set_result(interaction)

        for waiter in self._waiters:
            asyncio.create_task(waiter(interaction), name=f"leo-ui-fastmodal-{self.id}-callback-{waiter.__name__}")


async def input(
    interaction: discord.Interaction,
    title: str,
    question: Optional[str] = None,
    field: Optional[TextInput] = None,
    timeout=180,
    **kwargs,
):
    """
    Spawn a modal to accept input.
    Returns an (interaction, value) pair, with interaction not yet responded to.
    May raise asyncio.TimeoutError if the view times out.
    """
    if field is None:
        field = TextInput(
            label=kwargs.get('label', question),
            **kwargs
        )
    modal = FastModal(
        field,
        title=title,
        timeout=timeout
    )
    await interaction.response.send_modal(modal)
    interaction = await modal.wait_for()
    return (interaction, field.value)


class ChoicedEnum(Enum):
    @property
    def choice_name(self):
        return self.name

    @property
    def choice_value(self):
        return self.value

    @property
    def choice(self):
        return appcmd.Choice(
            name=self.choice_name, value=self.choice_value
        )

    @classmethod
    def choices(self):
        return [item.choice for item in self]

    @classmethod
    def make_choice_map(cls):
        return {item.choice_value: item for item in cls}

    @classmethod
    async def transform(cls, transformer: 'ChoicedEnumTransformer', interaction: discord.Interaction, value: Any):
        return transformer._choice_map[value]

    @classmethod
    def option_type(cls) -> AppCommandOptionType:
        return AppCommandOptionType.string

    @classmethod
    def transformer(cls, *args) -> appcmd.Transformer:
        return ChoicedEnumTransformer(cls, *args)


class ChoicedEnumTransformer(appcmd.Transformer):
    # __discord_app_commands_is_choice__ = True

    def __init__(self, enum: Type[ChoicedEnum], opt_type) -> None:
        super().__init__()

        self._type = opt_type
        self._enum = enum
        self._choices = enum.choices()
        self._choice_map = enum.make_choice_map()

    @property
    def _error_display_name(self) -> str:
        return self._enum.__name__

    @property
    def type(self) -> AppCommandOptionType:
        return self._type

    @property
    def choices(self):
        return self._choices

    async def transform(self, interaction: discord.Interaction, value: Any, /) -> Any:
        return await self._enum.transform(self, interaction, value)


if TYPE_CHECKING:
    from typing_extensions import Annotated as Transformed
else:

    class Transformed:
        def __class_getitem__(self, items):
            cls = items[0]
            options = items[1:]

            if not hasattr(cls, 'transformer'):
                raise ValueError("Tranformed class must have a transformer classmethod.")
            transformer = cls.transformer(*options)
            return appcmd.Transform[cls, transformer]


class ModalRetryUI(LeoUI):
    def __init__(self, modal: FastModal, message, label: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.modal = modal
        self.item_values = {item: item.value for item in modal.children if isinstance(item, TextInput)}

        self.message = message

        self._interaction = None

        if label is not None:
            self.retry_button.label = label

    @property
    def embed(self):
        return discord.Embed(
            description=self.message,
            colour=discord.Colour.red()
        )

    async def respond_to(self, interaction):
        self._interaction = interaction
        await interaction.response.send_message(embed=self.embed, ephemeral=True, view=self)

    @button(label="Retry")
    async def retry_button(self, interaction, butt):
        # Setting these here so they don't update in the meantime
        for item, value in self.item_values.items():
            item.default = value
        if self._interaction is not None:
            await self._interaction.delete_original_response()
            self._interaction = None
        await interaction.response.send_modal(self.modal)
        await self.close()

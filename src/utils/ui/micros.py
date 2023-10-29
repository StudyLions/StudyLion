from typing import List, Coroutine, Optional, Any, Type, TypeVar, Callable, Dict
import functools
import asyncio

import discord
from discord.ui import TextInput
from discord.ui.button import button

from meta.logger import logging_context
from meta.errors import ResponseTimedOut

from .leo import LeoModal, LeoUI

__all__ = (
    'FastModal',
    'ModalRetryUI',
    'Confirm',
    'input',
)


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
                    except Exception:
                        raise
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
        print("On submit")
        old_result = self._result
        self._result = asyncio.get_event_loop().create_future()
        old_result.set_result(interaction)

        tasks = []
        for waiter in self._waiters:
            task = asyncio.create_task(
                waiter(interaction),
                name=f"leo-ui-fastmodal-{self.id}-callback-{waiter.__name__}"
            )
            tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks)


async def input(
    interaction: discord.Interaction,
    title: str,
    question: Optional[str] = None,
    field: Optional[TextInput] = None,
    timeout=180,
    **kwargs,
) -> tuple[discord.Interaction, str]:
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
            title="Uh-Oh!",
            description=self.message,
            colour=discord.Colour.red()
        )

    async def respond_to(self, interaction):
        self._interaction = interaction
        if interaction.response.is_done():
            await interaction.followup.send(embed=self.embed, ephemeral=True, view=self)
        else:
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


class Confirm(LeoUI):
    """
    Micro UI class implementing a confirmation question.

    Parameters
    ----------
    confirm_msg: str
        The confirmation question to ask from the user.
        This is set as the description of the `embed` property.
        The `embed` may be further modified if required.
    permitted_id: Optional[int]
        The user id allowed to access this interaction.
        Other users will recieve an access denied error message.
    defer: bool
        Whether to defer the interaction response while handling the button.
        It may be useful to set this to `False` to obtain manual control
        over the interaction response flow (e.g. to send a modal or ephemeral message).
        The button press interaction may be accessed through `Confirm.interaction`.
        Default: True

    Example
    -------
    ```
    confirm = Confirm("Are you sure?", ctx.author.id)
    confirm.embed.colour = discord.Colour.red()
    confirm.confirm_button.label = "Yes I am sure"
    confirm.cancel_button.label = "No I am not sure"

    try:
        result = await confirm.ask(ctx.interaction, ephemeral=True)
    except ResultTimedOut:
        return
    ```
    """
    def __init__(
        self,
        confirm_msg: str,
        permitted_id: Optional[int] = None,
        defer: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.confirm_msg = confirm_msg
        self.permitted_id = permitted_id
        self.defer = defer

        self._embed: Optional[discord.Embed] = None
        self._result: asyncio.Future[bool] = asyncio.Future()

        # Indicates whether we should delete the message or the interaction response
        self._is_followup: bool = False
        self._original: Optional[discord.Interaction] = None
        self._message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction):
        return (self.permitted_id is None) or interaction.user.id == self.permitted_id

    async def on_timeout(self):
        # Propagate timeout to result Future
        self._result.set_exception(ResponseTimedOut)
        await self.cleanup()

    async def cleanup(self):
        """
        Cleanup the confirmation prompt by deleting it, if possible.
        Ignores any Discord errors that occur during the process.
        """
        try:
            if self._is_followup and self._message:
                await self._message.delete()
            elif not self._is_followup and self._original and not self._original.is_expired():
                await self._original.delete_original_response()
        except discord.HTTPException:
            # A user probably already deleted the message
            # Anything could have happened, just ignore.
            pass

    @button(label="Confirm")
    async def confirm_button(self, interaction: discord.Interaction, press):
        if self.defer:
            await interaction.response.defer()
        self._result.set_result(True)
        await self.close()

    @button(label="Cancel")
    async def cancel_button(self, interaction: discord.Interaction, press):
        if self.defer:
            await interaction.response.defer()
        self._result.set_result(False)
        await self.close()

    @property
    def embed(self):
        """
        Confirmation embed shown to the user.
        This is cached, and may be modifed directly through the usual EmbedProxy API,
        or explicitly overwritten.
        """
        if self._embed is None:
            self._embed = discord.Embed(
                colour=discord.Colour.orange(),
                description=self.confirm_msg
            )
        return self._embed

    @embed.setter
    def embed(self, value):
        self._embed = value

    async def ask(self, interaction: discord.Interaction, ephemeral=False, **kwargs):
        """
        Send this confirmation prompt in response to the provided interaction.
        Extra keyword arguments are passed to `Interaction.response.send_message`
        or `Interaction.send_followup`, depending on whether
        the provided interaction has already been responded to.

        The `epehemeral` argument is handled specially,
        since the question message can only be deleted through `Interaction.delete_original_response`.

        Waits on and returns the internal `result` Future.

        Returns: bool
            True if the user pressed the confirm button.
            False if the user pressed the cancel button.
        Raises:
            ResponseTimedOut:
                If the user does not respond before the UI times out.
        """
        self._original = interaction
        if interaction.response.is_done():
            # Interaction already responded to, send a follow up
            if ephemeral:
                raise ValueError("Cannot send an ephemeral response to a used interaction.")
            self._message = await interaction.followup.send(embed=self.embed, **kwargs, view=self)
            self._is_followup = True
        else:
            await interaction.response.send_message(
                embed=self.embed, ephemeral=ephemeral, **kwargs, view=self
            )
            self._is_followup = False
        return await self._result

# TODO: Selector MicroUI for displaying options (<= 25)

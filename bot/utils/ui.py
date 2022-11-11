from typing import List, Coroutine
import asyncio
import logging
from contextvars import copy_context

import discord
from discord.ui import Modal

from .lib import recover_context


class FastModal(Modal):
    def __init__(self, *items, **kwargs):
        super().__init__(**kwargs)
        for item in items:
            self.add_item(item)
        self._result: asyncio.Future[discord.Interaction] = asyncio.get_event_loop().create_future()
        self._waiters: List[Coroutine[discord.Interaction]] = []
        self._context = copy_context()

    async def wait_for(self, check=None, timeout=None):
        # Wait for _result or timeout
        # If we timeout, or the view times out, raise TimeoutError
        # Otherwise, return the Interaction
        # This allows multiple listeners and callbacks to wait on
        # TODO: Wait on the timeout as well
        while True:
            result = await asyncio.wait_for(asyncio.shield(self._result), timeout=timeout)
            if check is not None:
                if not check(result):
                    continue
            return result

    def submit_callback(self, timeout=None, check=None, once=False, pass_args=(), pass_kwargs={}):
        def wrapper(coro):
            async def wrapped_callback(interaction):
                if check is not None:
                    if not check(interaction):
                        return
                try:
                    await coro(interaction, *pass_args, **pass_kwargs)
                except Exception:
                    # TODO: Log exception
                    logging.exception(
                        f"Exception occurred executing FastModal callback '{coro.__name__}'"
                    )
                if once:
                    self._waiters.remove(wrapped_callback)
            self._waiters.append(wrapped_callback)
        return wrapper

    async def on_submit(self, interaction):
        # Transitional patch to re-instantiate the current context
        # Not required in py 3.11, instead pass a context parameter to create_task
        recover_context(self._context)

        old_result = self._result
        self._result = asyncio.get_event_loop().create_future()
        old_result.set_result(interaction)

        for waiter in self._waiters:
            asyncio.create_task(waiter(interaction))

    async def on_error(self, interaction, error):
        # This should never happen, since on_submit has its own error handling
        # TODO: Logging
        logging.error("Submit error occured in FastModal")

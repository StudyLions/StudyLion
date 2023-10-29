import time

import discord
from discord.ui.item import Item
from discord.ui.button import Button

from .leo import LeoUI

__all__ = (
    'HookedItem',
    'AButton',
    'AsComponents'
)


class HookedItem:
    """
    Mixin for Item classes allowing an instance to be used as a callback decorator.
    """
    def __init__(self, *args, pass_kwargs={}, **kwargs):
        super().__init__(*args, **kwargs)
        self.pass_kwargs = pass_kwargs

    def __call__(self, coro):
        async def wrapped(interaction, **kwargs):
            return await coro(interaction, self, **(self.pass_kwargs | kwargs))
        self.callback = wrapped
        return self


class AButton(HookedItem, Button):
    ...


class AsComponents(LeoUI):
    """
    Simple container class to accept a number of Items and turn them into an attachable View.
    """
    def __init__(self, *items, pass_kwargs={}, **kwargs):
        super().__init__(**kwargs)
        self.pass_kwargs = pass_kwargs

        for item in items:
            self.add_item(item)

    async def _scheduled_task(self, item: Item, interaction: discord.Interaction):
        try:
            item._refresh_state(interaction, interaction.data)  # type: ignore

            allow = await self.interaction_check(interaction)
            if not allow:
                return

            if self.timeout:
                self.__timeout_expiry = time.monotonic() + self.timeout

            await item.callback(interaction, **self.pass_kwargs)
        except Exception as e:
            return await self.on_error(interaction, e, item)

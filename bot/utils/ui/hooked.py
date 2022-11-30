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
        async def wrapped(view, interaction, **kwargs):
            return await coro(view, interaction, self, **kwargs, **self.pass_kwargs)
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
            item.callback = self.wrap_callback(item.callback)
            self.add_item(item)

    def wrap_callback(self, coro):
        async def wrapped(*args, **kwargs):
            return await coro(self, *args, **kwargs, **self.pass_kwargs)
        return wrapped

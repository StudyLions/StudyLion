"""
Namespace for various global context variables.
Allows asyncio callbacks to accurately retrieve information about the current state.
"""


from typing import TYPE_CHECKING, Optional

from contextvars import ContextVar

if TYPE_CHECKING:
    from .LionBot import LionBot
    from .LionContext import LionContext


# Contains the current command context, if applicable
context: ContextVar[Optional['LionContext']] = ContextVar('context', default=None)

# Contains the current LionBot instance
ctx_bot: ContextVar[Optional['LionBot']] = ContextVar('bot', default=None)

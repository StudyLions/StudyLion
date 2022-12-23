from typing import Optional
from string import Template


class SafeCancellation(Exception):
    """
    Raised to safely cancel execution of the current operation.

    If not caught, is expected to be propagated to the Tree and safely ignored there.
    If a `msg` is provided, a context-aware error handler should catch and send the message to the user.
    The error handler should then set the `msg` to None, to avoid double handling.
    Debugging information should go in `details`, to be logged by a top-level error handler.
    """
    default_message = ""

    @property
    def msg(self):
        return self._msg if self._msg is not None else self.default_message

    def __init__(self, _msg: Optional[str] = None, details: Optional[str] = None, **kwargs):
        self._msg: Optional[str] = _msg
        self.details: str = details if details is not None else self.msg
        super().__init__(**kwargs)


class UserInputError(SafeCancellation):
    """
    A SafeCancellation induced from unparseable user input.
    """
    default_message = "Could not understand your input."

    @property
    def msg(self):
        return Template(self._msg).substitute(**self.info) if self._msg is not None else self.default_message

    def __init__(self, _msg: Optional[str] = None, info: dict[str, str] = {}, **kwargs):
        self.info = info
        super().__init__(_msg, **kwargs)


class UserCancelled(SafeCancellation):
    """
    A SafeCancellation induced from manual user cancellation.

    Usually silent.
    """
    default_msg = None


class ResponseTimedOut(SafeCancellation):
    """
    A SafeCancellation induced from a user interaction time-out.
    """
    default_msg = "Session timed out waiting for input."


class HandledException(SafeCancellation):
    """
    Sentinel class to indicate to error handlers that this exception has been handled.
    Required because discord.ext breaks the exception stack, so we can't just catch the error in a lower handler.
    """
    def __init__(self, exc=None, **kwargs):
        self.exc = exc
        super().__init__(**kwargs)

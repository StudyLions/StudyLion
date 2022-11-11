from typing import Optional


class SafeCancellation(Exception):
    """
    Raised to safely cancel execution of the current operation.

    If not caught, is expected to be propagated to the Tree and safely ignored there.
    If a `msg` is provided, a context-aware error handler should catch and send the message to the user.
    The error handler should then set the `msg` to None, to avoid double handling.
    Debugging information should go in `details`, to be logged by a top-level error handler.
    """
    default_message = ""

    def __init__(self, msg: Optional[str] = None, details: Optional[str] = None, **kwargs):
        self.msg: Optional[str] = msg if msg is not None else self.default_message
        self.details: str = details if details is not None else self.msg
        super().__init__(**kwargs)


class UserInputError(SafeCancellation):
    """
    A SafeCancellation induced from unparseable user input.
    """
    default_message = "Could not understand your input."


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

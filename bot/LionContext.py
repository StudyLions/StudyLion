import types

from cmdClient import Context
from cmdClient.logger import log


class LionContext(Context):
    """
    Subclass to allow easy attachment of custom hooks and structure to contexts.
    """
    @classmethod
    def util(cls, util_func):
        """
        Decorator to make a utility function available as a Context instance method.
        Extends the default Context method to add logging and to return the utility function.
        """
        super().util(util_func)
        log(f"Attached context utility function: {util_func.__name__}")
        return util_func

    @classmethod
    def wrappable_util(cls, util_func):
        """
        Decorator to add a Wrappable utility function as a Context instance method.
        """
        wrappable = Wrappable(util_func)
        super().util(wrappable)
        log(f"Attached wrappable context utility function: {util_func.__name__}")
        return wrappable


class Wrappable:
    __slots = ('_func', 'wrappers')

    def __init__(self, func):
        self._func = func
        self.wrappers = None

    @property
    def __name__(self):
        return self._func.__name__

    def add_wrapper(self, func, name=None):
        self.wrappers = self.wrappers or {}
        name = name or func.__name__
        self.wrappers[name] = func
        log(
            f"Added wrapper '{name}' to Wrappable '{self._func.__name__}'.",
            context="Wrapping"
        )

    def remove_wrapper(self, name):
        if not self.wrappers or name not in self.wrappers:
            raise ValueError(
                f"Cannot remove non-existent wrapper '{name}' from Wrappable '{self._func.__name__}'"
            )
        self.wrappers.pop(name)
        log(
            f"Removed wrapper '{name}' from Wrappable '{self._func.__name__}'.",
            context="Wrapping"
        )

    def __call__(self, *args, **kwargs):
        if self.wrappers:
            return self._wrapped(iter(self.wrappers.values()))(*args, **kwargs)
        else:
            return self._func(*args, **kwargs)

    def _wrapped(self, iter_wraps):
        next_wrap = next(iter_wraps, None)
        if next_wrap:
            def _func(*args, **kwargs):
                return next_wrap(self._wrapped(iter_wraps), *args, **kwargs)
        else:
            _func = self._func
        return _func

    def __get__(self, instance, cls=None):
        if instance is None:
            return self
        else:
            return types.MethodType(self, instance)


# Override the original Context.reply with a wrappable utility
reply = LionContext.wrappable_util(Context.reply)

import datetime

import discord
from cmdClient import Context
from cmdClient.logger import log

reply_callbacks: list = [] # TODO Extend to all cmdClient.Context.Utils to give flexibility to modules

class LionContext(Context):
    """
    Subclass to allow easy attachment of custom hooks and structure to contexts.
    """

    def __init__(self, client, **kwargs):
        super().__init__(client, **kwargs)
    
    @classmethod
    def util(self, util_func):
        """
        Decorator to make a utility function available as a Context instance method
        """
        log('added util_function: ' + util_func.__name__)

        def util_fun_wrapper(*args, **kwargs):
            [args, kwargs] = self.util_pre(util_func, *args, **kwargs)            
            return util_func(*args, **kwargs)

        util_fun_wrapper.__name__ = util_func.__name__      # Hack

        super().util(util_fun_wrapper)

    @classmethod
    def util_pre(self, util_func, *args, **kwargs):

        if util_func.__name__ == 'reply':
            for cb in reply_callbacks:
                [args, kwargs] = cb(util_func, *args, **kwargs)    # Nesting handlers. Note: args and kwargs are mutable
                
        return [args, kwargs]


def register_reply_callback(func):
    reply_callbacks.append(func)

def unregister_reply_callback(func):
    reply_callbacks.remove(func)



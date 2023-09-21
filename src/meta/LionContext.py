import types
import logging
from collections import namedtuple
from typing import Optional, TYPE_CHECKING

import discord
from discord.enums import ChannelType
from discord.ext.commands import Context
from babel.translator import ctx_locale

if TYPE_CHECKING:
    from .LionBot import LionBot
    from core.lion_member import LionMember
    from core.lion_user import LionUser
    from core.lion_guild import LionGuild


logger = logging.getLogger(__name__)


"""
Stuff that might be useful to implement (see cmdClient):
    sent_messages cache
    tasks cache
    error reply
    usage
    interaction cache
    View cache?
    setting access
"""


FlatContext = namedtuple(
    'FlatContext',
    ('message',
     'interaction',
     'guild',
     'author',
     'channel',
     'alias',
     'prefix',
     'failed')
)


class LionContext(Context['LionBot']):
    """
    Represents the context a command is invoked under.

    Extends Context to add Lion-specific methods and attributes.
    Also adds several contextual wrapped utilities for simpler user during command invocation.
    """
    luser: 'LionUser'
    lguild: 'LionGuild'
    lmember: 'LionMember'
    alion: 'LionUser | LionMember'

    def __repr__(self):
        parts = {}
        if self.interaction is not None:
            parts['iid'] = self.interaction.id
            parts['itype'] = f"\"{self.interaction.type.name}\""
        if self.message is not None:
            parts['mid'] = self.message.id
        if self.author is not None:
            parts['uid'] = self.author.id
            parts['uname'] = f"\"{self.author.name}\""
        if self.channel is not None:
            parts['cid'] = self.channel.id
            if self.channel.type is ChannelType.private:
                parts['cname'] = f"\"{self.channel.recipient}\""
            else:
                parts['cname'] = f"\"{self.channel.name}\""
        if self.guild is not None:
            parts['gid'] = self.guild.id
            parts['gname'] = f"\"{self.guild.name}\""
        if self.command is not None:
            parts['cmd'] = f"\"{self.command.qualified_name}\""
        if self.invoked_with is not None:
            parts['alias'] = f"\"{self.invoked_with}\""
        if self.command_failed:
            parts['failed'] = self.command_failed
        parts['locale'] = f"\"{ctx_locale.get()}\""

        return "<LionContext: {}>".format(
            ' '.join(f"{name}={value}" for name, value in parts.items())
        )

    def flatten(self):
        """Flat pure-data context information, for caching and logging."""
        return FlatContext(
            self.message.id,
            self.interaction.id if self.interaction is not None else None,
            self.guild.id if self.guild is not None else None,
            self.author.id if self.author is not None else None,
            self.channel.id if self.channel is not None else None,
            self.invoked_with,
            self.prefix,
            self.command_failed
        )

    @classmethod
    def util(cls, util_func):
        """
        Decorator to make a utility function available as a Context instance method.
        """
        setattr(cls, util_func.__name__, util_func)
        logger.debug(f"Attached context utility function: {util_func.__name__}")
        return util_func

    @classmethod
    def wrappable_util(cls, util_func):
        """
        Decorator to add a Wrappable utility function as a Context instance method.
        """
        wrapped = Wrappable(util_func)
        setattr(cls, util_func.__name__, wrapped)
        logger.debug(f"Attached wrappable context utility function: {util_func.__name__}")
        return wrapped

    async def error_reply(self, content: Optional[str] = None, **kwargs):
        if content and 'embed' not in kwargs:
            embed = discord.Embed(
                colour=discord.Colour.red(),
                description=content
            )
            kwargs['embed'] = embed
            content = None

        # Expect this may be run in highly unusual circumstances.
        # This should never error, or at least handle all errors.
        if self.interaction:
            kwargs.setdefault('ephemeral', True)
        try:
            await self.reply(content=content, **kwargs)
        except discord.HTTPException:
            pass
        except Exception:
            logger.exception(
                "Unknown exception in 'error_reply'.",
                extra={'action': 'error_reply', 'ctx': repr(self), 'with_ctx': True}
            )


class Wrappable:
    __slots__ = ('_func', 'wrappers')

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
        logger.debug(
            f"Added wrapper '{name}' to Wrappable '{self._func.__name__}'.",
            extra={'action': "Wrap Util"}
        )

    def remove_wrapper(self, name):
        if not self.wrappers or name not in self.wrappers:
            raise ValueError(
                f"Cannot remove non-existent wrapper '{name}' from Wrappable '{self._func.__name__}'"
            )
        self.wrappers.pop(name)
        logger.debug(
            f"Removed wrapper '{name}' from Wrappable '{self._func.__name__}'.",
            extra={'action': "Unwrap Util"}
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


LionContext.reply = Wrappable(LionContext.reply)


# @LionContext.reply.add_wrapper
# async def think(func, ctx, *args, **kwargs):
#     await ctx.channel.send("thinking")
#     await func(ctx, *args, **kwargs)

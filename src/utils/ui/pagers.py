from typing import List, Coroutine, Optional, Any, Type, TypeVar, Callable, Dict
from collections import defaultdict

import discord
from discord.ui.button import Button, button
from discord import app_commands as appcmds

from meta.logger import log_action_stack, logging_context
from meta.errors import SafeCancellation
from meta.config import conf

from babel.translator import ctx_translator

from ..lib import MessageArgs, error_embed
from .. import util_babel

from .leo import LeoUI

_p = util_babel._p


__all__ = (
    'BasePager',
    'Pager',
)


class BasePager(LeoUI):
    """
    An ABC describing the common interface for a Paging UI.

    A paging UI represents a sequence of pages, accessible by `next` and `previous` buttons,
    and possibly by a dropdown (not implemented).

    A `Page` is represented as a `MessageArgs` object, which is passable to `send` and `edit` methods as required.

    Each page of a paging UI is accessed through the coroutine `get_page`.
    This allows for more complex paging schemes where the pages are expensive to compute,
    and not generally needed simultaneously.
    In general, `get_page` should cache expensive pages,
    perhaps simply with a `cached` decorator, but this is not enforced.

    The state of the base UI is represented as the current `page_num` and the `current_page`.

    This class also maintains an `active_pagers` cache,
    representing all `BasePager`s that are currently running.
    This allows access from external page controlling utilities, e.g. the `/page` command.
    """
    # List of valid keys indicating movement to the next page
    next_list = _p('cmd:page|pager:Pager|options:next', "n, nxt, next, forward, +")

    # List of valid keys indicating movement to the previous page
    prev_list = _p('cmd:page|pager:Pager|options:prev', "p, prev, back, -")

    # List of valid keys indicating movement to the first page
    first_list = _p('cmd:page|pager:Pager|options:first', "f, first, one, start")

    # List of valid keys indicating movement to the last page
    last_list = _p('cmd:page|pager:Pager|options:last', "l, last, end")
    # channelid -> pager.id -> list of active pagers in this channel
    active_pagers: dict[int, dict[int, 'BasePager']] = defaultdict(dict)

    page_num: int
    current_page: MessageArgs
    _channelid: Optional[int]

    @classmethod
    def get_active_pager(self, channelid, userid):
        """
        Get the last active pager in the `destinationid`, which may be accessed by `userid`.
        Returns None if there are no matching pagers.
        """
        for pager in reversed(self.active_pagers[channelid].values()):
            if pager.access_check(userid):
                return pager

    def set_active(self):
        if self._channelid is None:
            raise ValueError("Cannot set active without a channelid.")
        self.active_pagers[self._channelid][self.id] = self

    def set_inactive(self):
        self.active_pagers[self._channelid].pop(self.id, None)

    def access_check(self, userid):
        """
        Check whether the given userid is allowed to use this UI.
        Must be overridden by subclasses.
        """
        raise NotImplementedError

    async def get_page(self, page_id) -> MessageArgs:
        """
        `get_page` returns the specified page number, starting from 0.
        An implementation of `get_page` must:
            - Always return a page (if no data is a valid state, must return a placeholder page).
            - Always accept out-of-range `page_id` values.
                - There is no behaviour specified for these, although they will usually be modded into the correct
                range.
                - In some cases (e.g. stream data where we don't have a last page),
                they may simply return the last correct page instead.

        """
        raise NotImplementedError

    async def page_cmd(self, interaction: discord.Interaction, value: str):
        """
        Command implementation for the paging command.
        Pager subclasses should override this if they use `active_pagers`.
        Default implementation is essentially a no-op,
        simply replying to the interaction.
        """
        await interaction.response.defer()
        return

    async def page_acmpl(self, interaction: discord.Interaction, partial: str):
        """
        Command autocompletion for the paging command.
        Pager subclasses should override this if they use `active_pagers`.
        """
        return []

    @button(emoji=conf.emojis.getemoji('forward'))
    async def next_page_button(self, interaction: discord.Interaction, press):
        await interaction.response.defer()
        self.page_num += 1
        await self.redraw()

    @button(emoji=conf.emojis.getemoji('backward'))
    async def prev_page_button(self, interaction: discord.Interaction, press):
        await interaction.response.defer()
        self.page_num -= 1
        await self.redraw()

    async def refresh(self):
        """
        Recalculate current computed state.
        (E.g. fetch current page, set layout, disable components, etc.)
        """
        self.current_page = await self.get_page(self.page_num)

    async def redraw(self):
        """
        This should refresh the current state and redraw the UI.
        Not implemented here, as the implementation depends on whether this is a reaction response ephemeral UI
        or a message=based one.
        """
        raise NotImplementedError


class Pager(BasePager):
    """
    MicroUI to display a sequence of static pages,
    supporting paging reaction and paging commands.

    Parameters
    ----------
    pages: list[MessageArgs]
        A non-empty list of message arguments to page.
    start_from: int
        The page number to display first.
        Default: 0
    locked: bool
        Whether to only allow the author to use the paging interface.
    """

    def __init__(self, pages: list[MessageArgs],
                 start_from=0,
                 show_cancel=False, delete_on_cancel=True, delete_after=False, **kwargs):
        super().__init__(**kwargs)
        self._pages = pages
        self.page_num = start_from
        self.current_page = pages[self.page_num]

        self._locked = True
        self._ownerid: Optional[int] = None
        self._channelid: Optional[int] = None

        if not pages:
            raise ValueError("Cannot run Pager with no pages.")

        self._original: Optional[discord.Interaction] = None
        self._is_followup: bool = False
        self._message: Optional[discord.Message] = None

        self.show_cancel = show_cancel
        self._delete_on_cancel = delete_on_cancel
        self._delete_after = delete_after

    @property
    def ownerid(self):
        if self._ownerid is not None:
            return self._ownerid
        elif self._original:
            return self._original.user.id
        else:
            return None

    def access_check(self, userid):
        return not self._locked or (userid == self.ownerid)

    async def interaction_check(self, interaction: discord.Interaction):
        return self.access_check(interaction.user.id)

    @button(emoji=conf.emojis.getemoji('cancel'))
    async def cancel_button(self, interaction: discord.Interaction, press: Button):
        await interaction.response.defer()
        if self._delete_on_cancel:
            self._delete_after = True
        await self.close()

    async def cleanup(self):
        self.set_inactive()

        # If we still have a message, delete it or clear the view
        try:
            if self._is_followup:
                if self._message:
                    if self._delete_after:
                        await self._message.delete()
                    else:
                        await self._message.edit(view=None)
            else:
                if self._original and not self._original.is_expired():
                    if self._delete_after:
                        await self._original.delete_original_response()
                    else:
                        await self._original.edit_original_response(view=None)
        except discord.HTTPException:
            # Nothing we can do here
            pass

    async def get_page(self, page_id):
        page_id %= len(self._pages)
        return self._pages[page_id]

    def page_count(self):
        return len(self.pages)

    async def page_cmd(self, interaction: discord.Interaction, value: str):
        """
        `/page` command for the `Pager` MicroUI.
        """
        await interaction.response.defer(ephemeral=True)
        t = ctx_translator.get().t
        nexts = {word.strip() for word in t(self.next_list).split(',')}
        prevs = {word.strip() for word in t(self.prev_list).split(',')}
        firsts = {word.strip() for word in t(self.first_list).split(',')}
        lasts = {word.strip() for word in t(self.last_list).split(',')}

        if value:
            value = value.lower().strip()
            if value.isdigit():
                # Assume value is page number
                self.page_num = int(value) - 1
                if self.page_num == -1:
                    self.page_num = 0
            elif value in firsts:
                self.page_num = 0
            elif value in nexts:
                self.page_num += 1
            elif value in prevs:
                self.page_num -= 1
            elif value in lasts:
                self.page_num = -1
            elif value.startswith('-') and value[1:].isdigit():
                self.page_num = - int(value[1:])
            else:
                await interaction.edit_original_response(
                    embed=error_embed(
                        t(_p(
                            'cmd:page|pager:Pager|error:parse',
                            "Could not understand page specification `{value}`."
                        )).format(value=value)
                    )
                )
                return
        await interaction.delete_original_response()
        await self.redraw()

    async def page_acmpl(self, interaction: discord.Interaction, partial: str):
        """
        `/page` command autocompletion for the `Pager` MicroUI.
        """
        t = ctx_translator.get().t
        nexts = {word.strip() for word in t(self.next_list).split(',')}
        prevs = {word.strip() for word in t(self.prev_list).split(',')}
        firsts = {word.strip() for word in t(self.first_list).split(',')}
        lasts = {word.strip() for word in t(self.last_list).split(',')}

        total = len(self._pages)
        num = self.page_num
        page_choices: dict[int, str] = {}

        # TODO: Support page names and hints?

        if len(self._pages) > 10:
            # First add the general choices
            if num < total-1:
                page_choices[total-1] = t(_p(
                            'cmd:page|acmpl|pager:Pager|choice:last',
                            "Last: Page {page}/{total}"
                        )).format(page=total, total=total)

            page_choices[num] = t(_p(
                'cmd:page|acmpl|pager:Pager|choice:current',
                "Current: Page {page}/{total}"
            )).format(page=num+1, total=total)
            choices = [
                appcmds.Choice(name=string[:100], value=str(num+1))
                for num, string in sorted(page_choices.items(), key=lambda t: t[0])
            ]
        else:
            # Particularly support page names here
            choices = [
                appcmds.Choice(
                    name=('> ' * (i == num) + t(_p(
                        'cmd:page|acmpl|pager:Pager|choice:general',
                        "Page {page}"
                    )).format(page=i+1))[:100],
                    value=str(i+1)
                )
                for i in range(0, total)
            ]

        partial = partial.strip()

        if partial:
            value = partial.lower().strip()
            if value.isdigit():
                # Assume value is page number
                page_num = int(value) - 1
                if page_num == -1:
                    page_num = 0
            elif value in firsts:
                page_num = 0
            elif value in nexts:
                page_num = self.page_num + 1
            elif value in prevs:
                page_num = self.page_num - 1
            elif value in lasts:
                page_num = -1
            elif value.startswith('-') and value[1:].isdigit():
                page_num = - int(value[1:])
            else:
                page_num = None

            if page_num is not None:
                page_num %= total
                choice = appcmds.Choice(
                    name=t(_p(
                        'cmd:page|acmpl|pager:Page|choice:select',
                        "Selected: Page {page}/{total}"
                    )).format(page=page_num+1, total=total)[:100],
                    value=str(page_num + 1)
                )
                return [choice, *choices]
            else:
                return [
                    appcmds.Choice(
                        name=t(_p(
                            'cmd:page|acmpl|pager:Page|error:parse',
                            "No matching pages!"
                        )).format(page=page_num, total=total)[:100],
                        value=partial
                    )
                ]
        else:
            return choices

    @property
    def page_row(self):
        if self.show_cancel:
            if len(self._pages) > 1:
                return (self.prev_page_button, self.cancel_button, self.next_page_button)
            else:
                return (self.cancel_button,)
        else:
            if len(self._pages) > 1:
                return (self.prev_page_button, self.next_page_button)
            else:
                return ()

    async def refresh(self):
        await super().refresh()
        self.set_layout(self.page_row)

    async def redraw(self):
        await self.refresh()

        if not self._original:
            raise ValueError("Running run pager manually without interaction.")

        try:
            if self._message:
                await self._message.edit(**self.current_page.edit_args, view=self)
            else:
                if self._original.is_expired():
                    raise SafeCancellation("This interface has expired, please try again.")
                await self._original.edit_original_response(**self.current_page.edit_args, view=self)
        except discord.HTTPException:
            raise SafeCancellation("Could not page your results! Please try again.")

    async def run(self, interaction: discord.Interaction, ephemeral=False, locked=True, ownerid=None, **kwargs):
        """
        Display the UI.
        Attempts to reply to the interaction if it has not already been replied to,
        otherwise send a follow-up.

        An ephemeral response must be sent as an initial interaction response.
        On the other hand, a semi-persistent response (expected to last longer than the lifetime of the interaction)
        must be sent as a followup.

        Extra kwargs are combined with the first page arguments and given to the relevant send method.

        Parameters
        ----------
        interaction: discord.Interaction
            The interaction to send the pager in response to.
        ephemeral: bool
            Whether to send the interaction ephemerally.
            If this is true, the interaction *must* be fresh (i.e. no response done).
            Default: False
        locked: bool
            Whether this interface is locked to the user `self.ownerid`.
            Irrelevant for ephemeral messages.
            Use `ownerid` to override the default owner id.
            Defaults to true for fail-safety.
            Default: True
        ownerid: Optional[int]
            The userid allowed to use this interaction.
            By default, this will be the `interaction.user.id`,
            presuming that this is the user which originally triggered this message.
            An override may be useful if a user triggers a paging UI for someone else.
        """
        if not interaction.channel_id:
            raise ValueError("Cannot run pager on a channelless interaction.")

        self._original = interaction
        self._ownerid = ownerid
        self._locked = locked
        self._channelid = interaction.channel_id

        await self.refresh()
        args = self.current_page.send_args | kwargs

        if interaction.response.is_done():
            if ephemeral:
                raise ValueError("Ephemeral response requires fres interaction.")
            self._message = await interaction.followup.send(**args, view=self)
            self._is_followup = True
        else:
            self._is_followup = False
            await interaction.response.send_message(**args, view=self)

        self.set_active()

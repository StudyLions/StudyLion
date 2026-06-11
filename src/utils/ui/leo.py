from typing import List, Optional, Any, Dict
import asyncio
import logging
import time
from contextvars import copy_context, Context

import discord
from discord.ui import Modal, View, Item

from meta.logger import log_action_stack, logging_context
from meta.errors import SafeCancellation
# --- AI-MODIFIED (2026-03-14) ---
# Purpose: Import babel context vars for locale resolution in UI dispatch
from babel.translator import ctx_locale, ctx_translator, SOURCE_LOCALE
# --- END AI-MODIFIED ---

from gui.errors import RenderingException

from . import logger
from ..lib import MessageArgs, error_embed

# --- AI-REPLACED (2026-04-06) ---
# Reason: Expanded to also inject a "Report a Bug" feedback link button alongside the vote button
# What the new code does better: Adds a support-server link button in the same row as the vote
# button, giving users a one-click path to report bugs or request features from any UI.
# --- Original code (commented out for rollback) ---
# async def _maybe_append_vote_button(ui: 'LeoUI') -> None:
#     if ui._layout is None or len(ui._layout) >= 5:
#         return
#     bot = getattr(ui, 'bot', None)
#     if bot is None:
#         return
#     userid = getattr(ui, 'userid', None) or getattr(ui, '_callerid', None) or getattr(ui, '_ownerid', None)
#     if not userid:
#         user_obj = getattr(ui, 'user', None) or getattr(ui, 'caller', None)
#         if user_obj and hasattr(user_obj, 'id'):
#             userid = user_obj.id
#     if not userid:
#         return
#     try:
#         voting = bot.get_cog('TopggCog')
#         if not voting:
#             return
#         btn = await voting.vote_button_for_user(userid)
#         layout = list(ui._layout)
#         layout.append((btn,))
#         ui._layout = tuple(layout)
#     except Exception:
#         logger.debug("Vote button injection failed silently", exc_info=True)
# --- End original code ---
async def _maybe_append_vote_button(ui: 'LeoUI') -> None:
    if ui._layout is None or len(ui._layout) >= 5:
        return

    bot = getattr(ui, 'bot', None)
    if bot is None:
        return

    userid = getattr(ui, 'userid', None) or getattr(ui, '_callerid', None) or getattr(ui, '_ownerid', None)
    if not userid:
        user_obj = getattr(ui, 'user', None) or getattr(ui, 'caller', None)
        if user_obj and hasattr(user_obj, 'id'):
            userid = user_obj.id
    if not userid:
        return

    try:
        row_items = []

        voting = bot.get_cog('TopggCog')
        if voting:
            row_items.append(await voting.vote_button_for_user(userid))

        support_url = getattr(getattr(bot.config, 'bot', None), 'support_guild', None)
        if support_url:
            row_items.append(discord.ui.Button(
                label="Report a Bug",
                emoji="\U0001F41B",
                url=str(support_url),
                style=discord.ButtonStyle.link,
            ))

        if row_items:
            layout = list(ui._layout)
            layout.append(tuple(row_items))
            ui._layout = tuple(layout)
    except Exception:
        logger.debug("Global button injection failed silently", exc_info=True)
# --- END AI-REPLACED ---

__all__ = (
    'LeoUI',
    'MessageUI',
    'LeoModal',
    'error_handler_for'
)


class LeoUI(View):
    """
    View subclass for small-scale user interfaces.

    While a 'View' provides an interface for managing a collection of components,
    a `LeoUI` may also manage a message, and potentially slave Views or UIs.
    The `LeoUI` also exposes more advanced cleanup and timeout methods,
    and preserves the context.
    """

    def __init__(self, *args, ui_name=None, context=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        if context is None:
            self._context = copy_context()
        else:
            self._context = context

        self._name = ui_name or self.__class__.__name__
        self._context.run(log_action_stack.set, [*self._context[log_action_stack], self._name])

        # List of slaved views to stop when this view stops
        self._slaves: List[View] = []

        # TODO: Replace this with a substitutable ViewLayout class
        self._layout: Optional[tuple[tuple[Item, ...], ...]] = None

    @property
    def _stopped(self) -> asyncio.Future:
        """
        Return an future indicating whether the View has finished interacting.

        Currently exposes a hidden attribute of the underlying View.
        May be reimplemented in future.
        """
        # --- AI-MODIFIED (2026-03-20) ---
        # Purpose: discord.py 2.7.1 moved __stopped from View to BaseView
        # --- Original code (commented out for rollback) ---
        # return self._View__stopped
        # --- End original code ---
        return self._BaseView__stopped
        # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-21) ---
    # Purpose: Strip component 'id' fields from payloads to prevent duplicate ID
    # errors. discord.py 2.7+ populates component IDs from Discord's auto-assigned
    # values via _refresh(), but when the layout changes dynamically (e.g. TasklistUI
    # toggling buttons), stale IDs collide with Discord's new auto-assignments.
    # --- Original code (commented out for rollback) ---
    # def to_components(self) -> List[Dict[str, Any]]:
    #     """
    #     Extending component generator to apply the set _layout, if it exists.
    #     """
    #     if self._layout is not None:
    #         # Alternative rendering using layout
    #         components = []
    #         for i, row in enumerate(self._layout):
    #             # Skip empty rows
    #             if not row:
    #                 continue
    #
    #             # Since we aren't relying on ViewWeights, manually check width here
    #             if sum(item.width for item in row) > 5:
    #                 raise ValueError(f"Row {i} of custom {self.__class__.__name__} is too wide!")
    #
    #             # Create the component dict for this row
    #             components.append({
    #                 'type': 1,
    #                 'components': [item.to_component_dict() for item in row]
    #             })
    #     else:
    #         components = super().to_components()
    #
    #     return components
    # --- End original code ---
    def to_components(self) -> List[Dict[str, Any]]:
        """
        Extending component generator to apply the set _layout, if it exists.
        """
        if self._layout is not None:
            components = []
            for i, row in enumerate(self._layout):
                if not row:
                    continue

                if sum(item.width for item in row) > 5:
                    raise ValueError(f"Row {i} of custom {self.__class__.__name__} is too wide!")

                components.append({
                    'type': 1,
                    'components': [item.to_component_dict() for item in row]
                })
        else:
            components = super().to_components()

        for row in components:
            for comp in row.get('components', []):
                comp.pop('id', None)

        return components
    # --- END AI-MODIFIED ---

    def set_layout(self, *rows: tuple[Item, ...]) -> None:
        """
        Set the layout of the rendered View as a matrix of items,
        or more precisely, a list of action rows.

        This acts independently of the existing sorting with `_ViewWeights`,
        and overrides the sorting if applied.
        """
        self._layout = rows

    async def cleanup(self):
        """
        Coroutine to run when timeing out, stopping, or cancelling.
        Generally cleans up any open resources, and removes any leftover components.
        """
        logging.debug(f"{self!r} running default cleanup.", extra={'action': 'cleanup'})
        return None

    def stop(self):
        """
        Extends View.stop() to also stop all the slave views.
        Note that stopping is idempotent, so it is okay if close() also calls stop().
        """
        for slave in self._slaves:
            slave.stop()
        super().stop()

    async def close(self, msg=None):
        self.stop()
        await self.cleanup()

    async def pre_timeout(self):
        """
        Task to execute before actually timing out.
        This may cancel the timeout by refreshing or rescheduling it.
        (E.g. to ask the user whether they want to keep going.)

        Default implementation does nothing.
        """
        return None

    async def on_timeout(self):
        """
        Task to execute after timeout is complete.
        Default implementation calls cleanup.
        """
        await self.cleanup()

    async def __dispatch_timeout(self):
        """
        This essentially extends View._dispatch_timeout,
        to include a pre_timeout task
        which may optionally refresh and hence cancel the timeout.
        """
        # --- AI-MODIFIED (2026-03-20) ---
        # Purpose: discord.py 2.7.1 moved __stopped to BaseView; use public API
        # --- Original code (commented out for rollback) ---
        # if self._View__stopped.done():
        # --- End original code ---
        if self.is_finished():
        # --- END AI-MODIFIED ---
            # We are already stopped, nothing to do
            return

        with logging_context(action='Timeout'):
            try:
                await self.pre_timeout()
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                pass
            except Exception:
                # --- AI-MODIFIED (2026-04-02) ---
                # Purpose: Fix missing format arg -- {self!r} was literal text, not interpolated
                await logger.exception(
                    "Unhandled error caught while dispatching timeout for %r.",
                    self,
                    extra={'with_ctx': True, 'action': 'Error'}
                )
                # --- END AI-MODIFIED ---

            # Check if we still need to timeout
            if self.timeout is None:
                # The timeout was removed entirely, silently walk away
                return

            # --- AI-MODIFIED (2026-03-20) ---
            # Purpose: discord.py 2.7.1 moved internals from View to BaseView
            # --- Original code (commented out for rollback) ---
            # if self._View__stopped.done():
            #     return
            # now = time.monotonic()
            # if self._View__timeout_expiry is not None and now < self._View__timeout_expiry:
            #     if self._View__timeout_task is None or self._View__timeout_task.done():
            #         self._View__timeout_task = asyncio.create_task(self._View__timeout_task_impl())
            # --- End original code ---
            if self.is_finished():
                # We stopped while waiting for the pre timeout.
                # Or maybe another thread timed us out
                # Either way, we are done here
                return

            now = time.monotonic()
            if self._BaseView__timeout_expiry is not None and now < self._BaseView__timeout_expiry:
                # The timeout was extended, make sure the timeout task is running then fade away
                if self._BaseView__timeout_task is None or self._BaseView__timeout_task.done():
                    self._BaseView__timeout_task = asyncio.create_task(self._BaseView__timeout_task_impl())
            # --- END AI-MODIFIED ---
            else:
                # Actually timeout, and call the post-timeout task for cleanup.
                self._really_timeout()
                await self.on_timeout()

    def _dispatch_timeout(self):
        """
        Overriding timeout method completely, to support interactive flow during timeout,
        and optional refreshing of the timeout.
        """
        return self._context.run(asyncio.create_task, self.__dispatch_timeout())

    def _really_timeout(self):
        """
        Actuallly times out the View.
        This copies View._dispatch_timeout, apart from the `on_timeout` dispatch,
        which is now handled by `__dispatch_timeout`.
        """
        # --- AI-MODIFIED (2026-03-20) ---
        # Purpose: discord.py 2.7.1 moved internals from View to BaseView
        # --- Original code (commented out for rollback) ---
        # if self._View__stopped.done():
        #     return
        # if self._View__cancel_callback:
        #     self._View__cancel_callback(self)
        #     self._View__cancel_callback = None
        # self._View__stopped.set_result(True)
        # --- End original code ---
        if self.is_finished():
            return

        if self._BaseView__cancel_callback:
            self._BaseView__cancel_callback(self)
            self._BaseView__cancel_callback = None

        self._BaseView__stopped.set_result(True)
        # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-14) ---
    # Purpose: Ensure translator and locale context are available for all UI interactions,
    # especially persistent views that weren't created from a command context.
    def _dispatch_item(self, item, interaction, /):
        if self._context.get(ctx_translator, None) is None:
            self._context.run(ctx_translator.set, interaction.client.translator)
        if self._context.get(ctx_locale, SOURCE_LOCALE) == SOURCE_LOCALE and interaction.locale:
            self._context.run(ctx_locale.set, interaction.locale.value)
        return self._context.run(super()._dispatch_item, item, interaction)
    # --- END AI-MODIFIED ---

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: Item):
        """
        Default LeoUI error handle.
        This may be tail extended by subclasses to preserve the exception stack.
        """
        # --- AI-MODIFIED (2026-06-11) ---
        # Purpose: during a shutdown/restart, cogs unload while live UIs still
        #   dispatch component clicks; handlers then fail on missing internals
        #   (observed live: bot.core was None mid-restart → AttributeError in
        #   the leaderboard UI) and the bugsplat reply itself usually fails
        #   too. Drop these quietly instead of logging an unhandled exception.
        client = interaction.client
        if client.is_closed() or getattr(client, 'core', None) is None:
            logger.debug(
                f"Ignoring UI interaction error during shutdown/startup in {self!r}: {error!r}"
            )
            return
        # --- END AI-MODIFIED ---
        try:
            raise error
        except SafeCancellation as e:
            if e.msg and not interaction.is_expired():
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(
                            embed=error_embed(e.msg),
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            embed=error_embed(e.msg),
                            ephemeral=True
                        )
                except discord.HTTPException:
                    pass
            logger.debug(
                f"Caught a safe cancellation from LeoUI: {e.details}",
                extra={'action': 'Cancel'}
            )
        except RenderingException as e:
            logger.info(
                f"UI interaction failed due to rendering exception: {repr(e)}"
            )
            embed = interaction.client.tree.rendersplat(e)
            await interaction.client.tree.error_reply(interaction, embed)
        # --- AI-MODIFIED (2026-04-05) ---
        # Purpose: Show actionable permission error instead of generic bugsplat for UI interactions
        except discord.Forbidden as e:
            logger.warning(
                f"Forbidden error in UI item {item!r} of LeoUI {self!r}: {interaction.data}",
                exc_info=True,
                extra={'with_ctx': True, 'action': 'UIForbidden'}
            )
            embed = interaction.client.tree.forbidden_embed(interaction, e)
            await interaction.client.tree.error_reply(interaction, embed)
        # --- END AI-MODIFIED ---
        except Exception:
            logger.exception(
                f"Unhandled interaction exception occurred in item {item!r} of LeoUI {self!r} from interaction: "
                f"{interaction.data}",
                extra={'with_ctx': True, 'action': 'UIError'}
            )
            # Explicitly handle the bugsplat ourselves
            splat = interaction.client.tree.bugsplat(interaction, error)
            await interaction.client.tree.error_reply(interaction, splat)


class MessageUI(LeoUI):
    """
    Simple single-message LeoUI, intended as a framework for UIs
    attached to a single interaction response.

    UIs may also be sent as regular messages by using `send(channel)` instead of `run(interaction)`.
    """

    def __init__(self, *args, callerid: Optional[int] = None, **kwargs):
        super().__init__(*args, **kwargs)

        # ----- UI state -----
        # User ID of the original caller (e.g. command author).
        # Mainly used for interaction usage checks and logging
        self._callerid = callerid

        # Original interaction, if this UI is sent as an interaction response
        self._original: discord.Interaction = None

        # Message holding the UI, when the UI is sent attached to a followup
        self._message: discord.Message = None

        # Refresh lock, to avoid cache collisions on refresh
        self._refresh_lock = asyncio.Lock()

    @property
    def channel(self):
        if self._original is not None:
            return self._original.channel
        else:
            return self._message.channel

    # ----- UI API -----
    async def run(self, interaction: discord.Interaction, **kwargs):
        """
        Run the UI as a response or followup to the given interaction.

        Should be extended if more complex run mechanics are needed
        (e.g. registering listeners or setting up caches).
        """
        await self.draw(interaction, **kwargs)

    async def refresh(self, *args, thinking: Optional[discord.Interaction] = None, **kwargs):
        """
        Reload and redraw this UI.

        Primarily a hook-method for use by parents and other controllers.
        Performs a full data and reload and refresh (maintaining UI state, e.g. page n).
        """
        async with self._refresh_lock:
            # Reload data
            await self.reload()
            # Redraw UI message
            await self.redraw(thinking=thinking)

    async def quit(self):
        """
        Quit the UI.

        This usually involves removing the original message,
        and stopping or closing the underlying View.
        """
        for child in self._slaves:
            # TODO: Better to use duck typing or interface typing
            if isinstance(child, MessageUI) and not child.is_finished():
                asyncio.create_task(child.quit())
        try:
            if self._original is not None and not self._original.is_expired():
                await self._original.delete_original_response()
                self._original = None
            if self._message is not None:
                await self._message.delete()
                self._message = None
        except discord.HTTPException:
            pass

        # Note close() also runs cleanup and stop
        await self.close()

    # ----- UI Flow -----
    async def interaction_check(self, interaction: discord.Interaction):
        """
        Check the given interaction is authorised to use this UI.

        Default implementation simply checks that the interaction is
        from the original caller.
        Extend for more complex logic.
        """
        return interaction.user.id == self._callerid

    async def make_message(self) -> MessageArgs:
        """
        Create the UI message body, depening on the current state.

        Called upon each redraw.
        Should handle caching if message construction is for some reason intensive.

        Must be implemented by concrete UI subclasses.
        """
        raise NotImplementedError

    async def refresh_layout(self):
        """
        Asynchronously refresh the message components,
        and explicitly set the message component layout.

        Called just before redrawing, before `make_message`.

        Must be implemented by concrete UI subclasses.
        """
        raise NotImplementedError

    async def reload(self):
        """
        Reload and recompute the underlying data for this UI.

        Must be implemented by concrete UI subclasses.
        """
        raise NotImplementedError

    async def draw(self, interaction, force_followup=False, **kwargs):
        """
        Send the UI as a response or followup to the given interaction.

        If the interaction has been responded to, or `force_followup` is set,
        creates a followup message instead of a response to the interaction.
        """
        # Initial data loading
        await self.reload()
        # Set the UI layout
        await self.refresh_layout()
        # --- AI-MODIFIED (2026-03-19) ---
        # Purpose: Inject vote button globally on all MessageUI commands
        await _maybe_append_vote_button(self)
        # --- END AI-MODIFIED ---
        # Fetch message arguments
        args = await self.make_message()

        as_followup = force_followup or interaction.response.is_done()
        if as_followup:
            self._message = await interaction.followup.send(**args.send_args, **kwargs, view=self)
        else:
            self._original = interaction
            await interaction.response.send_message(**args.send_args, **kwargs, view=self)

    async def send(self, channel: discord.abc.Messageable, **kwargs):
        """
        Alternative to draw() which uses a discord.abc.Messageable.
        """
        await self.reload()
        await self.refresh_layout()
        # --- AI-MODIFIED (2026-03-19) ---
        await _maybe_append_vote_button(self)
        # --- END AI-MODIFIED ---
        args = await self.make_message()
        self._message = await channel.send(**args.send_args, view=self)

    async def _redraw(self, args):
        if self._original and not self._original.is_expired():
            await self._original.edit_original_response(**args.edit_args, view=self)
        elif self._message:
            await self._message.edit(**args.edit_args, view=self)
        else:
            # Interaction expired or already closed. Quietly cleanup.
            await self.close()

    async def redraw(self, thinking: Optional[discord.Interaction] = None):
        """
        Update the output message for this UI.

        If a thinking interaction is provided, deletes the response while redrawing.
        """
        await self.refresh_layout()
        # --- AI-MODIFIED (2026-03-19) ---
        await _maybe_append_vote_button(self)
        # --- END AI-MODIFIED ---
        args = await self.make_message()

        if thinking is not None and not thinking.is_expired() and thinking.response.is_done():
            asyncio.create_task(thinking.delete_original_response())

        try:
            await self._redraw(args)
        except discord.HTTPException as e:
            # Unknown communication error, nothing we can reliably do. Exit quietly.
            logger.warning(
                f"Unexpected UI redraw failure occurred in {self}: {repr(e)}",
            )
            await self.close()

    async def cleanup(self):
        """
        Remove message components from interaction response, if possible.

        Extend to remove listeners or clean up caches.
        `cleanup` is always called when the UI is exiting,
        through timeout or user-driven closure.
        """
        try:
            if self._original is not None and not self._original.is_expired():
                await self._original.edit_original_response(view=None)
                self._original = None
            if self._message is not None:
                await self._message.edit(view=None)
                self._message = None
        except discord.HTTPException:
            pass


class LeoModal(Modal):
    """
    Context-aware Modal class.
    """
    def __init__(self, *args, context: Optional[Context] = None, **kwargs):
        super().__init__(**kwargs)

        if context is None:
            self._context = copy_context()
        else:
            self._context = context
        self._context.run(log_action_stack.set, [*self._context[log_action_stack], self.__class__.__name__])

    # --- AI-MODIFIED (2026-03-14) ---
    # Purpose: Ensure translator and locale context are available for modal interactions
    # --- AI-REPLACED (2026-03-14) ---
    # Reason: discord.py 2.7.1 added 'resolved' param to Modal._dispatch_submit
    # --- Original code ---
    # def _dispatch_submit(self, interaction, components, /):
    #     ...
    #     return self._context.run(super()._dispatch_submit, interaction, components)
    # --- End original code ---
    def _dispatch_submit(self, interaction, components, resolved, /):
        if self._context.get(ctx_translator, None) is None:
            self._context.run(ctx_translator.set, interaction.client.translator)
        if self._context.get(ctx_locale, SOURCE_LOCALE) == SOURCE_LOCALE and interaction.locale:
            self._context.run(ctx_locale.set, interaction.locale.value)
        return self._context.run(super()._dispatch_submit, interaction, components, resolved)
    # --- END AI-REPLACED ---

    def _dispatch_item(self, item, interaction, /):
        if self._context.get(ctx_translator, None) is None:
            self._context.run(ctx_translator.set, interaction.client.translator)
        if self._context.get(ctx_locale, SOURCE_LOCALE) == SOURCE_LOCALE and interaction.locale:
            self._context.run(ctx_locale.set, interaction.locale.value)
        return self._context.run(super()._dispatch_item, item, interaction)
    # --- END AI-MODIFIED ---

    async def on_error(self, interaction: discord.Interaction, error: Exception, *args):
        """
        Default LeoModal error handle.
        This may be tail extended by subclasses to preserve the exception stack.
        """
        # --- AI-MODIFIED (2026-06-11) ---
        # Purpose: same shutdown guard as LeoUI.on_error — modals submitted
        #   while cogs are unloading fail on missing internals; drop quietly.
        client = interaction.client
        if client.is_closed() or getattr(client, 'core', None) is None:
            logger.debug(
                f"Ignoring modal error during shutdown/startup in {self!r}: {error!r}"
            )
            return
        # --- END AI-MODIFIED ---
        try:
            raise error
        except RenderingException as e:
            logger.info(
                f"Modal submit failed due to rendering exception: {repr(e)}"
            )
            embed = interaction.client.tree.rendersplat(e)
            await interaction.client.tree.error_reply(interaction, embed)
        # --- AI-MODIFIED (2026-04-05) ---
        # Purpose: Show actionable permission error instead of generic bugsplat for modal interactions
        except discord.Forbidden as e:
            logger.warning(
                f"Forbidden error in modal {self!r}: {interaction.data}",
                exc_info=True,
                extra={'with_ctx': True, 'action': 'ModalForbidden'}
            )
            embed = interaction.client.tree.forbidden_embed(interaction, e)
            await interaction.client.tree.error_reply(interaction, embed)
        # --- END AI-MODIFIED ---
        except Exception:
            logger.exception(
                f"Unhandled interaction exception occurred in {self!r}. Interaction: {interaction.data}",
                extra={'with_ctx': True, 'action': 'ModalError'}
            )
            # Explicitly handle the bugsplat ourselves
            splat = interaction.client.tree.bugsplat(interaction, error)
            await interaction.client.tree.error_reply(interaction, splat)


def error_handler_for(exc):
    def wrapper(coro):
        coro._ui_error_handler_for_ = exc
        return coro
    return wrapper

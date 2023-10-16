from typing import Optional, Callable, Any, Dict, Coroutine, Generic, TypeVar, List
import asyncio
from contextvars import copy_context

import discord
from discord import ui
from discord.ui.button import ButtonStyle, Button, button
from discord.ui.modal import Modal
from discord.ui.text_input import TextInput
from meta.errors import UserInputError

from utils.lib import tabulate, recover_context
from utils.ui import FastModal
from meta.config import conf
from meta.context import ctx_bot
from babel.translator import ctx_translator, LazyStr

from .base import BaseSetting, ParentID, SettingData, SettingValue
from . import babel

_p = babel._p


ST = TypeVar('ST', bound='InteractiveSetting')


class SettingModal(FastModal):
    input_field: TextInput = TextInput(label="Edit Setting")

    def update_field(self, new_field):
        self.remove_item(self.input_field)
        self.add_item(new_field)
        self.input_field = new_field


class SettingWidget(Generic[ST], ui.View):
    # TODO: Permission restrictions and callback!
    # Context variables for permitted user(s)? Subclass ui.View with PermittedView?
    # Don't need to descend permissions to Modal
    # Maybe combine with timeout manager

    def __init__(self, setting: ST, auto_write=True, **kwargs):
        self.setting = setting
        self.update_children()
        super().__init__(**kwargs)
        self.auto_write = auto_write

        self._interaction: Optional[discord.Interaction] = None
        self._modal: Optional[SettingModal] = None
        self._exports: List[ui.Item] = self.make_exports()

        self._context = copy_context()

    def update_children(self):
        """
        Method called before base View initialisation.
        Allows updating the children components (usually explicitly defined callbacks),
        before Item instantiation.
        """
        pass

    def order_children(self, *children):
        """
        Helper method to set and order the children using bound methods.
        """
        child_map = {child.__name__: child for child in self.__view_children_items__}
        self.__view_children_items__ = [child_map[child.__name__] for child in children]

    def update_child(self, child, new_args):
        args = getattr(child, '__discord_ui_model_kwargs__')
        args |= new_args

    def make_exports(self):
        """
        Called post-instantiation to populate self._exports.
        """
        return self.children

    def refresh(self):
        """
        Update widget components from current setting data, if applicable.
        E.g. to update the default entry in a select list after a choice has been made,
        or update button colours.
        This does not trigger a discord ui update,
        that is the responsibility of the interaction handler.
        """
        pass

    async def show(self, interaction: discord.Interaction, key: Any = None, override=False, **kwargs):
        """
        Complete standard setting widget UI flow for this setting.
        The SettingWidget components may be attached to other messages as needed,
        and they may be triggered individually,
        but this coroutine defines the standard interface.
        Intended for use by any interaction which wants to "open the setting".

        Extra keyword arguments are passed directly to the interaction reply (for e.g. ephemeral).
        """
        if key is None:
            # By default, only have one widget listener per interaction.
            key = ('widget', interaction.id)

        # If there is already a widget listening on this key, respect override
        if self.setting.get_listener(key) and not override:
            # Refuse to spawn another widget
            return

        async def update_callback(new_data):
            self.setting.data = new_data
            await interaction.edit_original_response(embed=self.setting.embed, view=self, **kwargs)

        self.setting.register_callback(key)(update_callback)
        await interaction.response.send_message(embed=self.setting.embed, view=self, **kwargs)
        await self.wait()
        try:
            # Try and detach the view, since we aren't handling events anymore.
            await interaction.edit_original_response(view=None)
        except discord.HTTPException:
            pass
        self.setting.deregister_callback(key)

    def attach(self, group_view: ui.View):
        """
        Attach this setting widget to a view representing several settings.
        """
        for item in self._exports:
            group_view.add_item(item)

    @button(style=ButtonStyle.secondary, label="Edit", row=4)
    async def edit_button(self, interaction: discord.Interaction, button: ui.Button):
        """
        Spawn a simple edit modal,
        populated with `setting.input_field`.
        """
        recover_context(self._context)
        # Spawn the setting modal
        await interaction.response.send_modal(self.modal)

    @button(style=ButtonStyle.danger, label="Reset", row=4)
    async def reset_button(self, interaction: discord.Interaction, button: Button):
        recover_context(self._context)
        await interaction.response.defer(thinking=True, ephemeral=True)
        await self.setting.interactive_set(None, interaction)

    @property
    def modal(self) -> Modal:
        """
        Build a Modal dialogue for updating the setting.
        Refreshes (and re-attaches) the input field each time this is called.
        """
        if self._modal is not None:
            self._modal.update_field(self.setting.input_field)
            return self._modal

        # TODO: Attach shared timeouts to the modal
        self._modal = modal = SettingModal(
            title=f"Edit {self.setting.display_name}",
        )
        modal.update_field(self.setting.input_field)

        @modal.submit_callback()
        async def edit_submit(interaction: discord.Interaction):
            # TODO: Catch and handle UserInputError
            await interaction.response.defer(thinking=True, ephemeral=True)
            data = await self.setting._parse_string(self.setting.parent_id, modal.input_field.value)
            await self.setting.interactive_set(data, interaction)

        return modal


class InteractiveSetting(BaseSetting[ParentID, SettingData, SettingValue]):
    __slots__ = ('_widget',)

    # Configuration interface descriptions
    _display_name: LazyStr  # User readable name of the setting
    _desc: LazyStr  # User readable brief description of the setting
    _long_desc: LazyStr  # User readable long description of the setting
    _accepts: LazyStr  # User readable description of the acceptable values
    _set_cmd: str = None
    _notset_str: LazyStr = _p('setting|formatted|notset', "Not Set")
    _virtual: bool = False  # Whether the setting should be hidden from tables and dashboards
    _required: bool = False

    Widget = SettingWidget

    # A list of callback coroutines to call when the setting updates
    # This can be used globally to refresh state when the setting updates,
    # Or locallly to e.g. refresh an active widget.
    # The callbacks are called on write, so they may be bypassed by direct use of _writer!
    _listeners_: Dict[Any, Callable[[Optional[SettingData]], Coroutine[Any, Any, None]]] = {}

    # Optional client event to dispatch when theis setting has been written
    # Event handlers should be of the form Callable[ParentID, SettingData]
    _event: Optional[str] = None

    # Interaction ward that should be validated via interaction_check
    _write_ward: Optional[Callable[[discord.Interaction], Coroutine[Any, Any, bool]]] = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._widget: Optional[SettingWidget] = None

    @property
    def long_desc(self):
        t = ctx_translator.get().t
        bot = ctx_bot.get()
        return t(self._long_desc).format(
            bot=bot,
            cmds=bot.core.mention_cache
        )

    @property
    def display_name(self):
        t = ctx_translator.get().t
        return t(self._display_name)

    @property
    def desc(self):
        t = ctx_translator.get().t
        return t(self._desc)

    @property
    def accepts(self):
        t = ctx_translator.get().t
        return t(self._accepts)

    async def write(self, **kwargs) -> None:
        await super().write(**kwargs)
        self.dispatch_update()
        for listener in self._listeners_.values():
            asyncio.create_task(listener(self.data))

    def dispatch_update(self):
        """
        Dispatch a client event along `self._event`, if set.

        Override to modify the target event handler arguments.
        By default, event handlers should be of the form:
            Callable[[ParentID, SettingData], Coroutine[Any, Any, None]]
        """
        if self._event is not None and (bot := ctx_bot.get()) is not None:
            bot.dispatch(self._event, self.parent_id, self)

    def get_listener(self, key):
        return self._listeners_.get(key, None)

    @classmethod
    def register_callback(cls, name=None):
        def wrapped(coro):
            cls._listeners_[name or coro.__name__] = coro
            return coro
        return wrapped

    @classmethod
    def deregister_callback(cls, name):
        cls._listeners_.pop(name, None)

    @property
    def update_message(self):
        """
        Response message sent when the setting has successfully been updated.
        Should generally be one line.
        """
        if self.data is None:
            return "Setting reset!"
        else:
            return f"Setting Updated! New value: {self.formatted}"

    @property
    def hover_desc(self):
        """
        This no longer works since Discord changed the hover rules.

        return '\n'.join((
            self.display_name,
            '=' * len(self.display_name),
            self.desc,
            f"\nAccepts: {self.accepts}"
        ))
        """
        return self.desc

    async def update_response(self, interaction: discord.Interaction, message: Optional[str] = None, **kwargs):
        """
        Respond to an interaction which triggered a setting update.
        Usually just wraps `update_message` in an embed and sends it back.
        Passes any extra `kwargs` to the message creation method.
        """
        embed = discord.Embed(
            description=f"{str(conf.emojis.tick)} {message or self.update_message}",
            colour=discord.Color.green()
        )
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, **kwargs)
        else:
            await interaction.response.send_message(embed=embed, **kwargs)

    async def interactive_set(self, new_data: Optional[SettingData], interaction: discord.Interaction, **kwargs):
        self.data = new_data
        await self.write()
        await self.update_response(interaction, **kwargs)

    async def format_in(self, bot, **kwargs):
        """
        Formatted version of the setting given an asynchronous context with client.
        """
        return self.formatted

    @property
    def embed_field(self):
        """
        Returns a {name, value} pair for use in an Embed field.
        """
        name = self.display_name
        value = f"{self.long_desc}\n{self.desc_table}"
        if len(value) > 1024:
            t = ctx_translator.get().t
            desc_table = '\n'.join(
                tabulate(
                    *self._desc_table(
                        show_value=t(_p(
                            'setting|embed_field|too_long',
                            "Too long to display here!"
                        ))
                    )
                )
            )
            value = f"{self.long_desc}\n{desc_table}"
        if len(value) > 1024:
            # Forcibly trim
            value = value[:1020] + '...'
        return {'name': name, 'value': value}

    @property
    def set_str(self):
        if self._set_cmd is not None:
            bot = ctx_bot.get()
            if bot:
                return bot.core.mention_cmd(self._set_cmd)
            else:
                return f"`/{self._set_cmd}`"

    @property
    def notset_str(self):
        t = ctx_translator.get().t
        return t(self._notset_str)

    @property
    def embed(self):
        """
        Returns a full embed describing this setting.
        """
        t = ctx_translator.get().t
        embed = discord.Embed(
            title=t(_p(
                'setting|summary_embed|title',
                "Configuration options for `{name}`"
            )).format(name=self.display_name),
        )
        embed.description = "{}\n{}".format(self.long_desc.format(self=self), self.desc_table)
        return embed

    def _desc_table(self, show_value: Optional[str] = None) -> list[tuple[str, str]]:
        t = ctx_translator.get().t
        lines = []

        # Currently line
        lines.append((
            t(_p('setting|summary_table|field:currently|key', "Currently")),
            show_value or (self.formatted or self.notset_str)
        ))

        # Default line
        if (default := self.default) is not None:
            lines.append((
                t(_p('setting|summary_table|field:default|key', "By Default")),
                self._format_data(self.parent_id, default) or 'None'
            ))

        # Set using line
        if (set_str := self.set_str) is not None:
            lines.append((
                t(_p('setting|summary_table|field:set|key', "Set Using")),
                set_str
            ))
        return lines

    @property
    def desc_table(self) -> str:
        return '\n'.join(tabulate(*self._desc_table()))

    @property
    def input_field(self) -> TextInput:
        """
        TextInput field used for string-based setting modification.
        May be added to external modal for grouped setting editing.
        This property is not persistent, and creates a new field each time.
        """
        return TextInput(
            label=self.display_name,
            placeholder=self.accepts,
            default=self.input_formatted[:4000] if self.input_formatted else None,
            required=self._required
        )

    @property
    def widget(self):
        """
        Returns the Discord UI View associated with the current setting.
        """
        if self._widget is None:
            self._widget = self.Widget(self)
        return self._widget

    @classmethod
    def set_widget(cls, WidgetCls):
        """
        Convenience decorator to create the widget class for this setting.
        """
        cls.Widget = WidgetCls
        return WidgetCls

    @property
    def formatted(self):
        """
        Default user-readable form of the setting.
        Should be a short single line.
        """
        return self._format_data(self.parent_id, self.data, **self.kwargs) or self.notset_str

    @property
    def input_formatted(self) -> str:
        """
        Format the current value as a default value for an input field.
        Returned string must be acceptable through parse_string.
        Does not take into account defaults.
        """
        if self._data is not None:
            return str(self._data)
        else:
            return ""

    @property
    def summary(self):
        """
        Formatted summary of the data.
        May be implemented in `_format_data(..., summary=True, ...)` or overidden.
        """
        return self._format_data(self.parent_id, self.data, summary=True, **self.kwargs)

    @classmethod
    async def from_string(cls, parent_id, userstr: str, **kwargs):
        """
        Return a setting instance initialised from a parsed user string.
        """
        data = await cls._parse_string(parent_id, userstr, **kwargs)
        return cls(parent_id, data, **kwargs)

    @classmethod
    async def from_value(cls, parent_id, value, **kwargs):
        await cls._check_value(parent_id, value, **kwargs)
        data = cls._data_from_value(parent_id, value, **kwargs)
        return cls(parent_id, data, **kwargs)

    @classmethod
    async def _parse_string(cls, parent_id, string: str, **kwargs) -> Optional[SettingData]:
        """
        Parse user provided string (usually from a TextInput) into raw setting data.
        Must be overriden by the setting if the setting is user-configurable.
        Returns None if the setting was unset.
        """
        raise NotImplementedError

    @classmethod
    def _format_data(cls, parent_id, data, **kwargs):
        """
        Convert raw setting data into a formatted user-readable string,
        representing the current value.
        """
        raise NotImplementedError

    @classmethod
    async def _check_value(cls, parent_id, value, **kwargs):
        """
        Check the provided value is valid.

        Many setting update methods now provide Discord objects instead of raw data or user strings.
        This method may be used for value-checking such a value.

        Raises UserInputError if the value fails validation.
        """
        pass

    @classmethod
    async def interaction_check(cls, parent_id, interaction: discord.Interaction, **kwargs):
        if cls._write_ward is not None and not await cls._write_ward(interaction):
            # TODO: Combine the check system so we can do customised errors here
            t = ctx_translator.get().t
            raise UserInputError(t(_p(
                'setting|interaction_check|error',
                "You do not have sufficient permissions to do this!"
            )))


"""
command callback for set command?
autocomplete for set command?

Might be better in a ConfigSetting subclass.
But also mix into the base setting types.
"""

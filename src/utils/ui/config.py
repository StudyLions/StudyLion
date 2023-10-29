from typing import Optional
import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle

from meta import conf, LionBot
from meta.errors import UserInputError
from utils.lib import error_embed
from wards import low_management_iward
from babel.translator import ctx_translator, LazyStr

from ..lib import tabulate
from . import LeoUI, util_babel, error_handler_for, FastModal, ModalRetryUI


_p = util_babel._p


class ConfigEditor(FastModal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction, error):
        await ModalRetryUI(self, error.msg).respond_to(interaction)


class ConfigUI(LeoUI):
    # TODO: Migrate to a subclass of MessageUI
    # TODO: Move instances to a {setting_id: instance} map for easy retrieval
    _listening = {}
    setting_classes = []

    edit_modal_title = _p('ui:configui|modal:edit|title', "Setting Editor")

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        super().__init__(**kwargs)
        self.bot = bot
        self.guildid = guildid
        self.channelid = channelid

        # Original interaction, if this UI is sent as an interaction response
        self._original: Optional[discord.Interaction] = None

        # Message containing the UI, when the UI is sent as a followup
        self._message: Optional[discord.Message] = None

        # Refresh lock, to avoid cache collisions
        self._refresh_lock = asyncio.Lock()

        # Instances of the settings this UI is managing
        self.instances = ()

    @property
    def page_instances(self):
        return self.instances

    def get_instance(self, setting_cls):
        setting_id = setting_cls.setting_id
        return next(instance for instance in self.instances if instance.setting_id == setting_id)

    async def interaction_check(self, interaction: discord.Interaction):
        """
        Default requirement for a Config UI is low management (i.e. manage_guild permissions).
        """
        passed = await low_management_iward(interaction)
        if passed:
            return True
        else:
            await interaction.response.send_message(
                embed=error_embed(
                    self.bot.translator.t(_p(
                        'ui:configui|check|not_permitted',
                        "You have insufficient server permissions to use this UI!"
                    ))
                ),
                ephemeral=True
            )
            return False

    async def cleanup(self):
        self._listening.pop(self.channelid, None)
        for instance in self.instances:
            instance.deregister_callback(self.id)
        try:
            if self._original is not None and not self._original.is_expired():
                await self._original.edit_original_response(view=None)
                self._original = None
            if self._message is not None:
                await self._message.edit(view=None)
                self._message = None
        except discord.HTTPException:
            pass

    @button(label="EDIT_PLACEHOLDER", style=ButtonStyle.blurple)
    async def edit_button(self, press: discord.Interaction, pressed: Button):
        """
        Bulk edit the current setting instances.

        There must be no more than 5 instances for this to work!
        They are all assumed to support `input_formatted` and `parse_string`.
        Errors should raise instances of `UserInputError`, and will be caught for retry.
        """
        t = ctx_translator.get().t
        instances = self.page_instances
        items = [setting.input_field for setting in instances]
        # Filter out settings which don't have input fields
        items = [item for item in items if item][:5]
        strings = [item.value for item in items]
        if not items:
            raise ValueError("Cannot make Config edit modal with no editable instances.")

        modal = ConfigEditor(*items, title=t(self.edit_modal_title))

        @modal.submit_callback()
        async def save_settings(interaction: discord.Interaction):
            # NOTE: Cannot respond with a defer because we need ephemeral error
            modified = []
            for setting, field, original in zip(instances, items, strings):
                if field.value != original:
                    # Setting was modified, attempt to parse
                    input_value = field.value.strip()
                    if not input_value:
                        # None input, reset the setting
                        new_data = None
                    else:
                        # If this raises a UserInputError, it will be caught and the modal retried
                        await setting.interaction_check(setting.parent_id, interaction)
                        new_data = await setting._parse_string(setting.parent_id, input_value)
                    setting.data = new_data
                    modified.append(setting)
            if modified:
                await interaction.response.defer(thinking=True)
                # Write the settings to disk
                for setting in modified:
                    # TODO: Again, need a way of batching these
                    # Also probably put them in a transaction
                    await setting.write()
                # TODO: Send modified ack
                desc = '\n'.join(f"{conf.emojis.tick} {setting.update_message}" for setting in modified)
                await interaction.edit_original_response(
                    embed=discord.Embed(
                        colour=discord.Colour.brand_green(),
                        description=desc
                    )
                )
            else:
                await interaction.response.defer(thinking=False)

        await press.response.send_modal(modal)

    async def edit_button_refresh(self):
        t = ctx_translator.get().t
        self.edit_button.label = t(_p(
            'ui:configui|button:edit|label',
            "Edit"
        ))

    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def close_button(self, press: discord.Interaction, pressed: Button):
        """
        Close the UI, if possible.
        """
        await press.response.defer()
        try:
            if self._original is not None and not self._original.is_expired():
                await self._original.delete_original_response()
                self._original = None
            elif self._message is not None:
                await self._message.delete()
                self._message = None
        except discord.HTTPException:
            self._original = None
            self._message = None

        await self.close()

    async def close_button_refresh(self):
        pass

    @button(label="RESET_PLACEHOLDER", style=ButtonStyle.red)
    async def reset_button(self, press: discord.Interaction, pressed: Button):
        """
        Reset the controlled settings.
        """
        await press.response.defer()

        for instance in self.page_instances:
            instance.data = None
            await instance.write()

    async def reset_button_refresh(self):
        t = self.bot.translator.t
        self.reset_button.label = t(_p(
            'ui:guild_config_base|button:reset|label', "Reset"
        ))

    async def refresh_components(self):
        """
        Refresh UI layout and individual components.
        """
        raise NotImplementedError

    async def reload(self):
        """
        Reload UI data, including instantiating settings.

        Default implementation directly re-instantiates each setting in self.setting_classes.
        Should be overridden for conditional settings or more advanced caching methods.
        """
        self.instances = tuple([
            await cls.get(self.guildid) for cls in self.setting_classes
        ])

    async def make_message(self):
        """
        UI message arguments, to be calculated after reload.
        """
        raise NotImplementedError

    async def redraw(self, thinking: Optional[discord.Interaction] = None):
        """
        Redraw the UI.

        If a thinking interaction is provided,
        deletes the response while redrawing.
        """
        args = await self.make_message()
        if thinking is not None and not thinking.is_expired() and thinking.response.is_done():
            asyncio.create_task(thinking.delete_original_response())
        try:
            if self._original and not self._original.is_expired():
                await self._original.edit_original_response(**args.edit_args, view=self)
            elif self._message:
                await self._message.edit(**args.edit_args, view=self)
            else:
                # Interaction expired or we already closed. Exit quietly.
                await self.close()
        except discord.HTTPException:
            # Some unknown communication error, nothing we can safely do. Exit quietly.
            await self.close()

    async def refresh(self, *args, thinking: Optional[discord.Interaction] = None):
        """
        Refresh the UI.
        """
        async with self._refresh_lock:
            # Refresh data
            await self.reload()
            # Refresh UI components and layout
            await self.refresh_components()
            # Redraw UI message
            await self.redraw(thinking=thinking)

    async def run(self, interaction: discord.Interaction):
        if old := self._listening.get(self.channelid, None):
            await old.close()

        await self.reload()
        await self.refresh_components()
        args = await self.make_message()

        if interaction.response.is_done():
            # Start UI using followup message
            self._message = await interaction.followup.send(**args.send_args, view=self)
        else:
            # Start UI using interaction response
            self._original = interaction
            await interaction.response.send_message(**args.send_args, view=self)

        for instance in self.instances:
            # Attach refresh callback to each instance
            instance.register_callback(self.id)(self.refresh)

        # Register this UI as listening for updates in this channel
        self._listening[self.channelid] = self


class DashboardSection:
    """
    Represents a section of a configuration Dashboard.
    """
    section_name: LazyStr = None
    setting_classes = []
    configui = None

    _option_name = None

    def __init__(self, bot: LionBot, guildid: int):
        self.bot = bot
        self.guildid = guildid

        # List of instances of the contained setting classes
        # Populated in load()
        self.instances = []

    @property
    def option_name(self) -> str:
        t = self.bot.translator.t
        string = self._option_name or self.section_name
        return t(string).format(
            bot=self.bot,
            commands=self.bot.core.mention_cache
        )

    async def load(self):
        """
        Initialise the contained settings.
        """
        instances = []
        for cls in self.setting_classes:
            instance = await cls.get(self.guildid)
            instances.append(instance)
        self.instances = instances
        return self

    def apply_to(self, page: discord.Embed):
        """
        Apply this section to the given dashboard page.

        Usually just defines and adds an embed field with the setting table.
        """
        t = ctx_translator.get().t

        # TODO: Header/description field
        table = self.make_table()
        if len(table) > 1024:
            value = t(_p(
                'ui:dashboard|error:section_too_long',
                "Oops, the settings in this configuration section are too large, "
                "and I can not display them here! "
                "Please view the settings in the linked configuration panel instead."
            ))
        else:
            value = table
        page.add_field(
            name=t(self.section_name).format(bot=self.bot, commands=self.bot.core.mention_cache),
            value=value,
            inline=False
        )

    def make_table(self):
        return self._make_table(self.instances)

    def _make_table(self, instances):
        rows = []
        for setting in instances:
            name = setting.display_name
            value = setting.formatted
            rows.append((name, value, setting.desc))
        table_rows = tabulate(
            *rows,
            row_format="[`{invis}{key:<{pad}}{colon}`](https://lionbot.org \"{field[2]}\")\t{value}"
        )
        return '\n'.join(table_rows)

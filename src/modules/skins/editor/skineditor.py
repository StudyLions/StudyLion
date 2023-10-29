from io import StringIO
import json
from typing import Optional
import asyncio
import datetime as dt

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, Select, SelectOption
from gui.base.AppSkin import AppSkin

from meta import LionBot, conf
from meta.errors import ResponseTimedOut, UserInputError
from meta.logger import log_wrap
from utils.ui import FastModal, Confirm, MessageUI, error_handler_for, ModalRetryUI, AButton, AsComponents
from utils.lib import MessageArgs, utc_now
from constants import DATA_VERSION

from .. import babel, logger
from ..skinlib import CustomSkin, FrozenCustomSkin, appskin_as_option
from .pages import pages
from .skinsetting import Setting, SettingInputType, SkinSetting
from .layout import SettingGroup, Page


_p = babel._p


class SettingInput(FastModal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction, error):
        await ModalRetryUI(self, error.msg).respond_to(interaction)


class CustomSkinEditor(MessageUI):
    def _init_children(self):
        # HACK to stop ViewWeights complaining that this UI has too many children
        # Children will be correctly initialised after parent init.
        return []

    def __init__(self, skin: CustomSkin, **kwargs):
        super().__init__(timeout=600, **kwargs)
        self._children = super()._init_children()

        self.skin = skin
        self.bot = skin.bot
        self.cog = self.bot.get_cog('CustomSkinCog')

        self.global_themes = self._get_available()

        # UI State

        # Whether we are currently in customisation mode
        self.customising = False
        self.page_index = 0
        self.showing_skin_setting: Optional[SkinSetting] = None

        # Last item in history is current state
        # Last item in future is next state
        self.history = [skin.freeze()]
        self.future = []
        self.dirty = False

    @property
    def page(self) -> Page:
        return pages[self.page_index]

    # ----- UI API -----
    def push_state(self):
        """
        Push a state onto the history stack.
        Run this on each change _before_ the refresh.
        """
        state = self.skin.freeze()
        self.history.append(state)
        self.future.clear()
        self.dirty = True

    def _get_available(self) -> dict[str, AppSkin]:
        skins = {
            skin.skin_id: skin for skin in AppSkin.get_all()
            if skin.public
        }
        skins['default'] = self._make_default()
        return skins

    def _make_default(self) -> AppSkin:
        """
        Create a placeholder 'default' skin.
        """
        t = self.bot.translator.t

        skin = AppSkin(None)
        skin.skin_id = 'default'
        skin.display_name = t(_p(
            'ui:skineditor|default_skin:display_name',
            "Default"
        ))
        skin.description = t(_p(
            'ui:skineditor|default_skin:description',
            "My default interface theme"
        ))
        skin.price = 0
        return skin

    # ----- UI Components -----

    # Download button
    # NOTE: property_id, card_id, property_name, value
    # Metadata with version, time generated, skinid, generating user
    # Special field for the global_skin_id
    @button(
        label="DOWNLOAD_BUTTON_PLACEHOLDER",
        style=ButtonStyle.blurple
    )
    async def download_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        
        data = {}
        data['metadata'] = {
            'requested_by': press.user.id,
            'requested_in': press.guild.id if press.guild else None,
            'skinid': self.skin.skinid,
            'created_at': utc_now().isoformat(),
            'data_version': DATA_VERSION,
        }
        data['custom_skin'] = {
            'skinid': self.skin.skinid,
            'base_skin': self.skin.base_skin_name,
        }
        properties = {}
        for card, card_props in self.skin.properties.items():
            props = {}
            for name, value in card_props.items():
                propid = (await self.cog.fetch_property_ids((card, name)))[0]
                props[name] = {
                    'property_id': propid,
                    'value': value
                }
            properties[card] = props
        data['custom_skin']['properties'] = properties

        content = json.dumps(data, indent=2)
        with StringIO(content) as fp:
            fp.seek(0)
            file = discord.File(fp, filename=f"skin-{self.skin.skinid}.json")
            await press.followup.send("Here is your custom skin data!", file=file, ephemeral=True)
    
    async def download_button_refresh(self):
        button = self.download_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:skineditor|button:download|label',
            "Download"
        ))

    # Save button
    @button(
        label="SAVE_BUTTON_PLACEHOLDER",
        style=ButtonStyle.green
    )
    async def save_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        await self.skin.save()
        self.history = self.history[-1:]
        self.dirty = False
        await self.refresh(thinking=press)
    
    async def save_button_refresh(self):
        button = self.save_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:skineditor|button:save|label',
            "Save"
        ))
        button.disabled = not self.dirty

    # Back button
    @button(
        label="BACK_BUTTON_PLACEHOLDER",
        style=ButtonStyle.red
    )
    async def back_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.customising = False
        await self.refresh(thinking=press)
    
    async def back_button_refresh(self):
        button = self.back_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:skineditor|button:back|label',
            "Back"
        ))

    # Customise button
    @button(
        label="CUSTOMISE_BUTTON_PLACEHOLDER",
        style=ButtonStyle.green
    )
    async def customise_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.customising = True
        await self.refresh(thinking=press)
    
    async def customise_button_refresh(self):
        button = self.customise_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:skineditor|button:customise|label',
            "Customise"
        ))

    # Reset card button
    @button(
        label="RESET_CARD_BUTTON_PLACEHOLDER",
        style=ButtonStyle.red
    )
    async def reset_card_button(self, press: discord.Interaction, pressed: Button):
        # Note this actually resets the page, not the card
        await press.response.defer(thinking=True, ephemeral=True)
        
        for group in self.page.groups:
            for setting in group.settings:
                setting.set_in(self.skin, None)

        self.push_state()
        await self.refresh(thinking=press)
    
    async def reset_card_button_refresh(self):
        button = self.reset_card_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:skineditor|button:reset_card|label',
            "Reset Card"
        ))

    # Reset all button
    @button(
        label="RESET_ALL_BUTTON_PLACEHOLDER",
        style=ButtonStyle.red
    )
    async def reset_all_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)

        self.skin.properties.clear()
        self.skin.base_skin_name = None

        self.push_state()
        await self.refresh(thinking=press)
    
    async def reset_all_button_refresh(self):
        button = self.reset_all_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:skineditor|button:reset_all|label',
            "Reset All"
        ))

    # Page selector
    @select(
        cls=Select,
        placeholder="PAGE_MENU_PLACEHOLDER",
        min_values=1, max_values=1
    )
    async def page_menu(self, selection: discord.Interaction, selected: Select):
        await selection.response.defer(thinking=True, ephemeral=True)
        self.page_index = int(selected.values[0])
        self.showing_skin_setting = None
        await self.refresh(thinking=selection)
    
    async def page_menu_refresh(self):
        menu = self.page_menu
        t = self.bot.translator.t

        options = []
        if not self.customising:
            menu.placeholder = t(_p(
                'ui:skineditor|menu:page|placeholder:preview',
                "Select a card to preview"
            ))
            for i, page in enumerate(pages):
                if page.visible_in_preview:
                    option = SelectOption(
                        label=t(page.display_name),
                        value=str(i),
                        description=t(page.preview_description) if page.preview_description else None
                    )
                    option.default = (i == self.page_index)
                    options.append(option)
        else:
            menu.placeholder = t(_p(
                'ui:skineditor|menu:page|placeholder:edit',
                "Select a card to customise"
            ))
            for i, page in enumerate(pages):
                option = SelectOption(
                    label=t(page.display_name),
                    value=str(i),
                    description=t(page.editing_description) if page.editing_description else None
                )
                option.default = (i == self.page_index)
                options.append(option)
        menu.options = options

    # Setting group selector
    @select(
        cls=Select,
        placeholder="GROUP_MENU_PLACEHOLDER",
        min_values=1, max_values=1
    )
    async def group_menu(self, selection: discord.Interaction, selected: Select):
        groupid = selected.values[0]
        group = next(group for group in self.page.groups if group.custom_id == groupid)

        if group.settings[0].input_type is SettingInputType.SkinInput:
            self.showing_skin_setting = group.settings[0]
            await selection.response.defer(thinking=True, ephemeral=True)
            await self.refresh(thinking=selection)
        else:
            await self._launch_group_editor(selection, group)

    async def _launch_group_editor(self, interaction: discord.Interaction, group: SettingGroup):
        t = self.bot.translator.t

        editable = group.editable_settings
        items = [
            setting.make_input_field(self.skin)
            for setting in editable
        ]
        modal = SettingInput(*items, title=t(group.name))

        @modal.submit_callback()
        async def group_modal_callback(interaction: discord.Interaction):
            values = []
            for item, setting in zip(items, editable):
                value = await setting.parse_input(self.skin, item.value)
                values.append(value)

            await interaction.response.defer(thinking=True, ephemeral=True)
            for value, setting in zip(values, editable):
                setting.set_in(self.skin, value)

            self.push_state()
            await self.refresh(thinking=interaction)

        await interaction.response.send_modal(modal)
    
    async def group_menu_refresh(self):
        menu = self.group_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:skineditor|menu:group|placeholder',
            "Select a group or option to customise"
        ))
        options = []
        for group in self.page.groups:
            option = group.select_option_for(self.skin)
            options.append(option)
        menu.options = options

    # Base skin selector
    @select(
        cls=Select,
        placeholder="SKIN_MENU_PLACEHOLDER",
        min_values=1, max_values=1
    )
    async def skin_menu(self, selection: discord.Interaction, selected: Select):
        await selection.response.defer(thinking=True, ephemeral=True)

        skin_id = selected.values[0]
        if skin_id == 'default':
            skin_id = None

        if self.customising:
            if self.showing_skin_setting:
                # Update the current page card with this skin id.
                self.showing_skin_setting.set_in(self.skin, skin_id)
        else:
            # Far more brutal
            # Update the global base skin id, and wipe the base skin id for each card
            self.skin.base_skin_name = skin_id
            for card_id in self.skin.properties:
                self.skin.set_prop(card_id, 'base_skin_id', None)

        self.push_state()
        await self.refresh(thinking=selection)
    
    async def skin_menu_refresh(self):
        menu = self.skin_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:skineditor|menu:skin|placeholder',
            "Select a theme"
        ))
        options = []
        for skin in self.global_themes.values():
            option = appskin_as_option(skin)
            options.append(option)
        menu.options = options

    # Quit button, with confirmation
    @button(style=ButtonStyle.grey, emoji=conf.emojis.cancel)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        # Confirm quit if there are unsaved changes
        if self.dirty:
            t = self.bot.translator.t
            confirm_msg = t(_p(
                'ui:skineditor|button:quit|confirm',
                "You have unsaved changes! Are you sure you want to quit?"
            ))
            confirm = Confirm(confirm_msg, self._callerid)
            confirm.confirm_button.label = t(_p(
                'ui:skineditor|button:quit|confirm|button:yes',
                "Yes, Quit Now"
            ))
            confirm.confirm_button.style = ButtonStyle.red
            confirm.cancel_button.style = ButtonStyle.green
            confirm.cancel_button.label = t(_p(
                'ui:skineditor|button:quit|confirm|button:no',
                "No, Go Back"
            ))
            try:
                result = await confirm.ask(press, ephemeral=True)
            except ResponseTimedOut:
                result = False

            if result:
                await self.quit()
        else:
            await self.quit()

    @button(label="UNDO_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def undo_button(self, press: discord.Interaction, pressed: Button):
        """
        Pop the history stack.
        """
        if len(self.history) > 1:
            state = self.history.pop()
            self.future.append(state)

            current = self.history[-1]
            self.skin.load_frozen(current)

        await press.response.defer(thinking=True, ephemeral=True)
        await self.refresh(thinking=press)

    async def undo_button_refresh(self):
        t = self.bot.translator.t
        button = self.undo_button
        button.label = t(_p(
            'ui:skineditor|button:undo|label',
            "Undo"
        ))
        button.disabled = (len(self.history) <= 1)

    @button(label="REDO_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def redo_button(self, press: discord.Interaction, pressed: Button):
        """
        Pop the future stack.
        """
        if len(self.future) > 0:
            state = self.future.pop()
            self.history.append(state)

            current = self.history[-1]
            self.skin.load_frozen(current)

        await press.response.defer(thinking=True, ephemeral=True)
        await self.refresh(thinking=press)

    async def redo_button_refresh(self):
        t = self.bot.translator.t
        button = self.redo_button
        button.label = t(_p(
            'ui:skineditor|button:redo|label',
            "Redo"
        ))
        button.disabled = (len(self.future) == 0)

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        page = self.page

        embed = page.make_embed_for(self.skin)
        if page.render_card is not None:
            args = self.skin.args_for(page.render_card.card_id)
            args.setdefault('base_skin_id', self.cog.current_default)
            file = await page.render_card.generate_sample(skin=args)
            files = [file]
        else:
            files = []

        return MessageArgs(embed=embed, files=files)

    async def refresh_layout(self):
        """
        Customising mode:
            (card_menu)
            (skin_menu?)
            (download, save, undo, redo, back,)
        Other:
            (card_menu)
            (theme_menu)
            (customise, save, reset_card, reset_all, X)
        """
        to_refresh = (
            self.page_menu_refresh(),
            self.skin_menu_refresh(),
            self.undo_button_refresh(),
            self.redo_button_refresh(),
            self.reset_card_button_refresh(),
            self.reset_all_button_refresh(),
            self.customise_button_refresh(),
            self.back_button_refresh(),
            self.save_button_refresh(),
            self.group_menu_refresh(),
            self.download_button_refresh(),
        )
        await asyncio.gather(*to_refresh)

        if self.customising:
            self.set_layout(
                (self.page_menu,),
                (self.group_menu,),
                (self.skin_menu,) if self.showing_skin_setting else (),
                (
                    self.save_button,
                    self.undo_button,
                    self.redo_button,
                    self.download_button,
                    self.back_button,
                ),
            )
        else:
            self.set_layout(
                (self.page_menu,),
                (self.skin_menu,),
                (
                    self.customise_button,
                    self.save_button,
                    self.reset_card_button,
                    self.reset_all_button,
                    self.quit_button,
                ),
            )

    async def reload(self):
        ...

    async def pre_timeout(self):
        # Timeout confirmation
        if self.dirty:
            t = self.bot.translator.t
            grace_period = 60
            grace_time = utc_now() + dt.timedelta(seconds=grace_period)
            embed = discord.Embed(
                title=t(_p(
                    'ui:skineditor|timeout_warning|title',
                    "Warning!"
                )),
                description=t(_p(
                    'ui:skineditor|timeout_warning|desc',
                    "This interface will time out {timestamp}. Press 'Continue' below to keep editing."
                )).format(
                    timestamp=discord.utils.format_dt(grace_time, style='R')
                ),
            )

            components = None
            stopped = False

            @AButton(label=t(_p('ui:skineditor|timeout_warning|continue', "Continue")), style=ButtonStyle.green)
            async def cont_button(interaction: discord.Interaction, pressed):
                await interaction.response.defer()
                if interaction.message:
                    await interaction.message.delete()
                nonlocal stopped
                stopped = True
                # TODO: Clean up this mess. It works, but needs to be refactored to a timeout confirmation mixin.
                # TODO: Consider moving the message to the interaction response
                self._refresh_timeout()
                components.stop()

            components = AsComponents(cont_button, timeout=grace_period)
            channel = self._original.channel if self._original else self._message.channel

            message = await channel.send(content=f"<@{self._callerid}>", embed=embed, view=components)
            await components.wait()

            if not stopped:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

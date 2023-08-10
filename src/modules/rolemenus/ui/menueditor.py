import asyncio
import json
from typing import Optional
from enum import Enum

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, Select, RoleSelect, ChannelSelect, SelectOption

from meta import LionBot, conf
from meta.errors import UserInputError, ResponseTimedOut, SafeCancellation
from utils.lib import utc_now, MessageArgs, error_embed, tabulate
from utils.ui import (
    MessageUI, ConfigEditor, FastModal, error_handler_for,
    ModalRetryUI, MsgEditor, Confirm, HookedItem, AsComponents,
)
from babel.translator import ctx_locale
from wards import equippable_role

from .. import babel
from ..data import MenuType, RoleMenuData
from ..rolemenu import RoleMenu, RoleMenuRole
from ..menuoptions import RoleMenuOptions
from ..templates import templates

_p = babel._p


class RoleEditorInput(FastModal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction, error):
        await ModalRetryUI(self, error.msg).respond_to(interaction)


class AChannelSelect(HookedItem, ChannelSelect):
    ...


class EditorMode(Enum):
    OPTIONS = 0
    ROLES = 1
    STYLE = 2


class MenuEditor(MessageUI):
    _listening = {}  # (channelid, callerid) -> active MenuEditor

    def _init_children(self):
        # HACK to stop ViewWeights complaining that this UI has too many children
        # Children will be correctly initialised after parent init.
        return []

    def __init__(self, bot: LionBot, menu: RoleMenu, **kwargs):
        super().__init__(**kwargs)
        self._children = super()._init_children()

        self.bot = bot
        self.menu = menu
        self.data: RoleMenuData = bot.get_cog('RoleMenuCog').data
        self.listen_key = None

        # UI State
        self.mode: EditorMode = EditorMode.ROLES
        self.page_count: int = 1
        self.pagen: int = 0
        self.page_block: list[RoleMenuRole] = []
        self._preview: Optional[discord.Interaction] = None

    # ----- UI API -----
    async def update_preview(self):
        """
        Update the preview message if it exists.
        """
        if self._preview is not None:
            args = await self.menu.make_args()
            view = await self.menu.make_view()
            try:
                await self._preview.edit_original_response(**args.edit_args, view=view)
            except discord.NotFound:
                self._preview = None
            except discord.HTTPException as e:
                # Due to emoji validation on creation and message edit validation,
                # This should be very rare.
                # Might happen if e.g. a custom emoji is deleted between opening the editor
                # and showing the preview.
                # Just show the error to the user and let them deal with it or rerun the editor.
                t = self.bot.translator.t
                title = t(_p(
                    'ui:menu_editor|preview|error:title',
                    "Display Error!"
                ))
                desc = t(_p(
                    'ui:menu_editor|preview|error:desc',
                    "Failed to display preview!\n"
                    "**Error:** `{exception}`"
                )).format(
                    exception=e.text
                )
                embed = discord.Embed(
                    colour=discord.Colour.brand_red(),
                    title=title,
                    description=desc
                )
                try:
                    await self._preview.edit_original_response(embed=embed)
                except discord.HTTPException:
                    # If we can't even edit the preview message now, something is probably wrong with the connection
                    # Just silently ignore
                    pass

    async def cleanup(self):
        self._listening.pop(self.listen_key, None)
        await super().cleanup()

    async def run(self, interaction: discord.Interaction, **kwargs):
        self.listen_key = (interaction.channel.id, interaction.user.id, self.menu.data.menuid)
        existing = self._listening.get(self.listen_key, None)
        if existing:
            await existing.quit()
        self._listening[self.listen_key] = self
        await super().run(interaction, **kwargs)

    async def quit(self):
        if self._preview is not None and not self._preview.is_expired():
            try:
                await self._preview.delete_original_response()
            except discord.HTTPException:
                pass
        await super().quit()

    # ----- Components -----
    # -- Options Components --
    # Menu Options Button
    @button(label="OPTIONS_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def options_button(self, press: discord.Interaction, pressed: Button):
        """
        Change mode to 'Options'.
        """
        await press.response.defer()
        self.mode = EditorMode.OPTIONS
        await self.refresh()

    async def options_button_refresh(self):
        t = self.bot.translator.t
        button = self.options_button
        button.label = t(_p(
            'ui:menu_editor|button:options|label',
            "Menu Options"
        ))
        if self.mode is EditorMode.OPTIONS:
            button.style = ButtonStyle.blurple
        else:
            button.style = ButtonStyle.grey

    # Bulk Edit Button
    @button(label="BULK_EDIT_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def bulk_edit_button(self, press: discord.Interaction, pressed: Button):
        """
        Open a Config-like modal to textually edit the Menu options.
        """
        t = self.bot.translator.t
        instances = (
            self.menu.config.name,
            self.menu.config.sticky,
            self.menu.config.refunds,
            self.menu.config.obtainable,
            self.menu.config.required_role,
        )
        fields = [instance.input_field for instance in instances]
        fields = [field for field in fields if fields]
        originals = [field.value for field in fields]
        modal = ConfigEditor(
            *fields,
            title=t(_p(
                'ui:menu_editor|button:bulk_edit|modal|title',
                "Menu Options"
            ))
        )

        @modal.submit_callback()
        async def save_options(interaction: discord.Interaction):
            modified = []
            for instance, field, original in zip(instances, fields, originals):
                if field.value != original:
                    # Option was modified, attempt to parse
                    userstr = field.value.strip()
                    if not userstr:
                        new_data = None
                    else:
                        new_data = await instance._parse_string(instance.parent_id, userstr)
                    instance.data = new_data
                    modified.append(instance)
            if modified:
                # All fields have been parsed, it is safe to respond
                await interaction.response.defer(thinking=True, ephemeral=True)
                # Write settings
                for instance in modified:
                    await instance.write()
                # Refresh the UI
                await self.refresh(thinking=interaction)
            else:
                # Nothing was modified, quietly accept
                await interaction.response.defer(thinking=False)

        await press.response.send_modal(modal)

    async def bulk_edit_button_refresh(self):
        t = self.bot.translator.t
        button = self.bulk_edit_button
        button.label = t(_p(
            'ui:menu_editor|button:bulk_edit|label',
            "Bulk Edit"
        ))

    # Toggle Sticky Button
    @button(label="STICKY_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def sticky_button(self, press: discord.Interaction, pressed: Button):
        """
        Toggle the menu.config.sticky flag.
        """
        await press.response.defer(thinking=True, ephemeral=True)
        instance = self.menu.config.sticky
        instance.value = not instance.value
        await instance.write()
        await self.refresh(thinking=press)

    async def sticky_button_refresh(self):
        t = self.bot.translator.t
        button = self.sticky_button
        button.label = t(_p(
            'ui:menu_editor|button:sticky|label',
            "Toggle Sticky"
        ))
        if self.menu.config.sticky.value:
            button.style = ButtonStyle.blurple
        else:
            button.style = ButtonStyle.grey

    # Toggle Refunds Button
    @button(label="REFUNDS_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def refunds_button(self, press: discord.Interaction, pressed: Button):
        """
        Toggle the menu.config.refunds flag.
        """
        await press.response.defer(thinking=True, ephemeral=True)
        instance = self.menu.config.refunds
        instance.value = not instance.value
        await instance.write()
        await self.refresh(thinking=press)

    async def refunds_button_refresh(self):
        t = self.bot.translator.t
        button = self.refunds_button
        button.label = t(_p(
            'ui:menu_editor|button:refunds|label',
            "Toggle Refunds"
        ))
        if self.menu.config.refunds.value:
            button.style = ButtonStyle.blurple
        else:
            button.style = ButtonStyle.grey

    # Required Roles Menu
    @select(cls=RoleSelect, placeholder="REQROLES_MENU_PLACEHOLDER", min_values=0, max_values=1)
    async def reqroles_menu(self, selection: discord.Interaction, selected: RoleSelect):
        """
        Set or reset the required role option for this menu.
        """
        await selection.response.defer(thinking=True, ephemeral=True)

        if selected.values:
            new_data = selected.values[0].id
        else:
            new_data = None

        instance = self.menu.config.required_role
        instance.data = new_data
        await instance.write()
        await self.refresh(thinking=selection)

    async def reqroles_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.reqroles_menu
        menu.placeholder = t(_p(
            'ui:menu_editor|menu:reqroles|placeholder',
            "Select Required Role"
        ))

    # -- Roles Components --
    # Modify Roles Button
    @button(label="MODIFY_ROLES_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def modify_roles_button(self, press: discord.Interaction, pressed: Button):
        """
        Change mode to 'Roles'.
        """
        await press.response.defer()
        self.mode = EditorMode.ROLES
        await self.refresh()

    async def modify_roles_button_refresh(self):
        t = self.bot.translator.t
        button = self.modify_roles_button
        button.label = t(_p(
            'ui:menu_editor|button:modify_roles|label',
            "Modify Roles"
        ))
        if self.mode is EditorMode.ROLES:
            button.style = ButtonStyle.blurple
        else:
            button.style = ButtonStyle.grey

    async def _edit_menu_role(self, interaction: discord.Interaction, menurole: RoleMenuRole):
        """
        Handle edit flow for the given RoleMenuRole.

        Opens the modal editor, and upon submit, also opens the RoleEditor.
        """
        t = self.bot.translator.t
        config = menurole.config
        instances = (
            config.label,
            config.emoji,
            config.description,
            config.price,
            config.duration,
        )
        fields = [instance.input_field for instance in instances]
        fields = [field for field in fields if fields]
        originals = [field.value for field in fields]
        modal = ConfigEditor(
            *fields,
            title=t(_p(
                'ui:menu_editor|role_editor|modal|title',
                "Edit Menu Role"
            ))
        )

        @modal.submit_callback()
        async def save_options(interaction: discord.Interaction):
            await interaction.response.defer(thinking=True, ephemeral=True)
            modified = []
            for instance, field, original in zip(instances, fields, originals):
                if field.value != original:
                    # Option was modified, attempt to parse
                    userstr = field.value.strip()
                    if not userstr:
                        new_data = None
                    else:
                        new_data = await instance._parse_string(instance.parent_id, userstr, interaction=interaction)
                    instance.data = new_data
                    modified.append(instance)
            if modified:
                # Write settings
                for instance in modified:
                    await instance.write()
                # Refresh the UI
                await self.refresh(thinking=interaction)
                await self.update_preview()
                await self.menu.update_message()
                if self.menu.data.menutype is MenuType.REACTION:
                    try:
                        await self.menu.update_reactons()
                    except SafeCancellation as e:
                        await interaction.followup.send(
                            embed=discord.Embed(
                                colour=discord.Colour.brand_red(),
                                description=e.msg
                            ),
                            ephemeral=True
                        )
            else:
                await interaction.delete_original_response()

        await interaction.response.send_modal(modal)

    # Add Roles Menu
    @select(cls=RoleSelect, placeholder="ADD_ROLES_MENU_PLACEHOLDER", min_values=0, max_values=25)
    async def add_roles_menu(self, selection: discord.Interaction, selected: RoleSelect):
        """
        Add one or multiple roles to the menu.

        Behaviour is slightly different between one or multiple roles.
        For one role, if it already exists then it is edited. If it doesn't exist
        then it is added and an editor opened for it.
        For multiple roles, they are ORed with the existing roles,
        and no prompt is given for the fields.
        """
        roles = selected.values
        if len(roles) == 0:
            await selection.response.defer(thinking=False)
        else:
            # Check equipment validity and permissions
            for role in roles:
                await equippable_role(self.bot, role, selection.user)

            single = None
            to_create = {role.id: role for role in roles}
            for mrole in self.menu.roles:
                if to_create.pop(mrole.data.roleid, None) is not None:
                    single = mrole

            if to_create:
                t = self.bot.translator.t
                # Check numbers
                if self.menu.data.menutype is MenuType.REACTION and len(self.menu.roles) + len(to_create) > 20:
                    raise UserInputError(t(_p(
                        'ui:menu_editor|menu:add_roles|error:too_many_reactions',
                        "Too many roles! Reaction role menus cannot exceed `20` roles."
                    )))
                if len(self.menu.roles) + len(to_create) > 25:
                    raise UserInputError(t(_p(
                        'ui:menu_editor|menu:add_roles|error:too_many_roles',
                        "Too many roles! Role menus cannot have more than `25` roles."
                    )))

                # Create roles
                emojis = self.menu.unused_emojis(include_defaults=(self.menu.data.menutype is MenuType.REACTION))
                rows = await self.data.RoleMenuRole.table.insert_many(
                    ('menuid', 'roleid', 'label', 'emoji'),
                    *(
                        (self.menu.data.menuid, role.id, role.name[:100], next(emojis, None))
                        for role in to_create.values()
                    )
                ).with_adapter(self.data.RoleMenuRole._make_rows)
                mroles = [RoleMenuRole(self.bot, row) for row in rows]
                single = single if single is not None else mroles[0]

            if len(roles) == 1:
                await self._edit_menu_role(selection, single)
            else:
                await selection.response.defer()

            await self.menu.reload_roles()
            if self.menu.data.name == 'Untitled':
                # Hack to name an anonymous menu
                # TODO: Formalise this
                await self.menu.data.update(name=roles[0].name)
            await self.refresh()
            await self.update_preview()
            await self.menu.update_message()
            if self.menu.data.menutype is MenuType.REACTION:
                try:
                    await self.menu.update_reactons()
                except SafeCancellation as e:
                    raise UserInputError(e.msg)

    async def add_roles_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.add_roles_menu
        menu.placeholder = t(_p(
            'ui:menu_editor|menu:add_roles|placeholder',
            "Add Roles"
        ))

    def _role_option(self, menurole: RoleMenuRole):
        return SelectOption(
            emoji=menurole.config.emoji.data or None,
            label=menurole.config.label.value,
            value=str(menurole.data.menuroleid),
            description=menurole.config.description.value,
        )

    # Edit Roles Menu
    @select(cls=Select, placeholder="EDIT_ROLES_MENU_PLACEHOLDER", min_values=1, max_values=1)
    async def edit_roles_menu(self, selection: discord.Interaction, selected: Select):
        """
        Edit a single selected role.
        """
        menuroleid = int(selected.values[0])
        menurole = next(menurole for menurole in self.menu.roles if menurole.data.menuroleid == menuroleid)
        await self._edit_menu_role(selection, menurole)

    async def edit_roles_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.edit_roles_menu
        menu.placeholder = t(_p(
            'ui:menu_editor|menu:edit_roles|placeholder',
            "Edit Roles"
        ))
        options = [self._role_option(menurole) for menurole in self.menu.roles]
        if options:
            menu.options = options
            menu.disabled = False
        else:
            menu.options = [SelectOption(label='DUMMY')]
            menu.disabled = True

    # Delete Roles Menu
    @select(cls=Select, placeholder="DEL_ROLE_MENU_PLACEHOLDER", min_values=0, max_values=25)
    async def del_role_menu(self, selection: discord.Interaction, selected: Select):
        """
        Remove one or multiple menu roles.
        """
        menuroleids = list(map(int, selected.values))
        if menuroleids:
            await selection.response.defer(thinking=True, ephemeral=True)
            await self.data.RoleMenuRole.table.delete_where(menuroleid=menuroleids)

            await self.menu.reload_roles()
            await self.refresh(thinking=selection)
            await self.update_preview()
            await self.menu.update_message()
        else:
            await selection.response.defer(thinking=False)

    async def del_role_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.del_role_menu
        menu.placeholder = t(_p(
            'ui:menu_editor|menu:del_role|placeholder',
            "Remove Roles"
        ))
        options = [self._role_option(menurole) for menurole in self.menu.roles]
        if options:
            menu.options = options
            menu.disabled = False
        else:
            menu.options = [SelectOption(label='DUMMY')]
            menu.disabled = True
        menu.max_values = len(menu.options)

    # -- Style Components --
    # Menu Style Button
    @button(label="STYLE_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def style_button(self, press: discord.Interaction, pressed: Button):
        """
        Change mode to 'Style'.
        """
        if self.menu.message and self.menu.message.author != self.menu.message.guild.me:
            t = self.bot.translator.t
            # Non-managed message, cannot change style
            raise UserInputError(
                t(_p(
                    'ui:menu_editor|button:style|error:non-managed',
                    "Cannot change the style of a menu attached to a message I did not send! Please repost first."
                ))
            )

        await press.response.defer()
        self.mode = EditorMode.STYLE
        await self.refresh()

    async def style_button_refresh(self):
        t = self.bot.translator.t
        button = self.style_button
        button.label = t(_p(
            'ui:menu_editor|button:style|label',
            "Menu Style"
        ))
        if self.mode is EditorMode.STYLE:
            button.style = ButtonStyle.blurple
        else:
            button.style = ButtonStyle.grey

    # Style Menu
    @select(cls=Select, placeholder="STYLE_MENU_PLACEHOLDER", min_values=1, max_values=1)
    async def style_menu(self, selection: discord.Interaction, selected: Select):
        """
        Select one of Reaction Roles / Dropdown / Button
        """
        t = self.bot.translator.t
        value = selected.values[0]
        menutype = MenuType[value]
        if menutype is not self.menu.data.menutype:
            # A change is requested
            if menutype is MenuType.REACTION:
                # Some checks need to be done when moving to reaction roles
                menuroles = self.menu.roles
                if len(menuroles) > 20:
                    raise UserInputError(
                        t(_p(
                            'ui:menu_editor|menu:style|error:too_many_reactions',
                            "Too many roles! The Reaction style is limited to `20` roles (Discord limitation)."
                        ))
                    )
                emojis = [mrole.config.emoji.value for mrole in menuroles]
                emojis = [emoji for emoji in emojis if emoji]
                uniq_emojis = set(emojis)
                if len(uniq_emojis) != len(menuroles):
                    raise UserInputError(
                        t(_p(
                            'ui:menu_editor|menu:style|error:incomplete_emojis',
                            "Cannot switch to the Reaction Role Style! Every role needs to have a distinct emoji first."
                        ))
                    )
            await selection.response.defer(thinking=True, ephemeral=True)
            await self.menu.data.update(menutype=menutype)
            await self.refresh(thinking=selection)
            await self.update_preview()
            await self.menu.update_message()
        else:
            await selection.response.defer()

    async def style_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.style_menu
        menu.placeholder = t(_p(
            'ui:menu_editor|menu:style|placeholder',
            "Select Menu Style"
        ))
        menu.options = [
            SelectOption(
                label=t(_p('ui:menu_editor|menu:style|option:reaction|label', "Reaction Roles")),
                description=t(_p(
                    'ui:menu_editor|menu:style|option:reaction|desc',
                    "Roles are represented compactly as clickable reactions on a message."
                )),
                value=str(MenuType.REACTION.name),
                default=(self.menu.data.menutype is MenuType.REACTION)
            ),
            SelectOption(
                label=t(_p('ui:menu_editor|menu:style|option:button|label', "Button Menu")),
                description=t(_p(
                    'ui:menu_editor|menu:style|option:button|desc',
                    "Roles are represented in 5 rows of 5 buttons, each with an emoji and label."
                )),
                value=str(MenuType.BUTTON.name),
                default=(self.menu.data.menutype is MenuType.BUTTON)
            ),
            SelectOption(
                label=t(_p('ui:menu_editor|menu:style|option:dropdown|label', "Dropdown Menu")),
                description=t(_p(
                    'ui:menu_editor|menu:style|option:dropdown|desc',
                    "Roles are selectable from a dropdown menu below the message."
                )),
                value=str(MenuType.DROPDOWN.name),
                default=(self.menu.data.menutype is MenuType.DROPDOWN)
            )
        ]

    async def _editor_callback(self, new_data):
        raws = json.dumps(new_data)
        await self.menu.data.update(rawmessage=raws)
        await self.update_preview()
        await self.menu.update_message()

    async def _message_editor(self, interaction: discord.Interaction):
        # Spawn the message editor with the current rawmessage data.
        # If the rawmessage data is empty, use the current template instead.
        editor = MsgEditor(
            self.bot, json.loads(self.menu.data.rawmessage), callback=self._editor_callback, callerid=self._callerid
        )
        self._slaves.append(editor)
        await editor.run(interaction)

    # Template/Custom Menu
    @select(cls=Select, placeholder="TEMPLATE_MENU_PLACEHOLDER", min_values=1, max_values=1)
    async def template_menu(self, selection: discord.Interaction, selected: Select):
        """
        Select a template for the menu message, or create a custom message.

        If the custom message does not already exist, it will be based on the current template.
        """
        templateid = int(selected.values[0])
        if templateid != self.menu.data.templateid:
            # Changes requested
            await selection.response.defer(thinking=True, ephemeral=True)
            if templateid == -1:
                # Chosen a custom message
                # Initialise the custom message if needed
                update_args = {'templateid': None}
                if not self.menu.data.rawmessage:
                    template = templates[self.menu.data.templateid]
                    margs = await template.render_menu(self.menu)
                    raw = {
                        'content': margs.kwargs.get('content', ''),
                    }
                    if 'embed' in margs.kwargs:
                        raw['embed'] = margs.kwargs['embed'].to_dict()
                    rawjson = json.dumps(raw)
                    update_args['rawmessage'] = rawjson

                # Save choice to data
                await self.menu.data.update(**update_args)

                # Spawn editor
                await self._message_editor(selection)
                await self.refresh()
                await self.update_preview()
                await self.menu.update_message()
            else:
                await self.menu.data.update(templateid=templateid)
                await self.refresh(thinking=selection)
                await self.update_preview()
                await self.menu.update_message()
        else:
            await selection.response.defer()

    async def template_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.template_menu
        menu.placeholder = t(_p(
            'ui:menu_editor|menu:template|placeholder',
            "Select Message Template"
        ))
        options = []
        for template in templates.values():
            option = template.as_option()
            option.default = (self.menu.data.templateid == template.id)
            options.append(option)
        custom_option = SelectOption(
            label=t(_p(
                'ui:menu_editor|menu:template|option:custom|label',
                "Custom Message"
            )),
            value='-1',
            description=t(_p(
                'ui:menu_editor|menu:template|option:custom|description',
                "Entirely custom menu message (opens an interactive editor)."
            )),
            default=(self.menu.data.templateid is None)
        )
        options.append(custom_option)
        menu.options = options

    # -- Common Components --
    # Delete Menu Button
    @button(label="DELETE_BUTTON_PLACEHOLDER", style=ButtonStyle.red)
    async def delete_button(self, press: discord.Interaction, pressed: Button):
        """
        Confirm menu deletion, and delete.
        """
        t = self.bot.translator.t
        confirm_msg = t(_p(
            'ui:menu_editor|button:delete|confirm|title',
            "Are you sure you want to delete this menu? This is not reversible!"
        ))
        confirm = Confirm(confirm_msg, self._callerid)
        confirm.confirm_button.label = t(_p(
            'ui:menu_editor|button:delete|confirm|button:yes',
            "Yes, Delete Now"
        ))
        confirm.confirm_button.style = ButtonStyle.red
        confirm.cancel_button.label = t(_p(
            'ui:menu_editor|button:delete|confirm|button:no',
            "No, Go Back"
        ))
        confirm.cancel_button.style = ButtonStyle.green
        try:
            result = await confirm.ask(press, ephemeral=True)
        except ResponseTimedOut:
            result = False

        if result:
            await self.menu.delete()
            await self.quit()

    async def delete_button_refresh(self):
        t = self.bot.translator.t
        button = self.delete_button
        button.label = t(_p(
            'ui:menu_editor|button:delete|label',
            "Delete Menu"
        ))

    # Quit Button
    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        """
        Close the UI. This should also close all children.
        """
        await press.response.defer(thinking=False)
        await self.quit()

    # Page Buttons
    @button(emoji=conf.emojis.forward)
    async def next_page_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        self.pagen += 1
        await self.refresh()

    @button(emoji=conf.emojis.backward)
    async def prev_page_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        self.pagen -= 1
        await self.refresh()

    # Edit Message Button
    @button(label="EDIT_MSG_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def edit_msg_button(self, press: discord.Interaction, pressed: Button):
        # Set the templateid to None if it isn't already
        # And initialise the rawmessage if it needs it.
        if (templateid := self.menu.data.templateid) is not None:
            update_args = {'templateid': None}
            if not self.menu.data.rawmessage:
                template = templates[templateid]
                margs = await template.render_menu(self.menu)
                raw = {
                    'content': margs.kwargs.get('content', ''),
                }
                if 'embed' in margs.kwargs:
                    raw['embed'] = margs.kwargs['embed'].to_dict()
                rawjson = json.dumps(raw)
                update_args['rawmessage'] = rawjson

            await self.menu.data.update(**update_args)

        # At this point we are certain the menu is in custom mode and has a rawmessage
        # Spawn editor
        await self._message_editor(press)
        await self.refresh()
        await self.update_preview()
        await self.menu.update_message()

    async def edit_msg_button_refresh(self):
        t = self.bot.translator.t
        button = self.edit_msg_button
        button.label = t(_p(
            'ui:menu_editor|button:edit_msg|label',
            "Edit Message"
        ))
        # Disable the button if we are on a non-managed message
        button.disabled = not self.menu.managed

    # Preview Button
    @button(label="PREVIEW_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def preview_button(self, press: discord.Interaction, pressed: Button):
        """
        Display or update the preview message.
        """
        args = await self.menu.make_args()
        view = await self.menu.make_view()
        if self._preview is not None:
            try:
                await self._preview.delete_original_response()
            except discord.HTTPException:
                pass
            self._preview = None
        await press.response.send_message(
            **args.send_args,
            view=view or discord.utils.MISSING,
            ephemeral=True
        )
        self._preview = press

    async def preview_button_refresh(self):
        t = self.bot.translator.t
        button = self.preview_button
        button.label = t(_p(
            'ui:menu_editor|button:preview|label',
            "Preview"
        ))

    # Repost Menu Button
    @button(label="REPOST_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def repost_button(self, press: discord.Interaction, pressed: Button):
        """
        Repost the menu in a selected channel.

        Pops up a minimal channel selection UI, asking where they want to post it.
        """
        t = self.bot.translator.t

        @AChannelSelect(
            placeholder=t(_p(
                'ui:menu_editor|button:repost|widget:repost|menu:channel|placeholder',
                "Select New Channel"
            )),
            channel_types=[discord.ChannelType.text, discord.ChannelType.voice],
            min_values=1, max_values=1
        )
        async def repost_widget(selection: discord.Interaction, selected: ChannelSelect):
            channel = selected.values[0].resolve() if selected.values else None
            if channel is None:
                await selection.response.defer()
            else:
                # Valid channel selected, do the repost
                await selection.response.defer(thinking=True, ephemeral=True)

                try:
                    await self.menu.repost_to(channel)
                except discord.Forbidden:
                    title = t(_p(
                        'ui:menu_editor|button:repost|widget:repost|error:perms|title',
                        "Insufficient Permissions!"
                    ))
                    desc = t(_p(
                        'ui:menu_editor|button:repost|eidget:repost|error:perms|desc',
                        "I lack the `EMBED_LINKS` or `SEND_MESSAGES` permission in this channel."
                    ))
                    embed = discord.Embed(
                        colour=discord.Colour.brand_red(),
                        title=title,
                        description=desc
                    )
                    await selection.edit_original_response(embed=embed)
                except discord.HTTPException:
                    error = discord.Embed(
                        colour=discord.Colour.brand_red(),
                        description=t(_p(
                            'ui:menu_editor|button:repost|widget:repost|error:post_failed',
                            "An error ocurred while posting to {channel}. Do I have sufficient permissions?"
                        )).format(channel=channel.mention)
                    )
                    await selection.edit_original_response(embed=error)
                else:
                    try:
                        await press.delete_original_response()
                    except discord.HTTPException:
                        pass

                    success_title = t(_p(
                        'ui:menu_editor|button:repost|widget:repost|success|title',
                        "Role Menu Moved"
                    ))
                    desc_lines = []
                    desc_lines.append(
                        t(_p(
                            'ui:menu_editor|button:repost|widget:repost|success|desc:general',
                            "The role menu `{name}` is now available at {message_link}."
                        )).format(
                            name=self.menu.data.name,
                            message_link=self.menu.message.jump_url,
                        )
                    )
                    if self.menu.data.menutype is MenuType.REACTION:
                        try:
                            await self.menu.update_reactons()
                        except SafeCancellation as e:
                            desc_lines.append(e.msg)
                        else:
                            t(_p(
                                'ui:menu_editor|button:repost|widget:repost|success|desc:reactions',
                                "Please check the message reactions are correct."
                            ))
                    await selection.edit_original_response(
                        embed=discord.Embed(
                            title=success_title,
                            description='\n'.join(desc_lines),
                            colour=discord.Colour.brand_green(),
                        )
                    )

        # Create the selection embed
        title = t(_p(
            'ui:menu_editor|button:repost|widget:repost|title',
            "Repost Role Menu"
        ))
        desc = t(_p(
            'ui:menu_editor|button:repost|widget:repost|description',
            "Please select the channel to which you want to resend this menu."
        ))
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title, description=desc
        )
        # Send as response with the repost widget attached
        await press.response.send_message(embed=embed, view=AsComponents(repost_widget))

    async def repost_button_refresh(self):
        t = self.bot.translator.t
        button = self.repost_button
        if self.menu.message is not None:
            button.label = t(_p(
                'ui:menu_editor|button:repost|label:repost',
                "Repost"
            ))
        else:
            button.label = t(_p(
                'ui:menu_editor|button:repost|label:post',
                "Post"
            ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        # TODO: Link to actual message

        title = t(_p(
            'ui:menu_editor|embed|title',
            "Role Menu Editor"
        )).format(name=self.menu.config.name.value)

        table = await RoleMenuOptions().make_setting_table(self.menu.data.menuid)

        jump = self.menu.jump_link
        if jump:
            jump_text = t(_p(
                'ui:menu_editor|embed|description|jump_text:attached',
                "Members may use this menu from {jump_url}"
            )).format(jump_url=jump)
        else:
            jump_text = t(_p(
                'ui:menu_editor|embed|description|jump_text:unattached',
                "This menu is not currently active!\n"
                "Make it available by clicking `Post` below."
            ))

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title,
            description=jump_text + '\n' + table
        )
        # Tip field
        embed.add_field(
            inline=False,
            name=t(_p(
                'ui:menu_editor|embed|field:tips|name',
                "Command Tips"
            )),
            value=t(_p(
                'ui:menu_editor|embed|field:tips|value',
                "Use the following commands for faster menu setup.\n"
                "{menuedit} to edit the above menu options.\n"
                "{addrole} to add new roles (recommended for roles with emojis).\n"
                "{editrole} to edit role options."
            )).format(
                menuedit=self.bot.core.mention_cmd('rolemenu editmenu'),
                addrole=self.bot.core.mention_cmd('rolemenu addrole'),
                editrole=self.bot.core.mention_cmd('rolemenu editrole'),
            )
        )

        # Compute and add the pages
        for mrole in self.page_block:
            name = f"{mrole.config.label.formatted}"
            prop_map = {
                mrole.config.emoji.display_name: mrole.config.emoji.formatted,
                mrole.config.price.display_name: mrole.config.price.formatted,
                mrole.config.duration.display_name: mrole.config.duration.formatted,
                mrole.config.description.display_name: mrole.config.description.formatted,
            }
            prop_table = '\n'.join(tabulate(*prop_map.items()))
            value = f"{mrole.config.role.formatted}\n{prop_table}"

            embed.add_field(name=name, value=value, inline=True)

        return MessageArgs(embed=embed)

    async def _handle_invalid_emoji(self, error: discord.HTTPException):
        t = self.bot.translator.t

        text = error.text
        splits = text.split('.')
        i = splits.index('emoji')
        role_index = int(splits[i-1])
        mrole = self.menu.roles[role_index]

        error = discord.Embed(
            colour=discord.Colour.brand_red(),
            title=t(_p(
                'ui:menu_editor|error:invald_emoji|title',
                "Invalid emoji encountered."
            )),
            description=t(_p(
                'ui:menu_editor|error:invalid_emoji|desc',
                "The emoji `{emoji}` for menu role `{label}` no longer exists, unsetting."
            )).format(emoji=mrole.config.emoji.data, label=mrole.config.label.data)
        )
        await mrole.data.update(emoji=None)
        await self.channel.send(embed=error)

    async def _redraw(self, args):
        try:
            await super()._redraw(args)
        except discord.HTTPException as e:
            if e.code == 50035 and 'Invalid emoji' in e.text:
                await self._handle_invalid_emoji(e)
                await self.refresh()
                await self.update_preview()
                await self.menu.update_message()
            else:
                raise e

    async def draw(self, *args, **kwargs):
        try:
            await super().draw(*args, **kwargs)
        except discord.HTTPException as e:
            if e.code == 50035 and 'Invalid emoji' in e.text:
                await self._handle_invalid_emoji(e)
                await self.draw(*args, **kwargs)
                await self.menu.update_message()
            else:
                raise e

    async def refresh_layout(self):
        to_refresh = (
            self.options_button_refresh(),
            self.reqroles_menu_refresh(),
            self.sticky_button_refresh(),
            self.refunds_button_refresh(),
            self.bulk_edit_button_refresh(),
            self.modify_roles_button_refresh(),
            self.add_roles_menu_refresh(),
            self.edit_roles_menu_refresh(),
            self.del_role_menu_refresh(),
            self.style_button_refresh(),
            self.style_menu_refresh(),
            self.template_menu_refresh(),
            self.preview_button_refresh(),
            self.delete_button_refresh(),
            self.edit_msg_button_refresh(),
            self.repost_button_refresh(),
        )
        await asyncio.gather(*to_refresh)

        line_last = (
            self.options_button, self.modify_roles_button, self.style_button, self.delete_button, self.quit_button
        )
        line_1 = (
            self.preview_button, self.edit_msg_button, self.repost_button,
        )
        if self.page_count > 1:
            line_1 = (self.prev_page_button, *line_1, self.next_page_button)
        if self.mode is EditorMode.OPTIONS:
            self.set_layout(
                line_1,
                (self.bulk_edit_button, self.sticky_button, self.refunds_button,),
                (self.reqroles_menu,),
                line_last,
            )
        elif self.mode is EditorMode.ROLES:
            self.set_layout(
                line_1,
                (self.add_roles_menu,),
                (self.edit_roles_menu,),
                (self.del_role_menu,),
                line_last
            )
        elif self.mode is EditorMode.STYLE:
            self.set_layout(
                line_1,
                (self.style_menu,),
                (self.template_menu,),
                line_last
            )

    async def reload(self):
        mroles = self.menu.roles
        page_size = 6
        blocks = [mroles[i:i+page_size] for i in range(0, len(mroles), page_size)] or [[]]
        self.page_count = len(blocks)
        self.pagen = self.pagen % self.page_count
        self.page_block = blocks[self.pagen]
        await self.menu.fetch_message()

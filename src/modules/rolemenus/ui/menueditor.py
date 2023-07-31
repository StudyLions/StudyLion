import asyncio
import json
from typing import Optional
from enum import Enum

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, Select, RoleSelect, ChannelSelect, SelectOption

from meta import LionBot, conf
from meta.errors import UserInputError
from utils.lib import utc_now, MessageArgs, error_embed
from utils.ui import MessageUI, ConfigEditor, FastModal, error_handler_for, ModalRetryUI, MsgEditor
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


class EditorMode(Enum):
    OPTIONS = 0
    ROLES = 1
    STYLE = 2


class MenuEditor(MessageUI):
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

        # UI State
        self.mode: EditorMode = EditorMode.ROLES
        self.pagen: int = 0
        self._preview: Optional[discord.Interaction] = None

    # ----- UI API -----
    async def dispatch_update(self):
        """
        Broadcast that the menu has changed.

        This updates the preview, and tells the menu itself to update any linked messages.
        """
        await self.menu.reload()
        if self._preview is not None:
            args = await self._preview_args()
            try:
                await self._preview.edit_original_response(**args.edit_args)
            except discord.NotFound:
                self._preview = None

    async def _preview_args(self):
        if (tid := self.menu.data.templateid) is not None:
            # Apply template
            template = templates[tid]
            args = await template.render_menu(self.menu)
        else:
            raw = self.menu.data.rawmessage
            data = json.loads(raw)
            args = MessageArgs(
                content=data.get('content', ''),
                embed=discord.Embed.from_dict(data['embed'])
            )
        return args

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
                # Propagate an update
                await self.dispatch_update()
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
        await self.dispatch_update()
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
        await self.dispatch_update()
        await self.refresh(thinking=press)

    async def refunds_button_refresh(self):
        t = self.bot.translator.t
        button = self.refunds_button
        button.label = t(_p(
            'ui:menu_editor|button:refunds|label',
            "Refunds"
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
        await self.dispatch_update()
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
                # Propagate an update
                await self.dispatch_update()
                # Refresh the UI
                await self.refresh(thinking=interaction)
            else:
                # Nothing was modified, quietly accept
                await interaction.response.defer(thinking=False)

        await interaction.response.send_modal(modal)
        await self.dispatch_update()

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
                # TODO: Emoji generation
                rows = await self.data.RoleMenuRole.table.insert_many(
                    ('menuid', 'roleid', 'label'),
                    *((self.menu.data.menuid, role.id, role.name[:100]) for role in to_create.values())
                ).with_adapter(self.data.RoleMenuRole._make_rows)
                mroles = [RoleMenuRole(self.bot, row) for row in rows]
                single = single if single is not None else mroles[0]
                await self.dispatch_update()

            if len(roles) == 1:
                await self._edit_menu_role(selection, single)
                await self.refresh()
            else:
                await selection.response.defer()
                await self.refresh()

    async def add_roles_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.add_roles_menu
        menu.placeholder = t(_p(
            'ui:menu_editor|menu:add_roles|placeholder',
            "Add Roles"
        ))

    def _role_option(self, menurole: RoleMenuRole):
        return SelectOption(
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
            await self.dispatch_update()
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
                    "Cannot change the style of a menu attached to a message I did not send! Please RePost first."
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
        value = int(selected.values[0])
        menutype = MenuType(value)
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
            await self.dispatch_update()
            await self.refresh(thinking=selection)
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
                value=str(MenuType.REACTION.value),
                default=(self.menu.data.menutype is MenuType.REACTION)
            ),
            SelectOption(
                label=t(_p('ui:menu_editor|menu:style|option:button|label', "Button Menu")),
                description=t(_p(
                    'ui:menu_editor|menu:style|option:button|desc',
                    "Roles are represented in 5 rows of 5 buttons, each with an emoji and label."
                )),
                value=str(MenuType.BUTTON.value),
                default=(self.menu.data.menutype is MenuType.BUTTON)
            ),
            SelectOption(
                label=t(_p('ui:menu_editor|menu:style|option:dropdown|label', "Dropdown Menu")),
                description=t(_p(
                    'ui:menu_editor|menu:style|option:dropdown|desc',
                    "Roles are selectable from a dropdown menu below the message."
                )),
                value=str(MenuType.DROPDOWN.value),
                default=(self.menu.data.menutype is MenuType.DROPDOWN)
            )
        ]

    async def _editor_callback(self, new_data):
        raws = json.dumps(new_data)
        await self.menu.data.update(rawmessage=raws)
        await self.dispatch_update()

    async def _message_editor(self, interaction: discord.Interaction):
        # Spawn the message editor with the current rawmessage data.
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
                await self.dispatch_update()
                await self.refresh()
            else:
                await self.menu.data.update(templateid=templateid)
                await self.dispatch_update()
                await self.refresh(thinking=selection)
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
    # Quit Button

    # Page left Button
    # Edit Message Button
    # Preview Button
    @button(label="PREVIEW_BUTTON_PLACEHOLDER", style=ButtonStyle.blurple)
    async def preview_button(self, press: discord.Interaction, pressed: Button):
        """
        Display or update the preview message.
        """
        args = await self._preview_args()
        if self._preview is not None:
            try:
                await self._preview.delete_original_response()
            except discord.HTTPException:
                pass
            self._preview = None
        await press.response.send_message(**args.send_args, ephemeral=True)
        self._preview = press

    async def preview_button_refresh(self):
        t = self.bot.translator.t
        button = self.preview_button
        button.label = t(_p(
            'ui:menu_editor|button:preview|label',
            "Preview"
        ))

    # Repost Menu Button

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t

        title = t(_p(
            'ui:menu_editor|embed|title',
            "'{name}' Role Menu Editor"
        )).format(name=self.menu.config.name.value)

        table = await RoleMenuOptions().make_setting_table(self.menu.data.menuid)

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title,
            description=table
        )
        return MessageArgs(embed=embed)

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
        )
        await asyncio.gather(*to_refresh)

        line_1 = (
            self.options_button, self.modify_roles_button, self.style_button,
        )
        line_last = (
            self.preview_button,
        )
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
        ...

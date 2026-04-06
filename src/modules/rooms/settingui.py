import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Import RoleSelect for room moderator role config
from discord.ui.select import select, ChannelSelect, RoleSelect
# --- END AI-MODIFIED ---

from meta import LionBot

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from .settings import RoomSettings
from . import babel

_p = babel._p


class RoomSettingUI(ConfigUI):
    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Include both model_settings and list_settings for the config panel
    setting_classes = RoomSettings.model_settings + RoomSettings.list_settings
    # --- END AI-MODIFIED ---

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('RoomCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    # ----- UI Components -----
    @select(cls=ChannelSelect, channel_types=[discord.ChannelType.category],
            min_values=0, max_values=1,
            placeholder='CATEGORY_PLACEHOLDER')
    async def category_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        await selection.response.defer()
        setting = self.instances[0]
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()

    async def category_menu_refresh(self):
        self.category_menu.placeholder = self.bot.translator.t(_p(
            'ui:room_config|menu:category|placeholder',
            "Select Private Room Category"
        ))

    @button(label="VISIBLE_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def visible_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        setting = next(inst for inst in self.instances if inst.setting_id == RoomSettings.Visible.setting_id)
        await setting.interaction_check(setting.parent_id, press)
        setting.value = not setting.value
        await setting.write()

    async def visible_button_refresh(self):
        button = self.visible_button
        button.label = self.bot.translator.t(_p(
            'ui:room_config|button:visible|label',
            "Toggle Room Visibility"
        ))
        setting = next(inst for inst in self.instances if inst.setting_id == RoomSettings.Visible.setting_id)
        button.style = ButtonStyle.green if setting.value else ButtonStyle.grey

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: Add role select for configuring room moderator role
    @select(cls=RoleSelect, min_values=0, max_values=1,
            placeholder='ROLE_PLACEHOLDER')
    async def role_menu(self, selection: discord.Interaction, selected: RoleSelect):
        await selection.response.defer()
        setting = next(inst for inst in self.instances if inst.setting_id == RoomSettings.RentingRole.setting_id)
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()

    async def role_menu_refresh(self):
        self.role_menu.placeholder = self.bot.translator.t(_p(
            'ui:room_config|menu:role|placeholder',
            "Select Room Moderator Role"
        ))
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-01) ---
    # Purpose: RoleSelect menus for configuring room rent role gate (required + any-of)
    @select(cls=RoleSelect, min_values=0, max_values=25,
            placeholder='REQUIRED_ROLES_PLACEHOLDER')
    async def required_roles_menu(self, selection: discord.Interaction, selected: RoleSelect):
        await selection.response.defer(thinking=True)
        setting = next(
            inst for inst in self.instances
            if inst.setting_id == RoomSettings.RentRequiredRoles.setting_id
        )
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values
        await setting.write()
        await selection.delete_original_response()

    async def required_roles_menu_refresh(self):
        self.required_roles_menu.placeholder = self.bot.translator.t(_p(
            'ui:room_config|menu:required_roles|placeholder',
            "Select Required Roles (must have ALL)"
        ))

    @select(cls=RoleSelect, min_values=0, max_values=25,
            placeholder='ANYOF_ROLES_PLACEHOLDER')
    async def anyof_roles_menu(self, selection: discord.Interaction, selected: RoleSelect):
        await selection.response.defer(thinking=True)
        setting = next(
            inst for inst in self.instances
            if inst.setting_id == RoomSettings.RentAnyOfRoles.setting_id
        )
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values
        await setting.write()
        await selection.delete_original_response()

    async def anyof_roles_menu_refresh(self):
        self.anyof_roles_menu.placeholder = self.bot.translator.t(_p(
            'ui:room_config|menu:anyof_roles|placeholder',
            "Select Any-Of Roles (must have at least ONE)"
        ))
    # --- END AI-MODIFIED ---

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:rooms_config|embed|title',
            "Private Room System Configuration Panel"
        ))
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title
        )
        for setting in self.instances:
            embed.add_field(**setting.embed_field, inline=False)

        args = MessageArgs(embed=embed)
        return args

    async def reload(self):
        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Load both ModelData settings (from guild config) and ListData settings (from their tables)
        # --- Original code (commented out for rollback) ---
        # lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        # self.instances = tuple(
        #     lguild.config.get(setting.setting_id)
        #     for setting in self.settings.model_settings
        # )
        # --- End original code ---
        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        model_instances = [
            lguild.config.get(setting.setting_id)
            for setting in self.settings.model_settings
        ]
        list_instances = [
            await setting.get(self.guildid)
            for setting in self.settings.list_settings
        ]
        self.instances = tuple(model_instances + list_instances)
        # --- END AI-MODIFIED ---

    async def refresh_components(self):
        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Include role_menu + role gate menus in config panel refresh and layout
        # --- Original code (commented out for rollback) ---
        # await asyncio.gather(
        #     self.category_menu_refresh(),
        #     self.visible_button_refresh(),
        #     self.edit_button_refresh(),
        #     self.close_button_refresh(),
        #     self.reset_button_refresh(),
        # )
        # self.set_layout(
        #     (self.category_menu,),
        #     (self.visible_button, self.edit_button, self.reset_button, self.close_button)
        # )
        # --- End original code ---
        await asyncio.gather(
            self.category_menu_refresh(),
            self.role_menu_refresh(),
            self.required_roles_menu_refresh(),
            self.anyof_roles_menu_refresh(),
            self.visible_button_refresh(),
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
        )
        self.set_layout(
            (self.category_menu,),
            (self.role_menu,),
            (self.required_roles_menu,),
            (self.anyof_roles_menu,),
            (self.visible_button, self.edit_button, self.reset_button, self.close_button)
        )
        # --- END AI-MODIFIED ---


class RoomDashboard(DashboardSection):
    section_name = _p(
        'dash:rooms|title',
        "Private Room Configuration ({commands[admin config rooms]})"
    )
    _option_name = _p(
        "dash:economy|dropdown|placeholder",
        "Private Room Panel"
    )
    configui = RoomSettingUI
    setting_classes = RoomSettingUI.setting_classes

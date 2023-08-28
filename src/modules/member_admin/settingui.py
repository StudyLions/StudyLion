import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, RoleSelect, ChannelSelect

from meta import LionBot

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs
from utils.ui.msgeditor import MsgEditor
from wards import equippable_role

from .settings import MemberAdminSettings as Settings
from . import babel

_p = babel._p


class MemberAdminUI(ConfigUI):
    setting_classes = (
        Settings.GreetingChannel,
        Settings.GreetingMessage,
        Settings.ReturningMessage,
        Settings.Autoroles,
        Settings.BotAutoroles,
        Settings.RolePersistence,
    )

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('MemberAdminCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    # ----- UI Components -----
    # Greeting Channel
    @select(
        cls=ChannelSelect,
        channel_types=[discord.ChannelType.voice, discord.ChannelType.text],
        placeholder="GREETCH_MENU_PLACEHOLDER",
        min_values=0, max_values=1
    )
    async def greetch_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        """
        Selector for the `greeting_channel` setting.
        """
        await selection.response.defer(thinking=True, ephemeral=True)
        setting = self.get_instance(Settings.GreetingChannel)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()
        await selection.delete_original_response()
    
    async def greetch_menu_refresh(self):
        menu = self.greetch_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:memberadmin|menu:greetch|placeholder',
            "Select Greeting Channel"
        ))

    # Autoroles
    @select(
        cls=RoleSelect,
        placeholder="AUTOROLES_MENU_PLACEHOLDER",
        min_values=0, max_values=25
    )
    async def autoroles_menu(self, selection: discord.Interaction, selected: RoleSelect):
        """
        Simple multi-role selector for the 'autoroles' setting.
        """
        await selection.response.defer(thinking=True, ephemeral=True)
        for role in selected.values:
            # Check authority to set these roles (for author and client)
            await equippable_role(self.bot, role, selection.user)

        setting = self.get_instance(Settings.Autoroles)
        setting.value = selected.values
        await setting.write()
        # Instance hooks will update the menu
        await selection.delete_original_response()
    
    async def autoroles_menu_refresh(self):
        menu = self.autoroles_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:memberadmin|menu:autoroles|placeholder',
            "Select Autoroles"
        ))

    # Bot autoroles
    @select(
        cls=RoleSelect,
        placeholder="BOT_AUTOROLES_MENU_PLACEHOLDER",
        min_values=0, max_values=25
    )
    async def bot_autoroles_menu(self, selection: discord.Interaction, selected: RoleSelect):
        """
        Simple multi-role selector for the 'bot_autoroles' setting.
        """
        await selection.response.defer(thinking=True, ephemeral=True)
        for role in selected.values:
            # Check authority to set these roles (for author and client)
            await equippable_role(self.bot, role, selection.user)

        setting = self.get_instance(Settings.BotAutoroles)
        setting.value = selected.values
        await setting.write()
        # Instance hooks will update the menu
        await selection.delete_original_response()
    
    async def bot_autoroles_menu_refresh(self):
        menu = self.bot_autoroles_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:memberadmin|menu:bot_autoroles|placeholder',
            "Select Bot Autoroles"
        ))

    # Greeting Msg
    @button(
        label="GREET_MSG_BUTTON_PLACEHOLDER",
        style=ButtonStyle.blurple
    )
    async def greet_msg_button(self, press: discord.Interaction, pressed: Button):
        """
        Message Editor Button for the `greeting_message` setting.

        This will open up a Message Editor with the current `greeting_message`,
        if set, otherwise a default `greeting_message`.
        This also generates a preview formatter using the calling user.
        """
        await press.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t
        setting = self.get_instance(Settings.GreetingMessage)

        value = setting.value
        if value is None:
            value = setting._data_to_value(self.guildid, t(setting._soft_default))
            setting.value = value
            await setting.write()

        editor = MsgEditor(
            self.bot,
            value,
            callback=setting.editor_callback,
            formatter=await setting.generate_formatter(self.bot, press.user),
            callerid=press.user.id,
        )
        self._slaves.append(editor)
        await editor.run(press)
    
    async def greet_msg_button_refresh(self):
        button = self.greet_msg_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:member_admin|button:greet_msg|label',
            "Greeting Msg"
        ))

    # Returning Msg
    @button(
        label="RETURN_MSG_BUTTON_PLACEHOLDER",
        style=ButtonStyle.blurple
    )
    async def return_msg_button(self, press: discord.Interaction, pressed: Button):
        """
        Message Editor Button for the `returning_message` setting.

        Similar to the `greet_msg_button`, this opens a Message Editor
        with the current `returning_message`.
        If the setting is unset, will instead either use the current `greeting_message`,
        or if that is also unset, use a default `returning_message`.
        """
        await press.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t
        setting = self.get_instance(Settings.ReturningMessage)
        greeting = self.get_instance(Settings.GreetingMessage)

        value = setting.value
        if value is not None:
            pass
        elif greeting.value is not None:
            value = greeting.value
        else:
            value = setting._data_to_value(self.guildid, t(setting._soft_default))
            setting.value = value
            await setting.write()

        editor = MsgEditor(
            self.bot,
            value,
            callback=setting.editor_callback,
            formatter=await setting.generate_formatter(
                self.bot, press.user, press.user.joined_at.timestamp()
            ),
            callerid=press.user.id,
        )
        self._slaves.append(editor)
        await editor.run(press)
    
    async def return_msg_button_refresh(self):
        button = self.return_msg_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:memberadmin|button:return_msg|label',
            "Returning Msg"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:memberadmin|embed|title',
            "Member Admin Configuration Panel"
        ))
        embed = discord.Embed(
            title=title,
            colour=discord.Colour.orange()
        )
        for setting in self.instances:
            embed.add_field(**setting.embed_field, inline=False)

        return MessageArgs(embed=embed)

    async def reload(self):
        # Re-fetch data for each instance
        # This should generally hit cache
        self.instances = [
            await setting.get(self.guildid)
            for setting in self.setting_classes
        ]

    async def refresh_components(self):
        component_refresh = (
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
            self.greetch_menu_refresh(),
            self.autoroles_menu_refresh(),
            self.bot_autoroles_menu_refresh(),
            self.greet_msg_button_refresh(),
            self.return_msg_button_refresh(),
        )
        await asyncio.gather(*component_refresh)

        self.set_layout(
            (self.greetch_menu,),
            (self.autoroles_menu,),
            (self.bot_autoroles_menu,),
            (self.greet_msg_button, self.return_msg_button,
             self.edit_button, self.reset_button, self.close_button),
        )


class MemberAdminDashboard(DashboardSection):
    section_name = _p(
        "dash:member_admin|title",
        "Greetings and Initial Roles ({commands[configure welcome]})"
    )
    _option_name = _p(
        "dash:member_admin|dropdown|placeholder",
        "Greetings and Initial Roles Panel"
    )
    configui = MemberAdminUI
    setting_classes = MemberAdminUI.setting_classes

    def apply_to(self, page: discord.Embed):
        """
        Overriding DashboardSection apply_to to split into two sections.
        """
        t = self.bot.translator.t
        sections = [
            self.instances[:3],
            self.instances[3:]
        ]
        
        # Greeting messages
        table = self._make_table(sections[0])
        page.add_field(
            name=t(_p(
                'dash:member_admin|section:greeting_messages|name',
                "Greeting Messages ({commands[configure welcome]})"
            )).format(commands=self.bot.core.mention_cache),
            value=table,
            inline=False
        )

        # Initial Roles
        table = self._make_table(sections[1])
        page.add_field(
            name=t(_p(
                'dash:member_admin|section:initial_roles|name',
                "Initial Roles ({commands[configure welcome]})"
            )).format(commands=self.bot.core.mention_cache),
            value=table,
            inline=False
        )

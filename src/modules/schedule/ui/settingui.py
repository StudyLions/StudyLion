import itertools
import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, ChannelSelect, RoleSelect

from meta import LionBot

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs

from ..settings import ScheduleSettings
from .. import babel

_p = babel._p


class ScheduleSettingUI(ConfigUI):
    pages = [
        (
            ScheduleSettings.SessionLobby,
            ScheduleSettings.SessionRoom,
            ScheduleSettings.SessionChannels,
        ), (
            ScheduleSettings.ScheduleCost,
            ScheduleSettings.AttendanceReward,
            ScheduleSettings.AttendanceBonus,
            ScheduleSettings.MinAttendance,
        ), (
            ScheduleSettings.BlacklistRole,
            ScheduleSettings.BlacklistAfter,
        )
    ]
    setting_classes = list(itertools.chain(*pages))

    def _init_children(self):
        # HACK to stop ViewWeights complaining that this UI has too many children
        # Children will be correctly initialised after parent init.
        return []

    def __init__(self, bot: LionBot, guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('ScheduleCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)
        self._children = super()._init_children()
        self.page_num = 0

    def get_instance(self, setting):
        return next(instance for instance in self.instances if instance.setting_id == setting.setting_id)

    @property
    def page_instances(self):
        start = sum(len(page) for page in self.pages[:self.page_num])
        end = start + len(self.pages[self.page_num])
        return self.instances[start:end]

    # ----- UI Components -----
    # Page 0 button
    @button(label="PAGE0_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def page0_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.page_num = 0
        await self.refresh(thinking=press)

    async def page0_button_refresh(self):
        t = self.bot.translator.t
        self.page0_button.label = t(_p(
            'ui:schedule_config|button:page0|label',
            "Page 1"
        ))
        self.page0_button.disabled = (self.page_num == 0)

    # Lobby channel selector
    @select(cls=ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.voice],
            min_values=0, max_values=1,
            placeholder='LOBBY_PLACEHOLDER')
    async def lobby_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        # TODO: Setting value checks
        await selection.response.defer()
        setting = self.get_instance(ScheduleSettings.SessionLobby)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()

    async def lobby_menu_refresh(self):
        t = self.bot.translator.t
        self.lobby_menu.placeholder = t(_p(
            'ui:schedule_config|menu:lobby|placeholder',
            "Select Lobby Channel"
        ))

    # Room channel selector
    @select(cls=ChannelSelect, channel_types=[discord.ChannelType.category, discord.ChannelType.voice],
            min_values=0, max_values=1,
            placeholder='ROOM_PLACEHOLDER')
    async def room_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        await selection.response.defer()
        setting = self.get_instance(ScheduleSettings.SessionRoom)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()

    async def room_menu_refresh(self):
        t = self.bot.translator.t
        self.room_menu.placeholder = t(_p(
            'ui:schedule_config|menu:room|placeholder',
            "Select Session Room"
        ))

    # Session channels selector
    @select(cls=ChannelSelect, channel_types=[discord.ChannelType.category, discord.ChannelType.voice],
            min_values=0, max_values=25,
            placeholder='CHANNELS_PLACEHOLDER')
    async def channels_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        # TODO: Consider XORing input
        await selection.response.defer()
        setting = self.get_instance(ScheduleSettings.SessionChannels)
        setting.value = selected.values
        await setting.write()

    async def channels_menu_refresh(self):
        t = self.bot.translator.t
        self.channels_menu.placeholder = t(_p(
            'ui:schedule_config|menu:channels|placeholder',
            "Select Session Channels"
        ))

    # Page 1 button
    @button(label="PAGE1_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def page1_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.page_num = 1
        await self.refresh(thinking=press)

    async def page1_button_refresh(self):
        t = self.bot.translator.t
        self.page1_button.label = t(_p(
            'ui:schedule_config|button:page1|label',
            "Page 2"
        ))
        self.page1_button.disabled = (self.page_num == 1)

    # Page 3 button
    @button(label="PAGE2_BUTTON_PLACEHOLDER", style=ButtonStyle.grey)
    async def page2_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.page_num = 2
        await self.refresh(thinking=press)

    async def page2_button_refresh(self):
        t = self.bot.translator.t
        self.page2_button.label = t(_p(
            'ui:schedule_config|button:page2|label',
            "Page 3"
        ))
        self.page2_button.disabled = (self.page_num == 3)

    # Blacklist role selector
    @select(cls=RoleSelect, min_values=0, max_values=1, placeholder="BLACKLIST_ROLE_PLACEHOLDER")
    async def blacklist_role_menu(self, selection: discord.Interaction, selected: RoleSelect):
        await selection.response.defer()
        setting = self.get_instance(ScheduleSettings.BlacklistRole)
        setting.value = selected.values[0] if selected.values else None
        # TODO: Warning for insufficient permissions?
        await setting.write()

    async def blacklist_role_menu_refresh(self):
        t = self.bot.translator.t
        self.blacklist_role_menu.placeholder = t(_p(
            'ui:schedule_config|menu:blacklist_role|placeholder',
            "Select Blacklist Role"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:schedule_config|embed|title',
            "Scheduled Session Configuration Panel"
        ))
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title
        )
        for setting in self.page_instances:
            embed.add_field(**setting.embed_field, inline=False)

        args = MessageArgs(embed=embed)
        return args

    async def refresh_components(self):
        await asyncio.gather(
            self.page0_button_refresh(),
            self.page1_button_refresh(),
            self.page2_button_refresh(),
            self.edit_button_refresh(),
            self.reset_button_refresh(),
            self.close_button_refresh(),
        )
        if self.page_num == 0:
            await asyncio.gather(
                self.lobby_menu_refresh(),
                self.room_menu_refresh(),
                self.channels_menu_refresh(),
            )
            self.set_layout(
                (self.page0_button, self.page1_button, self.page2_button),
                (self.lobby_menu,),
                (self.room_menu,),
                (self.channels_menu,),
                (self.edit_button, self.reset_button, self.close_button),
            )
        elif self.page_num == 1:
            self.set_layout(
                (self.page0_button, self.page1_button, self.page2_button),
                (self.edit_button, self.reset_button, self.close_button),
            )
        elif self.page_num == 2:
            await asyncio.gather(
                self.blacklist_role_menu_refresh()
            )
            self.set_layout(
                (self.page0_button, self.page1_button, self.page2_button),
                (self.blacklist_role_menu,),
                (self.edit_button, self.reset_button, self.close_button),
            )


class ScheduleDashboard(DashboardSection):
    section_name = _p(
        'dash:schedule|title',
        "Scheduled Session Configuration ({commands[configure schedule]})"
    )
    configui = ScheduleSettingUI
    setting_classes = ScheduleSettingUI.setting_classes

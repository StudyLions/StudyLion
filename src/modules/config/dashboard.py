from typing import Optional

import discord
from discord.ui.select import select, Select, SelectOption
from discord.ui.button import button, Button, ButtonStyle

from meta import conf, LionBot
from utils.lib import MessageArgs
from utils.ui import BasePager

from modules.economy.settingui import EconomyDashboard
from modules.tasklist.settings import TasklistDashboard
from tracking.voice.settings import VoiceTrackerDashboard
from tracking.text.ui import TextTrackerDashboard
from modules.ranks.ui.config import RankDashboard
from modules.pomodoro.settingui import TimerDashboard
from modules.rooms.settingui import RoomDashboard
from babel.settingui import LocaleDashboard
from modules.schedule.ui.settingui import ScheduleDashboard
from modules.statistics.settings import StatisticsDashboard
from modules.member_admin.settingui import MemberAdminDashboard
from modules.moderation.settingui import ModerationDashboard
from modules.video_channels.settingui import VideoDashboard


from . import babel, logger


_p = babel._p


class GuildDashboard(BasePager):
    """
    Paged UI providing an overview of the guild configuration.
    """
    pages = [
        (MemberAdminDashboard, LocaleDashboard, EconomyDashboard,),
        (ModerationDashboard, VideoDashboard,),
        (VoiceTrackerDashboard, TextTrackerDashboard, RankDashboard, StatisticsDashboard,),
        (TasklistDashboard, RoomDashboard, TimerDashboard,),
        (ScheduleDashboard,),
    ]

    def __init__(self, bot: LionBot, guild: discord.Guild, callerid: int, channelid: int, **kwargs):
        super().__init__(**kwargs)

        self.bot = bot
        self.guild = guild
        self.guildid = guild.id
        self.callerid = callerid

        self.page_num = 0

        self.child_config = None
        self._cached_pages = {}

        self._original = None
        self._channelid = channelid
        self.set_active()

        # Map settingid -> setting of listening setting classes
        self._listening = {}

    async def interaction_check(self, interaction: discord.Interaction):
        return self.access_check(interaction.user.id)

    def access_check(self, userid):
        return userid == self.callerid

    async def cleanup(self):
        for instance in self._listening.values():
            instance.deregister_callback(self.id)
        self._listening.clear()

        await super().cleanup()

    # ----- Pager Control -----
    async def get_page(self, page_id) -> MessageArgs:
        page_id %= len(self.pages)
        if (page := self._cached_pages.get(page_id, None)) is not None:
            pass
        else:
            # Format settings into a dashboard embed
            embed = discord.Embed(
                title="Guild Dashboard",
                colour=discord.Colour.orange()
            )

            section_classes = self.pages[page_id]
            sections = [
                await section_cls(self.bot, self.guildid).load()
                for section_cls in section_classes
            ]

            for section in sections:
                section.apply_to(embed)
                for setting in section.instances:
                    if setting.setting_id not in self._listening:
                        setting.register_callback(self.id)(self.reload)
                        self._listening[setting.setting_id] = setting

            page = MessageArgs(embed=embed)
            self._cached_pages[page_id] = page
        return page

    async def page_cmd(self, interaction: discord.Interaction, value: str):
        # TODO
        ...

    async def page_acmpl(self, interaction: discord.Interaction, partial: str):
        # TODO
        ...

    # ----- UI Components -----

    @select(placeholder="CONFIG_PLACEHOLDER")
    async def config_menu(self, interaction: discord.Interaction, selected: Select):
        """
        Select a configuration group to edit.

        Displays a list of Dashboard sections.
        When a section is selected, displays the associated ConfigUI.
        Closes the current ConfigUI if open.
        """
        await interaction.response.defer()
        value = int(selected.values[0])
        i = value // 10
        j = value % 10
        section = self.pages[i][j]
        if self.child_config is not None:
            if self.child_config._message is not None:
                try:
                    await self.child_config._message.delete()
                    self.child_config._message = None
                except discord.HTTPException:
                    pass
            await self.child_config.close()
            self.child_config = None
        sectionui = self.child_config = section.configui(self.bot, self.guildid, self._channelid)
        await sectionui.run(self._original)

    async def config_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.config_menu
        menu.placeholder = t(_p(
            'ui:dashboard|menu:config|placeholder',
            "Open Configuration Panel"
        ))

        options = []
        for i, page in enumerate(self.pages):
            for j, section in enumerate(page):
                option = SelectOption(
                    label=section(self.bot, self.guildid).option_name,
                    value=str(i * 10 + j)
                )
                options.append(option)
        menu.options = options

    # ----- UI Control -----
    async def reload(self, *args):
        self._cached_pages.clear()
        await self.redraw()

    async def refresh(self):
        await super().refresh()
        await self.config_menu_refresh()
        self._layout = [
            (self.config_menu,),
            (self.prev_page_button, self.next_page_button)
        ]

    async def redraw(self, *args):
        await self.refresh()
        await self._original.edit_original_response(
            **self.current_page.edit_args,
            view=self
        )

    async def run(self, interaction: discord.Interaction):
        await self.refresh()

        self._original = interaction
        await interaction.response.send_message(**self.current_page.send_args, view=self)

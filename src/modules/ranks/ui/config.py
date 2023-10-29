import asyncio

import discord
from discord.ui.select import select, ChannelSelect, Select, SelectOption
from discord.ui.button import button, Button, ButtonStyle

from meta import LionBot
from wards import high_management_iward
from core.data import RankType

from utils.ui import ConfigUI, DashboardSection
from utils.lib import MessageArgs, error_embed

from ..settings import RankSettings
from .. import babel, logger
from .overview import RankOverviewUI

_p = babel._p


class RankConfigUI(ConfigUI):
    setting_classes = (
        RankSettings.RankStatType,
        RankSettings.DMRanks,
        RankSettings.RankChannel,
    )

    def __init__(self, bot: LionBot,
                 guildid: int, channelid: int, **kwargs):
        self.settings = bot.get_cog('RankCog').settings
        super().__init__(bot, guildid, channelid, **kwargs)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        passed = await high_management_iward(interaction)
        if passed:
            return True
        else:
            await interaction.response.send_message(
                embed=error_embed(
                    self.bot.translator.t(_p(
                        'ui:rankconfigui|check|not_permitted',
                        "You have insufficient server permissions to use this UI!"
                    ))
                ),
                ephemeral=True
            )
            return False

    # ----- UI Components -----

    # Button to summon Overview UI
    @button(label="OVERVIEW_PLACEHOLDER", style=ButtonStyle.blurple)
    async def overview_button(self, press: discord.Interaction, pressed: Button):
        """
        Display the Overview UI
        """
        overviewui = RankOverviewUI(self.bot, press.guild, press.user.id)
        self._slaves.append(overviewui)
        await overviewui.run(press)

    async def overview_button_refresh(self):
        self.overview_button.label = self.bot.translator.t(_p(
            'ui:rank_config|button:overview|label',
            "Edit Ranks"
        ))

    # Channel select menu
    @select(placeholder="TYPE_SELECT_PLACEHOLDER", min_values=1, max_values=1)
    async def type_menu(self, selection: discord.Interaction, selected: Select):
        await selection.response.defer(thinking=True)
        setting = self.instances[0]
        await setting.interaction_check(setting.parent_id, selection)
        value = selected.values[0]
        data = RankType((value,))
        setting.data = data
        await setting.write()
        await selection.delete_original_response()

    async def type_menu_refresh(self):
        t = self.bot.translator.t
        self.type_menu.placeholder = t(_p(
            'ui:rank_config|menu:types|placeholder',
            "Select Statistic Type"
        ))

        current = self.instances[0].data
        options = [
            SelectOption(
                label=t(_p(
                    'ui:rank_config|menu:types|option:voice',
                    "Voice Activity"
                )),
                value=RankType.VOICE.value[0],
                default=(current is RankType.VOICE)
            ),
            SelectOption(
                label=t(_p(
                    'ui:rank_config|menu:types|option:xp',
                    "XP Earned"
                )),
                value=RankType.XP.value[0],
                default=(current is RankType.XP)
            ),
            SelectOption(
                label=t(_p(
                    'ui:rank_config|menu:types|option:messages',
                    "Messages Sent"
                )),
                value=RankType.MESSAGE.value[0],
                default=(current is RankType.MESSAGE)
            ),
        ]
        self.type_menu.options = options

    @select(cls=ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            placeholder="CHANNEL_SELECT_PLACEHOLDER",
            min_values=0, max_values=1)
    async def channel_menu(self, selection: discord.Interaction, selected: ChannelSelect):
        await selection.response.defer()
        setting = self.instances[2]
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values[0] if selected.values else None
        await setting.write()

    async def channel_menu_refresh(self):
        self.channel_menu.placeholder = self.bot.translator.t(_p(
            'ui:rank_config|menu:channels|placeholder',
            "Select Rank Notification Channel"
        ))

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        title = t(_p(
            'ui:rank_config|embed|title',
            "Ranks Configuration Panel"
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
        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        self.instances = tuple(
            lguild.config.get(setting.setting_id) for setting in self.setting_classes
        )

    async def refresh_components(self):
        await asyncio.gather(
            self.overview_button_refresh(),
            self.channel_menu_refresh(),
            self.type_menu_refresh(),
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
        )
        self._layout = [
            (self.type_menu,),
            (self.channel_menu,),
            (self.overview_button, self.edit_button, self.reset_button, self.close_button)
        ]


class RankDashboard(DashboardSection):
    section_name = _p(
        'dash:rank|title',
        "Rank Configuration ({commands[admin config ranks]})",
    )
    _option_name = _p(
        "dash:rank|dropdown|placeholder",
        "Activity Rank Panel"
    )
    configui = RankConfigUI
    setting_classes = RankConfigUI.setting_classes

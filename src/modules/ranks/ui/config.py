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
    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Added secondary rank type toggle settings to the config UI
    setting_classes = (
        RankSettings.RankStatType,
        RankSettings.DMRanks,
        RankSettings.RankChannel,
        RankSettings.VoiceRanksEnabled,
        RankSettings.MsgRanksEnabled,
        RankSettings.XpRanksEnabled,
    )
    # --- END AI-MODIFIED ---

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

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Toggle buttons for secondary rank types
    @button(label="VOICE_TOGGLE_PLACEHOLDER", style=ButtonStyle.grey)
    async def voice_toggle(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        setting = self.instances[3]  # VoiceRanksEnabled
        setting.data = not setting.data
        await setting.write()

    async def voice_toggle_refresh(self):
        t = self.bot.translator.t
        setting = self.instances[3]  # VoiceRanksEnabled
        primary = self.instances[0].data  # RankStatType
        if primary is RankType.VOICE:
            self.voice_toggle.label = t(_p(
                'ui:rank_config|button:voice_toggle|label:primary',
                "Voice (Primary)"
            ))
            self.voice_toggle.style = ButtonStyle.blurple
            self.voice_toggle.disabled = True
        elif setting.data:
            self.voice_toggle.label = t(_p(
                'ui:rank_config|button:voice_toggle|label:enabled',
                "Voice: ON"
            ))
            self.voice_toggle.style = ButtonStyle.green
            self.voice_toggle.disabled = False
        else:
            self.voice_toggle.label = t(_p(
                'ui:rank_config|button:voice_toggle|label:disabled',
                "Voice: OFF"
            ))
            self.voice_toggle.style = ButtonStyle.grey
            self.voice_toggle.disabled = False

    @button(label="MSG_TOGGLE_PLACEHOLDER", style=ButtonStyle.grey)
    async def msg_toggle(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        setting = self.instances[4]  # MsgRanksEnabled
        setting.data = not setting.data
        await setting.write()

    async def msg_toggle_refresh(self):
        t = self.bot.translator.t
        setting = self.instances[4]  # MsgRanksEnabled
        primary = self.instances[0].data  # RankStatType
        if primary is RankType.MESSAGE:
            self.msg_toggle.label = t(_p(
                'ui:rank_config|button:msg_toggle|label:primary',
                "Messages (Primary)"
            ))
            self.msg_toggle.style = ButtonStyle.blurple
            self.msg_toggle.disabled = True
        elif setting.data:
            self.msg_toggle.label = t(_p(
                'ui:rank_config|button:msg_toggle|label:enabled',
                "Messages: ON"
            ))
            self.msg_toggle.style = ButtonStyle.green
            self.msg_toggle.disabled = False
        else:
            self.msg_toggle.label = t(_p(
                'ui:rank_config|button:msg_toggle|label:disabled',
                "Messages: OFF"
            ))
            self.msg_toggle.style = ButtonStyle.grey
            self.msg_toggle.disabled = False

    @button(label="XP_TOGGLE_PLACEHOLDER", style=ButtonStyle.grey)
    async def xp_toggle(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        setting = self.instances[5]  # XpRanksEnabled
        setting.data = not setting.data
        await setting.write()

    async def xp_toggle_refresh(self):
        t = self.bot.translator.t
        setting = self.instances[5]  # XpRanksEnabled
        primary = self.instances[0].data  # RankStatType
        if primary is RankType.XP:
            self.xp_toggle.label = t(_p(
                'ui:rank_config|button:xp_toggle|label:primary',
                "XP (Primary)"
            ))
            self.xp_toggle.style = ButtonStyle.blurple
            self.xp_toggle.disabled = True
        elif setting.data:
            self.xp_toggle.label = t(_p(
                'ui:rank_config|button:xp_toggle|label:enabled',
                "XP: ON"
            ))
            self.xp_toggle.style = ButtonStyle.green
            self.xp_toggle.disabled = False
        else:
            self.xp_toggle.label = t(_p(
                'ui:rank_config|button:xp_toggle|label:disabled',
                "XP: OFF"
            ))
            self.xp_toggle.style = ButtonStyle.grey
            self.xp_toggle.disabled = False
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-06-10) ---
    # Purpose: Fix NotNullViolation when pressing Reset on the rank config panel.
    #   The generic ConfigUI.reset_button writes `data = None` for every setting on
    #   the page, but voice_ranks_enabled / msg_ranks_enabled / xp_ranks_enabled are
    #   NOT NULL columns in guild_config, so the UPDATE failed with NotNullViolation
    #   and the panel errored with "Something went wrong!".
    #   This override resets those boolean toggles to their setting default (False)
    #   while still writing NULL for the nullable settings (rank_type, dm_ranks,
    #   rank_channel), which the settings framework reads back as their defaults.
    @button(label="RESET_PLACEHOLDER", style=ButtonStyle.red)
    async def reset_button(self, press: discord.Interaction, pressed: Button):
        """
        Reset the controlled settings, respecting NOT NULL toggle columns.
        """
        await press.response.defer()

        not_null_toggles = (
            RankSettings.VoiceRanksEnabled,
            RankSettings.MsgRanksEnabled,
            RankSettings.XpRanksEnabled,
        )
        for instance in self.page_instances:
            if isinstance(instance, not_null_toggles):
                instance.data = False
            else:
                instance.data = None
            await instance.write()
    # --- END AI-MODIFIED ---

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
        for setting in self.instances[:3]:
            embed.add_field(**setting.embed_field, inline=False)

        # --- AI-MODIFIED (2026-03-25) ---
        # Purpose: Show secondary rank type toggles section
        primary = self.instances[0].data
        primary_label = {
            RankType.VOICE: "Voice",
            RankType.XP: "XP",
            RankType.MESSAGE: "Messages",
        }.get(primary, "?")
        secondary_lines = [
            t(_p(
                'ui:rank_config|embed|field:secondary|header',
                "Primary type (**{primary}**) is always active. Toggle additional types below:"
            )).format(primary=primary_label)
        ]
        for setting in self.instances[3:]:
            status = "ON" if setting.data else "OFF"
            secondary_lines.append(f"- **{setting._display_name}**: {status}")
        embed.add_field(
            name=t(_p(
                'ui:rank_config|embed|field:secondary|name',
                "Secondary Rank Types"
            )),
            value='\n'.join(secondary_lines),
            inline=False
        )
        # --- END AI-MODIFIED ---

        args = MessageArgs(embed=embed)
        return args

    async def reload(self):
        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        self.instances = tuple(
            lguild.config.get(setting.setting_id) for setting in self.setting_classes
        )

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Include secondary rank type toggle buttons in layout
    async def refresh_components(self):
        await asyncio.gather(
            self.overview_button_refresh(),
            self.channel_menu_refresh(),
            self.type_menu_refresh(),
            self.voice_toggle_refresh(),
            self.msg_toggle_refresh(),
            self.xp_toggle_refresh(),
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
        )
        self._layout = [
            (self.type_menu,),
            (self.channel_menu,),
            (self.voice_toggle, self.msg_toggle, self.xp_toggle),
            (self.overview_button, self.edit_button, self.reset_button, self.close_button)
        ]
    # --- END AI-MODIFIED ---


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

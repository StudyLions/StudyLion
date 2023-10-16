"""
Configuration settings associated to the statistics module
"""
from typing import Optional
import asyncio
import discord
from discord.ui.select import select, Select, SelectOption, RoleSelect
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.text_input import TextInput, TextStyle

from settings import ListData, ModelData, InteractiveSetting
from settings.setting_types import RoleListSetting, EnumSetting, ListSetting, BoolSetting, TimestampSetting
from settings.groups import SettingGroup

from meta import conf, LionBot
from meta.context import ctx_bot
from meta.errors import UserInputError
from utils.lib import tabulate, utc_now
from utils.ui import ConfigUI, FastModal, error_handler_for, ModalRetryUI, DashboardSection
from utils.lib import MessageArgs
from core.data import CoreData
from core.lion_guild import VoiceMode
from babel.translator import ctx_translator
from wards import low_management_iward, high_management_iward

from . import babel
from .data import StatsData, StatisticType

_p = babel._p


class StatTypeSetting(EnumSetting):
    """
    ABC setting type mixin describing an available stat type.
    """
    _enum = StatisticType
    _outputs = {
        StatisticType.VOICE: _p('settype:stat|output:voice', "`Voice`"),
        StatisticType.TEXT: _p('settype:stat|output:text', "`Text`"),
        StatisticType.ANKI: _p('settype:stat|output:anki', "`Anki`"),
    }
    _input_formatted = {
        StatisticType.VOICE: _p('settype:stat|input_format:voice', "Voice"),
        StatisticType.TEXT: _p('settype:stat|input_format:text', "Text"),
        StatisticType.ANKI: _p('settype:stat|input_format:anki', "Anki"),
    }
    _input_patterns = {
        StatisticType.VOICE: _p('settype:stat|input_pattern:voice', "voice|study"),
        StatisticType.TEXT: _p('settype:stat|input_pattern:text', "text|messages"),
        StatisticType.ANKI: _p('settype:stat|input_pattern:anki', "anki"),
    }
    _accepts = _p(
        'settype:state|accepts',
        'Voice/Text/Anki'
    )


class StatisticsSettings(SettingGroup):
    class UserGlobalStats(ModelData, BoolSetting):
        """
        User setting, describing whether to display global statistics or not in servers.

        Exposed via a button on the `/stats` panel.
        """
        setting_id = 'show_global_stats'

        _display_name = _p('userset:show_global_stats', "global_stats")
        _desc = _p(
            'userset:show_global_stats|desc',
            "Whether displayed statistics include all your servers."
        )
        _long_desc = _p(
            'userset:show_global_stats|long_desc',
            "Whether statistics commands display combined stats for all servers or just your current server."
        )

        _model = CoreData.User
        _column = CoreData.User.show_global_stats.name

    class SeasonStart(ModelData, TimestampSetting):
        """
        Start of the statistics season,
        displayed on the leaderboard and used to determine activity ranks
        Time is assumed to be in set guild timezone (although supports +00 syntax)
        """
        setting_id = 'season_start'
        _set_cmd = 'admin config statistics'
        _write_ward = high_management_iward

        _display_name = _p('guildset:season_start', "season_start")
        _desc = _p(
            'guildset:season_start|desc',
            "Start of the current statistics season."
        )
        _long_desc = _p(
            'guildset:season_start|long_desc',
            "Activity ranks will be determined based on tracked activity since this time, "
            "and the leaderboard will display activity since this time by default. "
            "Unset to disable seasons and use all-time statistics instead.\n"
            "Provided dates and times are assumed to be in the guild `timezone`, so set this first!"
        )
        _accepts = _p(
            'guildset:season_start|accepts',
            "The season start time in the form YYYY-MM-DD HH:MM"
        )
        _notset_str = _p(
            'guildset:season_start|notset',
            "Not Set (Using all-time statistics)"
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.season_start.name

        @classmethod
        async def _timezone_from_id(cls, guildid, **kwargs):
            bot = ctx_bot.get()
            lguild = await bot.core.lions.fetch_guild(guildid)
            return lguild.timezone

        @classmethod
        async def _parse_string(cls, parent_id, string, **kwargs):
            parsed = await super()._parse_string(parent_id, string, **kwargs)
            if parsed is not None and parsed > utc_now():
                t = ctx_translator.get().t
                raise UserInputError(t(_p(
                    'guildset:season_start|parse|error:future_time',
                    "Provided season start time {timestamp} is in the future!"
                )).format(timestamp=f"<t:{int(parsed.timestamp())}>"))
            return parsed

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            bot = ctx_bot.get()
            value = self.value
            if value is not None:
                resp = t(_p(
                    'guildset:season_start|set_response|set',
                    "The leaderboard season and activity ranks will now count from {timestamp}. "
                    "Member ranks will update when they are next active.\n"
                    "Use {rank_cmd} and press **Refresh Member Ranks** to refresh all ranks immediately."
                )).format(
                    timestamp=self.formatted,
                    rank_cmd=bot.core.mention_cmd('ranks')
                )
            else:
                resp = t(_p(
                    'guildset:season_start|set_response|unset',
                    "The leaderboard and activity ranks will now count all-time statistics. "
                    "Member ranks will update when they are next active.\n"
                    "Use {rank_cmd} and press **Refresh Member Ranks** to refresh all ranks immediately."
                )).format(rank_cmd=bot.core.mention_cmd('ranks'))
            return resp

    class UnrankedRoles(ListData, RoleListSetting):
        """
        List of roles not displayed on the leaderboard
        """
        setting_id = 'unranked_roles'
        _write_ward = high_management_iward

        _display_name = _p('guildset:unranked_roles', "unranked_roles")
        _desc = _p(
            'guildset:unranked_roles|desc',
            "Roles to exclude from the leaderboards."
        )
        _long_desc = _p(
            'guildset:unranked_roles|long_desc',
            "When set, members with *any* of these roles will not appear on the /leaderboard ranking list."
        )
        _accepts = _p(
            'guildset:unranked_roles|accepts',
            "Comma separated list of unranked role names or ids."
        )
        _default = None

        _table_interface = StatsData.unranked_roles
        _id_column = 'guildid'
        _data_column = 'roleid'
        _order_column = 'roleid'

        _cache = {}

        @property
        def set_str(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:unranked_roles|set_using',
                "Role selector below."
            ))

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is not None:
                resp = t(_p(
                    'guildset:unranked_roles|set_response|set',
                    "Members of the following roles will not appear on the leaderboard: {roles}"
                )).format(
                    roles=self.formatted
                )
            else:
                resp = t(_p(
                    'guildset:unranked_roles|set_response|unset',
                    "You have cleared the unranked role list."
                ))
            return resp

    class VisibleStats(ListData, ListSetting, InteractiveSetting):
        """
        Which of the three stats (text, voice/study, anki) to enable in statistics views

        Default is determined by current guild mode
        """
        setting_id = 'visible_stats'
        _write_ward = high_management_iward

        _setting = StatTypeSetting

        _display_name = _p('guildset:visible_stats', "visible_stats")
        _desc = _p(
            'guildset:visible_stats|desc',
            "Which statistics will be visible in the statistics commands."
        )
        _long_desc = _p(
            'guildset:visible_stats|desc',
            "Choose which statistics types to display in the leaderboard and statistics commands."
        )
        _accepts = _p(
            'guildset:visible_stats|accepts',
            "Voice, Text, Anki"
        )
        # TODO: Format VOICE as STUDY when possible?

        _default = [
            StatisticType.VOICE,
            StatisticType.TEXT,
        ]

        _table_interface = StatsData.visible_statistics
        _id_column = 'guildid'
        _data_column = 'stat_type'
        _order_column = 'stat_type'

        _cache = {}

        @property
        def set_str(self):
            t = ctx_translator.get().t
            return t(_p(
                'guildset:visible_stats|set_using',
                "Option menu below."
            ))

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            resp = t(_p(
                'guildset:visible_stats|set_response',
                "Members will be able to view the following statistics types: {types}"
            )).format(types=self.formatted)
            return resp

    class DefaultStat(ModelData, StatTypeSetting):
        """
        Which of the three stats to display by default
        """
        setting_id = 'default_stat'
        _write_ward = high_management_iward

        _display_name = _p('guildset:default_stat', "default_stat")
        _desc = _p(
            'guildset:default_stat|desc',
            "Statistic type to display by default in setting dialogues."
        )
        _long_desc = _p(
            'guildset:default_stat|long_desc',
            "Which statistic type to display by default in setting dialogues."
        )


class StatisticsConfigUI(ConfigUI):
    setting_classes = (
        StatisticsSettings.SeasonStart,
        StatisticsSettings.UnrankedRoles,
        StatisticsSettings.VisibleStats
    )

    def __init__(self, bot: LionBot,
                 guildid: int, channelid: int, **kwargs):
        super().__init__(bot, guildid, channelid, **kwargs)
        self.settings = self.bot.get_cog('StatsCog').settings

    @select(cls=RoleSelect, placeholder='UNRANKED_ROLE_MENU', min_values=0, max_values=25)
    async def unranked_roles_menu(self, selection: discord.Interaction, selected):
        """
        Selection menu for the "unranked_roles" setting.
        """
        await selection.response.defer(thinking=True)
        setting = self.instances[1]
        await setting.interaction_check(setting.parent_id, selection)
        setting.value = selected.values
        await setting.write()
        # Don't need to refresh due to instance hooks
        # await self.refresh(thinking=selection)
        await selection.delete_original_response()

    async def unranked_roles_menu_refresh(self):
        t = self.bot.translator.t
        self.unranked_roles_menu.placeholder = t(_p(
            'ui:statistics_config|menu:unranked_roles|placeholder',
            "Select Unranked Roles"
        ))

    @select(placeholder="STAT_TYPE_MENU", min_values=1, max_values=3)
    async def stat_type_menu(self, selection: discord.Interaction, selected):
        """
        Selection menu for the "visible_stats" setting.
        """
        await selection.response.defer(thinking=True)
        setting = self.instances[2]
        await setting.interaction_check(setting.parent_id, selection)
        data = [StatisticType((value,)) for value in selected.values]
        setting.data = data
        await setting.write()
        await selection.delete_original_response()

    async def stat_type_menu_refresh(self):
        t = self.bot.translator.t
        setting = self.instances[2]
        value = setting.value

        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        if lguild.guild_mode.voice is VoiceMode.VOICE:
            voice_label = t(_p(
                'ui:statistics_config|menu:visible_stats|item:voice|mode:voice',
                "Voice Activity"
            ))
        else:
            voice_label = t(_p(
                'ui:statistics_config|menu:visible_stats|item:voice|mode:study',
                "Study Statistics"
            ))
        voice_option = SelectOption(
            label=voice_label,
            value=StatisticType.VOICE.value[0],
            default=(StatisticType.VOICE in value)
        )
        text_option = SelectOption(
            label=t(_p(
                'ui:statistics_config|menu:visible_stats|item:text',
                "Message Activity"
            )),
            value=StatisticType.TEXT.value[0],
            default=(StatisticType.TEXT in value)
        )
        anki_option = SelectOption(
            label=t(_p(
                'ui:statistics_config|menu:visible_stats|item:anki',
                "Anki Reviews"
            )),
            value=StatisticType.ANKI.value[0],
            default=(StatisticType.ANKI in value)
        )
        self.stat_type_menu.options = [
            voice_option, text_option, anki_option
        ]

        self.stat_type_menu.placeholder = t(_p(
            'ui:statistics_config|menu:visible_stats|placeholder',
            "Select Visible Statistics"
        ))

    async def refresh_components(self):
        await asyncio.gather(
            self.edit_button_refresh(),
            self.close_button_refresh(),
            self.reset_button_refresh(),
            self.unranked_roles_menu_refresh(),
            self.stat_type_menu_refresh(),
        )
        self._layout = [
            (self.unranked_roles_menu,),
            (self.stat_type_menu,),
            (self.edit_button, self.reset_button, self.close_button)
        ]

    async def make_message(self):
        t = self.bot.translator.t
        title = t(_p(
            'ui:statistics_config|embed|title',
            "Statistics Configuration Panel"
        ))
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=title
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


class StatisticsDashboard(DashboardSection):
    section_name = _p(
        'dash:stats|title',
        "Activity Statistics Configuration ({commands[admin config statistics]})"
    )
    _option_name = _p(
        "dash:stats|dropdown|placeholder",
        "Activity Statistics Panel"
    )
    configui = StatisticsConfigUI
    setting_classes = StatisticsConfigUI.setting_classes

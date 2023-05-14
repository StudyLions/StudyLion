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
from utils.lib import tabulate
from utils.ui import ConfigUI, FastModal, error_handler_for, ModalRetryUI
from utils.lib import MessageArgs
from core.data import CoreData
from core.lion_guild import VoiceMode
from babel.translator import ctx_translator

from . import babel
from .data import StatsData, StatisticType

_p = babel._p


class StatTypeSetting(EnumSetting):
    """
    ABC setting type mixin describing an available stat type.
    """
    _enum = StatisticType
    _outputs = {
        StatisticType.VOICE: '`Voice`',
        StatisticType.TEXT: '`Text`',
        StatisticType.ANKI: '`Anki`'
    }
    _inputs = {
        'voice': StatisticType.VOICE,
        'study': StatisticType.VOICE,
        'text': StatisticType.TEXT,
        'anki': StatisticType.ANKI
    }


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

        _display_name = _p('guildset:season_start', "season_start")
        _desc = _p(
            'guildset:season_start|desc',
            "Start of the current statistics season."
        )
        _long_desc = _p(
            'guildset:season_start|long_desc',
            "Activity ranks will be determined based on tracked activity since this time, "
            "and the leaderboard will display activity since this time by default. "
            "Unset to disable seasons and use all-time statistics instead."
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.season_start.name
        # TODO: Offer to update badge ranks when this changes?
        # TODO: Don't allow future times?

        @classmethod
        async def _timezone_from_id(cls, guildid, **kwargs):
            bot = ctx_bot.get()
            lguild = await bot.core.lions.fetch_guild(guildid)
            return lguild.timezone

    class UnrankedRoles(ListData, RoleListSetting):
        """
        List of roles not displayed on the leaderboard
        """
        setting_id = 'unranked_roles'

        _display_name = _p('guildset:unranked_roles', "unranked_roles")
        _desc = _p(
            'guildset:unranked_roles|desc',
            "Roles to exclude from the leaderboards."
        )
        _long_desc = _p(
            'guildset:unranked_roles|long_desc',
            "When set, members with *any* of these roles will not appear on the /leaderboard ranking list."
        )
        _default = None

        _table_interface = StatsData.unranked_roles
        _id_column = 'guildid'
        _data_column = 'roleid'
        _order_column = 'roleid'

        _cache = {}

        @property
        def set_str(self):
            return "Role selector below"

    class VisibleStats(ListData, ListSetting, InteractiveSetting):
        """
        Which of the three stats (text, voice/study, anki) to enable in statistics views

        Default is determined by current guild mode
        """
        setting_id = 'visible_stats'

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

    class DefaultStat(ModelData, StatTypeSetting):
        """
        Which of the three stats to display by default
        """
        setting_id = 'default_stat'

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

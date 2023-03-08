from settings import ModelData
from settings.setting_types import BoolSetting
from settings.groups import SettingGroup

from core.data import CoreData

from . import babel

_p = babel._p


class StatsSettings(SettingGroup):
    class UserGlobalStats(ModelData, BoolSetting):
        """
        User setting, describing whether to display global statistics or not in servers.

        Exposed via a button on the `/stats` panel.
        """
        setting_id = 'show_global_stats'

        _display_name = _p('userset:show_global_stats', "global_stats")
        _desc = _p(
            'userset:show_global_stats',
            "Whether statistics commands display combined stats for all servers or just your current server."
        )

        _model = CoreData.User
        _column = CoreData.User.show_global_stats.name

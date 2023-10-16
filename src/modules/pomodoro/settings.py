from settings import ModelData
from settings.groups import SettingGroup
from settings.setting_types import ChannelSetting

from core.data import CoreData
from babel.translator import ctx_translator
from wards import low_management_iward

from . import babel

_p = babel._p


class TimerSettings(SettingGroup):
    class PomodoroChannel(ModelData, ChannelSetting):
        setting_id = 'pomodoro_channel'
        _event = 'guildset_pomodoro_channel'
        _set_cmd = 'config pomodoro'
        _write_ward = low_management_iward

        _display_name = _p('guildset:pomodoro_channel', "pomodoro_channel")
        _desc = _p(
            'guildset:pomodoro_channel|desc',
            "Default central notification channel for pomodoro timers."
        )
        _long_desc = _p(
            'guildset:pomodoro_channel|long_desc',
            "Pomodoro timers which do not have a custom notification channel set will send "
            "timer notifications in this channel. "
            "If this setting is not set, pomodoro notifications will default to the "
            "timer voice channel itself."
        )
        _notset_str = _p(
            'guildset:pomodoro_channel|formatted|notset',
            "Not Set (Will use timer voice channel.)"
        )
        _accepts = _p(
            'guildset:pomodoro_channel|accepts',
            "Timer notification channel name or id."
        )

        _model = CoreData.Guild
        _column = CoreData.Guild.pomodoro_channel.name
        _allow_object = False

        @property
        def update_message(self) -> str:
            t = ctx_translator.get().t
            value = self.value
            if value is not None:
                resp = t(_p(
                    'guildset:pomodoro_channel|set_response|set',
                    "Pomodoro timer notifications will now default to {channel}"
                )).format(channel=value.mention)
            else:
                resp = t(_p(
                    'guildset:pomodoro_channel|set_response|unset',
                    "Pomodoro timer notifications will now default to their voice channel."
                ))
            return resp

        @property
        def set_str(self) -> str:
            cmdstr = super().set_str
            t = ctx_translator.get().t
            return t(_p(
                'guildset:pomdoro_channel|set_using',
                "{cmd} or channel selector below."
            )).format(cmd=cmdstr)

from settings import ModelData
from settings.groups import SettingGroup
from settings.setting_types import ChannelSetting

from core.data import CoreData
from babel.translator import ctx_translator

from . import babel

_p = babel._p


class TimerSettings(SettingGroup):
    class PomodoroChannel(ModelData, ChannelSetting):
        setting_id = 'pomodoro_channel'
        _event = 'guildset_pomodoro_channel'

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
        _model = CoreData.Guild
        _column = CoreData.Guild.pomodoro_channel.name

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

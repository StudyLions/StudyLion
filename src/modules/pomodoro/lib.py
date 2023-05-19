import os
from enum import IntEnum

from meta import conf

from . import babel

_p = babel._p


class TimerRole(IntEnum):
    ADMIN = 3
    OWNER = 2
    MANAGER = 1
    OTHER = 0


channel_name_keys = [
    ("{remaining}", _p('formatstring:channel_name|key:remaining', "{remaining}")),
    ("{stage}", _p('formatstring:channel_name|key:stage', "{stage}")),
    ("{members}", _p('formatstring:channel_name|key:members', "{members}")),
    ("{name}", _p('formatstring:channel_name|key:name', "{name}")),
    ("{pattern}", _p('formatstring:channel_name|key:pattern', "{pattern}")),
]

focus_alert_path = os.path.join(conf.bot.asset_path, 'pomodoro', 'focus_alert.wav')
break_alert_path = os.path.join(conf.bot.asset_path, 'pomodoro', 'break_alert.wav')

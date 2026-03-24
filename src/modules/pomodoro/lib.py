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

# --- AI-MODIFIED (2026-03-17) ---
# Purpose: Website URL constants for link buttons in Discord UI.
# Imports central config-driven constant so test bot -> staging, live bot -> lionbot.org.
from meta import WEBSITE_URL as WEBSITE_BASE_URL
FOCUS_MODE_URL = f"{WEBSITE_BASE_URL}/dashboard/session/focus"
DASHBOARD_SESSION_URL = f"{WEBSITE_BASE_URL}/dashboard/session"

# Pomodoro presets: name -> (focus_minutes, break_minutes)
POMODORO_PRESETS = {
    'classic': (25, 5),
    'long_focus': (50, 10),
    'short_sprint': (15, 3),
    'lecture': (45, 10),
}

BREAK_TIPS = [
    "Stand up and stretch your shoulders",
    "Drink a glass of water",
    "Look at something 20 feet away for 20 seconds",
    "Roll your neck gently side to side",
    "Take 3 deep breaths",
    "Wiggle your fingers and toes",
    "Close your eyes and relax your jaw",
    "Walk around the room for a moment",
    "Splash cold water on your face",
    "Do a quick shoulder roll",
    "Stretch your wrists and forearms",
    "Take a moment to appreciate your progress",
    "Straighten your posture",
    "Give your eyes a break from the screen",
    "Hydrate \u2014 your brain needs water to focus",
]
# --- END AI-MODIFIED ---

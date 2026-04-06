# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Data registry for screen share enforcement tables
# ============================================================
from data import Registry, Table


class ScreenData(Registry):
    screen_channels = Table('screen_channels')
    screen_exempt_roles = Table('screen_exempt_roles')
    screen_blacklist_durations = Table('screenban_durations')

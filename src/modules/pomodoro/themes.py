# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-18
# Purpose: Premium timer card theme definitions and color palettes
# ============================================================

from typing import NamedTuple, Optional
from datetime import datetime


class TimerTheme(NamedTuple):
    """Defines the visual properties of a premium timer card theme."""
    name: str
    display_name: str
    focus_color: tuple  # RGB for focus stage main color
    break_color: tuple  # RGB for break stage main color
    particle_focus_color: tuple  # RGB for focus particles
    particle_break_color: tuple  # RGB for break particles
    bg_tint: Optional[tuple]  # Optional RGB tint applied to background
    stage_text_color: tuple  # RGB for stage label text
    countdown_color_override: Optional[tuple]  # If set, overrides countdown text color
    description: str  # Short description for theme picker UI


TIMER_THEMES: dict[str, TimerTheme] = {
    'default': TimerTheme(
        name='default',
        display_name='Classic',
        focus_color=(221, 178, 29),
        break_color=(120, 183, 239),
        particle_focus_color=(221, 178, 29),
        particle_break_color=(120, 183, 239),
        bg_tint=None,
        stage_text_color=(255, 255, 255),
        countdown_color_override=None,
        description='Classic gold & blue',
    ),
    'neon': TimerTheme(
        name='neon',
        display_name='Neon',
        focus_color=(0, 255, 157),
        break_color=(255, 0, 230),
        particle_focus_color=(0, 255, 200),
        particle_break_color=(255, 50, 255),
        bg_tint=(10, 0, 20),
        stage_text_color=(200, 255, 220),
        countdown_color_override=(0, 255, 157),
        description='Cyberpunk neon glow',
    ),
    'forest': TimerTheme(
        name='forest',
        display_name='Forest',
        focus_color=(76, 175, 80),
        break_color=(139, 195, 74),
        particle_focus_color=(100, 200, 100),
        particle_break_color=(180, 220, 100),
        bg_tint=(5, 15, 5),
        stage_text_color=(200, 240, 200),
        countdown_color_override=None,
        description='Woodland serenity',
    ),
    'ocean': TimerTheme(
        name='ocean',
        display_name='Ocean',
        focus_color=(0, 150, 200),
        break_color=(0, 188, 212),
        particle_focus_color=(0, 180, 220),
        particle_break_color=(100, 220, 255),
        bg_tint=(0, 5, 15),
        stage_text_color=(180, 230, 255),
        countdown_color_override=None,
        description='Deep ocean depths',
    ),
    'sunset': TimerTheme(
        name='sunset',
        display_name='Sunset',
        focus_color=(255, 120, 50),
        break_color=(255, 160, 120),
        particle_focus_color=(255, 140, 70),
        particle_break_color=(255, 180, 150),
        bg_tint=(15, 5, 0),
        stage_text_color=(255, 220, 200),
        countdown_color_override=(255, 140, 60),
        description='Golden sunset warmth',
    ),
    'midnight': TimerTheme(
        name='midnight',
        display_name='Midnight',
        focus_color=(138, 43, 226),
        break_color=(100, 100, 200),
        particle_focus_color=(160, 80, 255),
        particle_break_color=(120, 120, 220),
        bg_tint=(10, 0, 15),
        stage_text_color=(200, 180, 255),
        countdown_color_override=None,
        description='Starlit midnight',
    ),
    'sakura': TimerTheme(
        name='sakura',
        display_name='Sakura',
        focus_color=(255, 150, 180),
        break_color=(255, 182, 193),
        particle_focus_color=(255, 170, 200),
        particle_break_color=(255, 200, 220),
        bg_tint=(15, 5, 8),
        stage_text_color=(255, 220, 230),
        countdown_color_override=None,
        description='Cherry blossom dreams',
    ),
    'retro': TimerTheme(
        name='retro',
        display_name='Retro',
        focus_color=(255, 176, 0),
        break_color=(0, 255, 100),
        particle_focus_color=(255, 200, 50),
        particle_break_color=(50, 255, 120),
        bg_tint=(8, 5, 0),
        stage_text_color=(255, 200, 50),
        countdown_color_override=(255, 176, 0),
        description='Retro terminal',
    ),
    'minimal': TimerTheme(
        name='minimal',
        display_name='Minimal',
        focus_color=(200, 200, 200),
        break_color=(160, 160, 160),
        particle_focus_color=(220, 220, 220),
        particle_break_color=(180, 180, 180),
        bg_tint=None,
        stage_text_color=(230, 230, 230),
        countdown_color_override=(220, 220, 220),
        description='Clean & minimal',
    ),
}

# Month-to-theme mapping for the seasonal theme
_SEASONAL_MAP = {
    12: 'midnight', 1: 'midnight', 2: 'midnight',   # Winter
    3: 'sakura', 4: 'sakura', 5: 'sakura',           # Spring
    6: 'sunset', 7: 'sunset', 8: 'sunset',           # Summer
    9: 'forest', 10: 'forest', 11: 'forest',         # Autumn
}


def get_seasonal_theme() -> TimerTheme:
    """Returns the appropriate theme based on the current month."""
    month = datetime.utcnow().month
    theme_name = _SEASONAL_MAP.get(month, 'default')
    return TIMER_THEMES[theme_name]


def get_theme(theme_name: str) -> TimerTheme:
    """Returns the TimerTheme for the given name.

    Falls back to 'default' if the name is not recognized.
    The special name 'seasonal' resolves to a month-appropriate theme.
    """
    if theme_name == 'seasonal':
        return get_seasonal_theme()
    return TIMER_THEMES.get(theme_name, TIMER_THEMES['default'])


def get_all_themes() -> dict[str, TimerTheme]:
    """Returns the full TIMER_THEMES dict (for the website theme picker)."""
    return TIMER_THEMES


def get_theme_names() -> list[str]:
    """Returns list of available theme names, including 'seasonal'."""
    return list(TIMER_THEMES.keys()) + ['seasonal']

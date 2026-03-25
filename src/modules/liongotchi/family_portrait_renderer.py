# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-24
# Purpose: LionGotchi Family Portrait Renderer
#          Composites all family member pet sprites into a
#          single themed animated GIF with stats panel
# ============================================================
import io
import math
import logging
import random
from typing import Optional
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .renderer import (
    PetState, compose_pet_sprite, _load_asset, _get_font, _draw_outlined_text,
    ANIMATION_FRAMES, GIF_FRAME_DURATION, STROKE_OFFSETS,
)

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / 'assets'

# --------------- canvas & layout ---------------
CANVAS_W = 500
CANVAS_H = 300
UPSCALE = 3
OUT_W = CANVAS_W * UPSCALE
OUT_H = CANVAS_H * UPSCALE

HEADER_H = 48
DIV_H = 3
SCENE_Y = HEADER_H + DIV_H
SCENE_H = 192
STATS_DIV_Y = SCENE_Y + SCENE_H
STATS_Y = STATS_DIV_Y + DIV_H
STATS_H = CANVAS_H - STATS_Y

GROUND_H = 30

# --------------- role config ---------------
ROLE_BADGE = {
    'LEADER': ('\u2654', (255, 215, 0)),
    'ADMIN': ('\u2605', (230, 126, 34)),
    'MODERATOR': ('\u2666', (52, 152, 219)),
    'MEMBER': ('\u2022', (180, 180, 180)),
}

# --------------- themes ---------------
DEFAULT_THEME = {
    "bg_color": [30, 30, 50],
    "bg_gradient_end": [50, 40, 80],
    "accent_color": [88, 101, 242],
    "text_color": [255, 255, 255],
    "border_color": [255, 215, 0],
    "border_width": 2,
    "glow_color": [88, 101, 242, 60],
    "glow_radius": 4,
    "ground_color": [40, 35, 65],
    "ground_highlight": [60, 50, 90],
}

PRESET_THEMES = {
    "royal_gold": {
        "bg_color": [25, 20, 15],
        "bg_gradient_end": [50, 35, 15],
        "accent_color": [180, 140, 40],
        "text_color": [255, 245, 220],
        "border_color": [255, 215, 0],
        "border_width": 3,
        "glow_color": [255, 180, 50, 70],
        "glow_radius": 5,
        "ground_color": [55, 40, 15],
        "ground_highlight": [80, 60, 25],
    },
    "ocean_blue": {
        "bg_color": [10, 20, 50],
        "bg_gradient_end": [20, 50, 80],
        "accent_color": [30, 144, 200],
        "text_color": [220, 240, 255],
        "border_color": [70, 200, 230],
        "border_width": 2,
        "glow_color": [50, 180, 220, 60],
        "glow_radius": 5,
        "ground_color": [15, 40, 70],
        "ground_highlight": [25, 60, 100],
    },
    "forest_green": {
        "bg_color": [15, 30, 15],
        "bg_gradient_end": [25, 55, 30],
        "accent_color": [34, 139, 34],
        "text_color": [220, 255, 220],
        "border_color": [50, 205, 50],
        "border_width": 2,
        "glow_color": [50, 180, 80, 60],
        "glow_radius": 4,
        "ground_color": [25, 50, 20],
        "ground_highlight": [40, 75, 30],
    },
    "midnight": {
        "bg_color": [8, 8, 16],
        "bg_gradient_end": [20, 15, 35],
        "accent_color": [100, 100, 130],
        "text_color": [200, 200, 220],
        "border_color": [180, 180, 200],
        "border_width": 2,
        "glow_color": [120, 100, 180, 50],
        "glow_radius": 6,
        "ground_color": [18, 15, 30],
        "ground_highlight": [30, 25, 50],
    },
    "sunset": {
        "bg_color": [60, 20, 40],
        "bg_gradient_end": [80, 40, 20],
        "accent_color": [230, 100, 60],
        "text_color": [255, 240, 220],
        "border_color": [255, 140, 80],
        "border_width": 2,
        "glow_color": [255, 120, 60, 60],
        "glow_radius": 5,
        "ground_color": [70, 30, 20],
        "ground_highlight": [100, 45, 30],
    },
    "cherry_blossom": {
        "bg_color": [40, 15, 30],
        "bg_gradient_end": [60, 20, 50],
        "accent_color": [200, 60, 120],
        "text_color": [255, 220, 240],
        "border_color": [255, 100, 160],
        "border_width": 2,
        "glow_color": [255, 100, 150, 60],
        "glow_radius": 5,
        "ground_color": [55, 20, 40],
        "ground_highlight": [80, 30, 55],
    },
}


class FamilyPortraitState:
    def __init__(
        self,
        family_name: str = "Family",
        family_level: int = 1,
        family_xp: int = 0,
        family_gold: int = 0,
        member_count: int = 0,
        max_members: int = 10,
        description: str = "",
        icon_url: str = "",
        member_sprites: list = None,
        theme: dict = None,
    ):
        self.family_name = family_name
        self.family_level = family_level
        self.family_xp = family_xp
        self.family_gold = family_gold
        self.member_count = member_count
        self.max_members = max_members
        self.description = description
        self.icon_url = icon_url
        self.member_sprites = member_sprites or []
        self.theme = {**DEFAULT_THEME, **(theme or {})}


# =============== helpers ===============

def _t(theme: dict, key: str):
    val = theme.get(key, DEFAULT_THEME.get(key, [255, 255, 255]))
    return tuple(val) if isinstance(val, list) else val


# --- AI-MODIFIED (2026-03-24) ---
# Purpose: Unified with website familyLevelThreshold formula (was level²*1000)
def _xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    return int(500 * ((level - 1) ** 1.8))
# --- END AI-MODIFIED ---


# =============== background & frame ===============

def _draw_gradient_bg(canvas: Image.Image, theme: dict):
    c1 = _t(theme, 'bg_color')
    c2 = _t(theme, 'bg_gradient_end')
    draw = ImageDraw.Draw(canvas)
    for y in range(CANVAS_H):
        t = y / max(1, CANVAS_H - 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(0, y), (CANVAS_W - 1, y)], fill=(r, g, b))


def _draw_ground_plane(canvas: Image.Image, theme: dict):
    """Gradient ground plane at the bottom of the scene so pets feel anchored."""
    gc = _t(theme, 'ground_color')
    gh = _t(theme, 'ground_highlight')
    draw = ImageDraw.Draw(canvas)
    ground_top = STATS_DIV_Y - GROUND_H
    for y in range(GROUND_H):
        t = y / max(1, GROUND_H - 1)
        r = int(gh[0] + (gc[0] - gh[0]) * t)
        g = int(gh[1] + (gc[1] - gh[1]) * t)
        b = int(gh[2] + (gc[2] - gh[2]) * t)
        alpha = int(60 + 140 * t)
        draw.line([(0, ground_top + y), (CANVAS_W - 1, ground_top + y)],
                  fill=(r, g, b, alpha))


def _draw_border(draw: ImageDraw.ImageDraw, theme: dict):
    bw = theme.get('border_width', 2)
    color = _t(theme, 'border_color')
    for i in range(bw):
        draw.rectangle(
            [i, i, CANVAS_W - 1 - i, CANVAS_H - 1 - i],
            outline=(*color, 200)
        )


def _draw_glow_border(canvas: Image.Image, theme: dict):
    gc = _t(theme, 'glow_color')
    gr = theme.get('glow_radius', 4)
    if len(gc) < 4 or gc[3] == 0 or gr < 1:
        return
    draw = ImageDraw.Draw(canvas)
    for d in range(gr, 0, -1):
        alpha = int(gc[3] * (1 - d / (gr + 1)))
        draw.rectangle(
            [-d, -d, CANVAS_W - 1 + d, CANVAS_H - 1 + d],
            outline=(*gc[:3], alpha)
        )


# =============== header ===============

def _draw_crest(draw: ImageDraw.ImageDraw, x: int, y: int, theme: dict):
    """Draw a 12x14 pixel shield crest."""
    accent = _t(theme, 'accent_color')
    border = _t(theme, 'border_color')
    bc = (*border[:3], 255)
    ac = (*accent[:3], 220)

    shield = [
        (x + 1, y), (x + 2, y), (x + 3, y), (x + 4, y), (x + 5, y),
        (x + 6, y), (x + 7, y), (x + 8, y), (x + 9, y), (x + 10, y),
        (x, y + 1), (x + 11, y + 1),
        (x, y + 2), (x + 11, y + 2),
        (x, y + 3), (x + 11, y + 3),
        (x, y + 4), (x + 11, y + 4),
        (x, y + 5), (x + 11, y + 5),
        (x, y + 6), (x + 11, y + 6),
        (x + 1, y + 7), (x + 10, y + 7),
        (x + 1, y + 8), (x + 10, y + 8),
        (x + 2, y + 9), (x + 9, y + 9),
        (x + 3, y + 10), (x + 8, y + 10),
        (x + 4, y + 11), (x + 7, y + 11),
        (x + 5, y + 12), (x + 6, y + 12),
    ]
    for px, py in shield:
        draw.point((px, py), fill=bc)

    fill_rows = [
        (y + 1, x + 1, x + 10),
        (y + 2, x + 1, x + 10),
        (y + 3, x + 1, x + 10),
        (y + 4, x + 1, x + 10),
        (y + 5, x + 1, x + 10),
        (y + 6, x + 1, x + 10),
        (y + 7, x + 2, x + 9),
        (y + 8, x + 2, x + 9),
        (y + 9, x + 3, x + 8),
        (y + 10, x + 4, x + 7),
        (y + 11, x + 5, x + 6),
    ]
    for ry, rx1, rx2 in fill_rows:
        draw.line([(rx1, ry), (rx2, ry)], fill=ac)

    star_c = (*border[:3], 255)
    cx, cy = x + 5, y + 5
    for pt in [(cx, cy - 2), (cx - 1, cy - 1), (cx, cy - 1), (cx + 1, cy - 1),
               (cx - 2, cy), (cx - 1, cy), (cx, cy), (cx + 1, cy), (cx + 2, cy),
               (cx - 1, cy + 1), (cx, cy + 1), (cx + 1, cy + 1),
               (cx, cy + 2)]:
        draw.point(pt, fill=star_c)


def _draw_header(canvas: Image.Image, state: FamilyPortraitState):
    theme = state.theme
    accent = _t(theme, 'accent_color')
    text_color = _t(theme, 'text_color')
    draw = ImageDraw.Draw(canvas)

    bw = theme.get('border_width', 2)
    pad = bw + 8
    draw.rectangle([bw, bw, CANVAS_W - 1 - bw, HEADER_H - 1],
                   fill=(*accent, 160))

    _draw_crest(draw, pad, 6, theme)

    name_text = state.family_name.upper()
    name_x = pad + 16

    lv_text = f"Lv. {state.family_level}"
    font_level = _get_font(16)
    lv_w = int(draw.textlength(lv_text, font=font_level))
    lv_x = CANVAS_W - lv_w - pad

    max_name_w = lv_x - name_x - 12
    font_name = _get_font(20)
    name_w = int(draw.textlength(name_text, font=font_name))
    if name_w > max_name_w:
        font_name = _get_font(16)
        name_w = int(draw.textlength(name_text, font=font_name))
    if name_w > max_name_w:
        font_name = _get_font(14)
        name_w = int(draw.textlength(name_text, font=font_name))
        while name_w > max_name_w and len(name_text) > 8:
            name_text = name_text[:-4] + "..."
            name_w = int(draw.textlength(name_text, font=font_name))

    _draw_outlined_text(draw, (name_x, 4), name_text, font=font_name,
                        fill=text_color, outline=(0, 0, 0))

    _draw_outlined_text(draw, (lv_x, 5), lv_text,
                        font=font_level, fill=text_color, outline=(0, 0, 0))

    if state.description:
        font_desc = _get_font(10)
        desc = state.description[:50]
        desc_w = int(draw.textlength(desc, font=font_desc))
        if desc_w > CANVAS_W - pad * 2 - 16:
            while desc_w > CANVAS_W - pad * 2 - 16 and len(desc) > 10:
                desc = desc[:-4] + "..."
                desc_w = int(draw.textlength(desc, font=font_desc))
        _draw_outlined_text(draw, (name_x, 28), desc, font=font_desc,
                            fill=(*text_color[:3], 180), outline=(0, 0, 0))


# =============== dividers ===============

def _draw_divider(canvas: Image.Image, y: int, theme: dict):
    accent = _t(theme, 'accent_color')
    border = _t(theme, 'border_color')
    bw = theme.get('border_width', 2)
    draw = ImageDraw.Draw(canvas)

    line_y = y + 1
    draw.line([(bw + 2, line_y), (CANVAS_W - bw - 3, line_y)],
              fill=(*accent[:3], 120), width=1)

    cx = CANVAS_W // 2
    diamond_pts = [(cx, line_y - 2), (cx + 3, line_y), (cx, line_y + 2), (cx - 3, line_y)]
    draw.polygon(diamond_pts, fill=(*border[:3], 220))

    for off in [30, 60, 90, 120, 150, 180, 210]:
        for sign in [-1, 1]:
            dx = cx + sign * off
            if bw + 4 < dx < CANVAS_W - bw - 4:
                if off % 60 == 0:
                    sm = [(dx, line_y - 1), (dx + 1, line_y), (dx, line_y + 1), (dx - 1, line_y)]
                    draw.polygon(sm, fill=(*border[:3], 100))
                else:
                    draw.point((dx, line_y), fill=(*border[:3], 80))


# =============== sparkles ===============

_sparkle_seed = None
_sparkle_positions = []

def _init_sparkles(count=16):
    global _sparkle_seed, _sparkle_positions
    _sparkle_positions = []
    rng = random.Random(42)
    for _ in range(count):
        _sparkle_positions.append({
            'x': rng.randint(10, CANVAS_W - 10),
            'y': rng.randint(SCENE_Y + 5, STATS_DIV_Y - GROUND_H - 10),
            'phase_off': rng.random() * 6.28,
            'size': rng.choice([1, 1, 2, 2, 3]),
            'speed': 0.5 + rng.random() * 1.5,
        })

_init_sparkles()


def _draw_sparkles(canvas: Image.Image, frame_idx: int, theme: dict):
    border = _t(theme, 'border_color')
    accent = _t(theme, 'accent_color')
    draw = ImageDraw.Draw(canvas)
    TWO_PI = 2 * math.pi

    for i, sp in enumerate(_sparkle_positions):
        phase = (frame_idx * sp['speed'] / ANIMATION_FRAMES * TWO_PI) + sp['phase_off']
        brightness = max(0.0, math.sin(phase))
        if brightness < 0.1:
            continue

        alpha = int(100 * brightness)
        col = border if i % 3 == 0 else accent
        c = (*col[:3], alpha)
        x, y = sp['x'], sp['y']
        sz = sp['size']

        draw.point((x, y), fill=(*col[:3], min(255, alpha + 60)))

        if sz >= 2:
            draw.point((x + 1, y), fill=c)
            draw.point((x - 1, y), fill=c)
            draw.point((x, y + 1), fill=c)
            draw.point((x, y - 1), fill=c)

        if sz >= 3:
            c2 = (*col[:3], alpha // 2)
            draw.point((x + 2, y), fill=c2)
            draw.point((x - 2, y), fill=c2)
            draw.point((x, y + 2), fill=c2)
            draw.point((x, y - 2), fill=c2)


# =============== pet decorations ===============

def _draw_shadow(draw: ImageDraw.ImageDraw, cx: int, cy: int, w: int):
    hw = w // 2
    hh = max(3, w // 6)
    for ring in range(3):
        alpha = 40 - ring * 12
        if alpha <= 0:
            break
        draw.ellipse(
            [cx - hw - ring, cy - hh + ring, cx + hw + ring, cy + hh - ring],
            fill=(0, 0, 0, max(0, alpha))
        )


def _draw_leader_glow(canvas: Image.Image, cx: int, cy: int, size: int,
                      theme: dict, frame_idx: int):
    border = _t(theme, 'border_color')
    phase = (frame_idx % ANIMATION_FRAMES) / ANIMATION_FRAMES
    pulse = 0.6 + 0.4 * math.sin(2 * math.pi * phase)

    glow = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)

    for ring in range(5, 0, -1):
        r = int(size * 0.5 + ring * 5)
        alpha = int(30 * pulse * (6 - ring))
        gd.ellipse([cx - r, cy - r, cx + r, cy + r],
                   fill=(*border[:3], min(255, alpha)))

    canvas.alpha_composite(glow)


def _draw_crown(draw: ImageDraw.ImageDraw, cx: int, y: int, theme: dict):
    """15x9 pixel crown with gems."""
    c = _t(theme, 'border_color')
    col = (*c[:3], 255)
    dark = (max(0, c[0] - 60), max(0, c[1] - 60), max(0, c[2] - 60), 255)

    for dx in range(-6, 7):
        draw.point((cx + dx, y + 7), fill=col)
        draw.point((cx + dx, y + 8), fill=dark)
    for dx in range(-5, 6):
        draw.point((cx + dx, y + 6), fill=col)
    for dx in range(-6, 7):
        draw.point((cx + dx, y + 5), fill=col)

    for peak_x, peak_top in [(-5, y + 1), (0, y), (5, y + 1)]:
        draw.point((cx + peak_x, peak_top), fill=col)
        draw.point((cx + peak_x, peak_top + 1), fill=col)
        draw.point((cx + peak_x - 1, peak_top + 2), fill=col)
        draw.point((cx + peak_x, peak_top + 2), fill=col)
        draw.point((cx + peak_x + 1, peak_top + 2), fill=col)

    for dx in [-4, -3, -2, -1, 1, 2, 3, 4]:
        draw.point((cx + dx, y + 3), fill=col)
        draw.point((cx + dx, y + 4), fill=col)

    gem_red = (255, 50, 50, 255)
    gem_blue = (80, 140, 255, 255)
    draw.point((cx, y + 6), fill=gem_red)
    draw.point((cx + 1, y + 6), fill=gem_red)
    draw.point((cx - 4, y + 6), fill=gem_blue)
    draw.point((cx + 4, y + 6), fill=gem_blue)


def _draw_pedestal(canvas: Image.Image, cx: int, y: int, w: int, theme: dict):
    """Flat elliptical stone disc the pet stands on."""
    accent = _t(theme, 'accent_color')
    border = _t(theme, 'border_color')
    hw = w // 2
    hh = max(4, w // 10)

    disc = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(disc)

    dd.ellipse([cx - hw, y - hh, cx + hw, y + hh],
               fill=(max(0, accent[0] - 20), max(0, accent[1] - 20),
                     max(0, accent[2] - 20), 120))

    dd.ellipse([cx - hw + 1, y - hh + 1, cx + hw - 1, y + hh - 1],
               fill=(*accent[:3], 80))

    dd.ellipse([cx - hw, y - hh, cx + hw, y + hh],
               outline=(*border[:3], 100))

    dd.ellipse([cx - hw // 2, y - hh + 1, cx + hw // 2, y],
               fill=(*border[:3], 30))

    canvas.alpha_composite(disc)


def _draw_nameplate(draw: ImageDraw.ImageDraw, cx: int, y: int,
                    name: str, role: str, level: int, theme: dict,
                    is_leader: bool, max_plate_w: int = 0):
    """Ribbon nameplate with name on top, role + level below."""
    accent = _t(theme, 'accent_color')
    border = _t(theme, 'border_color')
    text_color = _t(theme, 'text_color')

    font_name = _get_font(10)
    font_sub = _get_font(8)

    display_name = name[:12]
    badge_char, badge_color = ROLE_BADGE.get(role, ('\u2022', (180, 180, 180)))
    lv_text = f"Lv.{level}"
    sub_text = f"{badge_char} {lv_text}"

    name_w = int(draw.textlength(display_name, font=font_name))
    sub_w = int(draw.textlength(sub_text, font=font_sub))

    if max_plate_w and name_w > max_plate_w - 14:
        while name_w > max_plate_w - 14 and len(display_name) > 4:
            display_name = display_name[:-2] + ".."
            name_w = int(draw.textlength(display_name, font=font_name))

    inner_w = max(name_w, sub_w) + 14
    if max_plate_w:
        inner_w = min(inner_w, max_plate_w)
    hw = inner_w // 2
    rh = 26

    plate_color = (*accent[:3], 180)
    draw.rectangle([cx - hw, y, cx + hw, y + rh], fill=plate_color)

    draw.line([(cx - hw, y), (cx + hw, y)], fill=(*border[:3], 200), width=1)
    draw.line([(cx - hw, y + rh), (cx + hw, y + rh)], fill=(*border[:3], 120), width=1)
    draw.line([(cx - hw, y), (cx - hw, y + rh)], fill=(*border[:3], 100), width=1)
    draw.line([(cx + hw, y), (cx + hw, y + rh)], fill=(*border[:3], 100), width=1)

    notch = 4
    draw.polygon([
        (cx - hw - 1, y + 1), (cx - hw - notch, y + rh // 2), (cx - hw - 1, y + rh - 1)
    ], fill=plate_color)
    draw.polygon([
        (cx + hw + 1, y + 1), (cx + hw + notch, y + rh // 2), (cx + hw + 1, y + rh - 1)
    ], fill=plate_color)

    nx = cx - name_w // 2
    _draw_outlined_text(draw, (nx, y + 2), display_name,
                        font=font_name, fill=text_color, outline=(0, 0, 0))

    sx = cx - sub_w // 2
    _draw_outlined_text(draw, (sx, y + 14), sub_text,
                        font=font_sub, fill=badge_color, outline=(0, 0, 0))

    if is_leader:
        draw.rectangle([cx - hw + 1, y + 1, cx - hw + 2, y + rh - 1],
                       fill=(*border[:3], 100))
        draw.rectangle([cx + hw - 2, y + 1, cx + hw - 1, y + rh - 1],
                       fill=(*border[:3], 100))


def _draw_mood_bubble(draw: ImageDraw.ImageDraw, cx: int, y: int,
                      pet_state: PetState, frame_idx: int, theme: dict):
    """Mood as a colored pip/bubble with gentle float animation."""
    m = pet_state.mood
    if m >= 7:
        color = (255, 215, 0, 220)
    elif m >= 5:
        color = (100, 210, 100, 200)
    elif m >= 3:
        color = (220, 200, 80, 180)
    elif m >= 1:
        color = (255, 140, 60, 180)
    else:
        color = (255, 60, 60, 200)

    phase = (frame_idx % ANIMATION_FRAMES) / ANIMATION_FRAMES
    bob = int(1.5 * math.sin(2 * math.pi * phase))
    by = y + bob

    draw.ellipse([cx - 3, by - 3, cx + 3, by + 3], fill=color)
    draw.ellipse([cx - 3, by - 3, cx + 3, by + 3],
                 outline=(*color[:3], min(255, color[3] + 40)))
    draw.point((cx - 1, by - 1), fill=(255, 255, 255, 120))


# =============== pet layout & rendering ===============

def _layout_pets(members, theme):
    """Compute pet positions. Two rows for 7+ members, single row otherwise."""
    count = len(members)
    available_w = CANVAS_W - 40

    leaders = [(i, m) for i, m in enumerate(members) if m[1] == 'LEADER']
    others = [(i, m) for i, m in enumerate(members) if m[1] != 'LEADER']

    if count <= 6:
        if count <= 1:
            pet_size = 68
        elif count <= 3:
            pet_size = 62
        elif count <= 5:
            pet_size = 56
        else:
            pet_size = 50

        leader_size = int(pet_size * 1.15)

        sorted_members = []
        half = len(others) // 2
        sorted_members.extend(others[:half])
        sorted_members.extend(leaders)
        sorted_members.extend(others[half:])

        spacing = min(pet_size + 20, available_w // max(count, 1))
        total_w = spacing * count - (spacing - pet_size)
        start_x = (CANVAS_W - total_w) // 2

        ground_y = STATS_DIV_Y - GROUND_H
        nameplate_y = ground_y - 30

        slots = []
        for pos, (_, member_data) in enumerate(sorted_members):
            name, role, ps = member_data
            is_leader = (role == 'LEADER')
            sz = leader_size if is_leader else pet_size
            slot_cx = start_x + pos * spacing + pet_size // 2

            slots.append({
                'name': name, 'role': role, 'pet_state': ps,
                'is_leader': is_leader, 'pet_size': sz,
                'cx': slot_cx, 'pedestal_y': nameplate_y - 8,
                'nameplate_y': nameplate_y,
            })
        return slots

    half = len(others) // 2
    sorted_all = others[:half] + leaders + others[half:]

    front_row = sorted_all[::2]
    back_row = sorted_all[1::2]

    pet_size_front = max(38, min(48, available_w // len(front_row) - 10))
    pet_size_back = int(pet_size_front * 0.75)
    leader_bonus = int(pet_size_front * 0.12)

    ground_y = STATS_DIV_Y - GROUND_H
    front_nameplate_y = ground_y - 28
    front_ped_y = front_nameplate_y - 6

    back_ped_y = front_ped_y - pet_size_front + 10

    front_spacing = min(pet_size_front + 16, available_w // max(len(front_row), 1))
    front_total_w = front_spacing * len(front_row) - (front_spacing - pet_size_front)
    front_start_x = (CANVAS_W - front_total_w) // 2

    back_spacing = front_spacing
    half_offset = front_spacing // 2
    back_total_w = back_spacing * len(back_row) - (back_spacing - pet_size_back)
    back_start_x = front_start_x + half_offset

    if len(back_row) < len(front_row):
        back_total_w = back_spacing * len(back_row) - (back_spacing - pet_size_back)
        back_start_x = front_start_x + half_offset

    slots = []

    for pos, (_, member_data) in enumerate(back_row):
        name, role, ps = member_data
        is_leader = (role == 'LEADER')
        sz = pet_size_back + (leader_bonus if is_leader else 0)
        slot_cx = back_start_x + pos * back_spacing + pet_size_back // 2
        slots.append({
            'name': name, 'role': role, 'pet_state': ps,
            'is_leader': is_leader, 'pet_size': sz,
            'cx': slot_cx,
            'pedestal_y': back_ped_y,
            'nameplate_y': 0,
            'is_back_row': True,
        })

    for pos, (_, member_data) in enumerate(front_row):
        name, role, ps = member_data
        is_leader = (role == 'LEADER')
        sz = pet_size_front + (leader_bonus if is_leader else 0)
        slot_cx = front_start_x + pos * front_spacing + pet_size_front // 2
        slots.append({
            'name': name, 'role': role, 'pet_state': ps,
            'is_leader': is_leader, 'pet_size': sz,
            'cx': slot_cx,
            'pedestal_y': front_ped_y,
            'nameplate_y': front_nameplate_y,
            'is_back_row': False,
        })

    slots.sort(key=lambda s: (0 if s.get('is_back_row') else 1, s['cx']))
    return slots


def _draw_pets(canvas: Image.Image, state: FamilyPortraitState, frame_idx: int):
    members = state.member_sprites
    if not members:
        return

    theme = state.theme
    slots = _layout_pets(members, theme)

    for slot in slots:
        ps = slot['pet_state']
        is_leader = slot['is_leader']
        pet_size = slot['pet_size']
        cx = slot['cx']
        ped_y = slot['pedestal_y']
        np_y = slot['nameplate_y']

        pet_img, y_off = compose_pet_sprite(ps, frame_idx)
        scale = pet_size / 64
        scaled_w = max(1, int(pet_img.width * scale))
        scaled_h = max(1, int(pet_img.height * scale))
        pet_scaled = pet_img.resize((scaled_w, scaled_h), Image.Resampling.NEAREST)

        foot_y = ped_y + 2
        pet_x = cx - scaled_w // 2
        pet_y = max(SCENE_Y + 2, foot_y - scaled_h)

        pet_center_y = foot_y - pet_size // 2

        if is_leader:
            _draw_leader_glow(canvas, cx, pet_center_y, pet_size, theme, frame_idx)

        draw = ImageDraw.Draw(canvas)
        _draw_shadow(draw, cx, foot_y, int(pet_size * 0.7))

        canvas.alpha_composite(pet_scaled, (max(0, pet_x), max(0, pet_y)))

        draw = ImageDraw.Draw(canvas)
        is_back = slot.get('is_back_row', False)

        if not is_back:
            mood_y = pet_y - 8
            _draw_mood_bubble(draw, cx, mood_y, ps, frame_idx, theme)

        if is_leader:
            crown_y = pet_y - (6 if is_back else 14)
            _draw_crown(draw, cx, max(SCENE_Y + 2, crown_y), theme)

        if is_back:
            font_sm = _get_font(8)
            text_color = _t(theme, 'text_color')
            label = slot['name'][:9]
            lw = int(draw.textlength(label, font=font_sm))
            label_y = pet_y - 10
            _draw_outlined_text(draw, (cx - lw // 2, label_y), label,
                                font=font_sm, fill=text_color, outline=(0, 0, 0))
        else:
            plate_max = int(pet_size * 1.6)
            _draw_nameplate(draw, cx, np_y + 8, slot['name'], slot['role'],
                            ps.level, theme, is_leader, max_plate_w=plate_max)


# =============== stats bar ===============

def _draw_stats_bar(canvas: Image.Image, state: FamilyPortraitState):
    theme = state.theme
    accent = _t(theme, 'accent_color')
    text_color = _t(theme, 'text_color')
    border = _t(theme, 'border_color')
    draw = ImageDraw.Draw(canvas)

    bw = theme.get('border_width', 2)
    pad = bw + 10
    draw.rectangle([bw, STATS_Y, CANVAS_W - 1 - bw, CANVAS_H - 1 - bw],
                   fill=(*accent[:3], 110))

    font_label = _get_font(9)
    font_value = _get_font(14)
    font_xp_num = _get_font(10)

    usable_w = CANVAS_W - pad * 2
    sec_w = usable_w // 4

    # --- XP ---
    xp_x = pad
    # --- AI-MODIFIED (2026-03-24) ---
    # Purpose: Fix XP bar to show progress toward next level, not within current
    xp_current_threshold = _xp_for_level(state.family_level)
    xp_next_threshold = _xp_for_level(state.family_level + 1)
    xp_in_level = max(0, state.family_xp - xp_current_threshold)
    xp_range = max(1, xp_next_threshold - xp_current_threshold)
    progress = max(0.0, min(1.0, xp_in_level / xp_range))
    # --- END AI-MODIFIED ---

    _draw_outlined_text(draw, (xp_x, STATS_Y + 4), "EXP",
                        font=font_label, fill=(*text_color[:3], 160), outline=(0, 0, 0))

    bar_x = xp_x
    bar_y = STATS_Y + 18
    bar_w = sec_w - 12
    bar_h = 14

    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                    fill=(15, 15, 15, 220))

    fill_w = int(bar_w * progress)
    if fill_w > 0:
        bc = border
        for i in range(fill_w):
            t = i / max(1, bar_w)
            r = int(bc[0] * (0.6 + 0.4 * t))
            g = int(bc[1] * (0.6 + 0.4 * t))
            b = int(bc[2] * (0.6 + 0.4 * t))
            draw.line([(bar_x + i, bar_y + 1), (bar_x + i, bar_y + bar_h - 1)],
                      fill=(min(255, r), min(255, g), min(255, b), 230))
        draw.line([(bar_x + 1, bar_y + 1), (bar_x + fill_w - 1, bar_y + 1)],
                  fill=(255, 255, 255, 40))

    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                    outline=(*text_color[:3], 80))

    xp_text = f"{int(progress * 100)}%"
    xtw = int(draw.textlength(xp_text, font=font_xp_num))
    _draw_outlined_text(draw, (bar_x + (bar_w - xtw) // 2, bar_y + 1), xp_text,
                        font=font_xp_num, fill=text_color, outline=(0, 0, 0))

    xp_abs = f"{xp_in_level:,}/{xp_range:,}"
    _draw_outlined_text(draw, (xp_x + 30, STATS_Y + 4), xp_abs,
                        font=font_label, fill=(*text_color[:3], 120), outline=(0, 0, 0))

    # --- Gold ---
    gold_x = pad + sec_w + 4
    _draw_outlined_text(draw, (gold_x, STATS_Y + 4), "TREASURY",
                        font=font_label, fill=(*text_color[:3], 160), outline=(0, 0, 0))

    coin_icon = _load_asset("ui/icons/coin.png")
    if coin_icon:
        coin_s = coin_icon.resize((16, 16), Image.Resampling.NEAREST)
        canvas.alpha_composite(coin_s, (gold_x, STATS_Y + 18))

    draw = ImageDraw.Draw(canvas)
    gold_text = f"{state.family_gold:,}"
    _draw_outlined_text(draw, (gold_x + 20, STATS_Y + 17), gold_text,
                        font=font_value, fill=(255, 215, 0), outline=(0, 0, 0))

    # --- Members ---
    mem_x = pad + sec_w * 2 + 4
    _draw_outlined_text(draw, (mem_x, STATS_Y + 4), "MEMBERS",
                        font=font_label, fill=(*text_color[:3], 160), outline=(0, 0, 0))
    mem_text = f"{state.member_count}/{state.max_members}"
    _draw_outlined_text(draw, (mem_x, STATS_Y + 17), mem_text,
                        font=font_value, fill=text_color, outline=(0, 0, 0))

    # --- Power ---
    pwr_x = pad + sec_w * 3 + 4
    _draw_outlined_text(draw, (pwr_x, STATS_Y + 4), "POWER",
                        font=font_label, fill=(*text_color[:3], 160), outline=(0, 0, 0))
    total_levels = sum(ps.level for _, _, ps in state.member_sprites) if state.member_sprites else 0
    _draw_outlined_text(draw, (pwr_x, STATS_Y + 17), f"Lv.{total_levels}",
                        font=font_value, fill=(*border[:3], 230), outline=(0, 0, 0))

    # --- section dividers ---
    for i in range(1, 4):
        sx = pad + sec_w * i
        draw.line([(sx, STATS_Y + 5), (sx, CANVAS_H - bw - 5)],
                  fill=(*text_color[:3], 40), width=1)


# =============== frame composition ===============

def compose_family_frame(state: FamilyPortraitState, frame_idx: int) -> Image.Image:
    canvas = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

    _draw_gradient_bg(canvas, state.theme)
    _draw_ground_plane(canvas, state.theme)
    _draw_glow_border(canvas, state.theme)

    _draw_sparkles(canvas, frame_idx, state.theme)

    _draw_header(canvas, state)
    _draw_divider(canvas, HEADER_H, state.theme)
    _draw_pets(canvas, state, frame_idx)
    _draw_divider(canvas, STATS_DIV_Y, state.theme)
    _draw_stats_bar(canvas, state)

    draw = ImageDraw.Draw(canvas)
    _draw_border(draw, state.theme)

    return canvas


def render_family_portrait(state: FamilyPortraitState) -> bytes:
    gif_frames = []

    for frame_idx in range(ANIMATION_FRAMES):
        frame = compose_family_frame(state, frame_idx)
        upscaled = frame.resize((OUT_W, OUT_H), Image.Resampling.NEAREST)
        rgb = Image.new('RGB', (OUT_W, OUT_H), (20, 20, 30))
        rgb.paste(upscaled, mask=upscaled.split()[3])
        gif_frames.append(rgb)

    out = io.BytesIO()
    gif_frames[0].save(
        out,
        format='GIF',
        save_all=True,
        append_images=gif_frames[1:],
        duration=GIF_FRAME_DURATION,
        loop=0,
        optimize=False,
    )
    out.seek(0)
    return out.getvalue()

# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-07
# Purpose: Generate premium animated "drop card" GIFs for item
#          drop notifications. Rarity-escalating visual system
#          with floating items, light rays, energy rings,
#          particle effects, glowing text, and prismatic backgrounds.
# ============================================================
import io
import math
import random
import logging
from typing import Optional
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / 'assets'

CARD_W = 800
CARD_H = 360
EFFECT_PAD = 24
FULL_W = CARD_W + EFFECT_PAD * 2
FULL_H = CARD_H + EFFECT_PAD * 2
OUTER_BG = (16, 18, 24)
FRAMES = 12
FRAME_DURATION_MS = 120
ITEM_DISPLAY_SIZE = 180
ITEM_AREA_W = 280
CORNER_RADIUS = 20
BORDER_WIDTH = 4

EQUIPMENT_CATEGORIES = {'HAT', 'GLASSES', 'COSTUME', 'SHIRT', 'WINGS', 'BOOTS'}

RARITY_ORDER = ['COMMON', 'UNCOMMON', 'RARE', 'EPIC', 'LEGENDARY', 'MYTHICAL']

RARITY_THEMES = {
    'COMMON': {
        'bg_dark': (24, 26, 34),
        'bg_light': (38, 42, 52),
        'border': (80, 85, 100),
        'glow': (140, 145, 160),
        'text': (170, 175, 185),
        'badge_bg': (60, 65, 78),
        'glow_radius': 0,
        'glow_pulse': 0.0,
        'float_amplitude': 0,
        'sparkle_count': 0,
        'ray_count': 0,
        'ray_length': 0,
        'ring_count': 0,
        'orbit_count': 0,
        'star_count': 0,
    },
    'UNCOMMON': {
        'bg_dark': (12, 20, 45),
        'bg_light': (22, 36, 68),
        'border': (64, 128, 240),
        'glow': (80, 150, 255),
        'text': (120, 175, 255),
        'badge_bg': (40, 80, 180),
        'glow_radius': 20,
        'glow_pulse': 0.0,
        'float_amplitude': 4,
        'sparkle_count': 5,
        'ray_count': 0,
        'ray_length': 0,
        'ring_count': 0,
        'orbit_count': 0,
        'star_count': 0,
    },
    'RARE': {
        'bg_dark': (40, 12, 12),
        'bg_light': (62, 22, 22),
        'border': (224, 64, 64),
        'glow': (255, 80, 80),
        'text': (255, 120, 120),
        'badge_bg': (180, 40, 40),
        'glow_radius': 24,
        'glow_pulse': 0.3,
        'float_amplitude': 5,
        'sparkle_count': 8,
        'ray_count': 0,
        'ray_length': 0,
        'ring_count': 0,
        'orbit_count': 0,
        'star_count': 12,
    },
    'EPIC': {
        'bg_dark': (35, 28, 8),
        'bg_light': (55, 45, 14),
        'border': (240, 192, 64),
        'glow': (255, 215, 80),
        'text': (255, 220, 100),
        'badge_bg': (190, 150, 30),
        'glow_radius': 30,
        'glow_pulse': 0.4,
        'float_amplitude': 6,
        'sparkle_count': 12,
        'ray_count': 4,
        'ray_length': 120,
        'ring_count': 1,
        'orbit_count': 0,
        'star_count': 16,
    },
    'LEGENDARY': {
        'bg_dark': (28, 14, 40),
        'bg_light': (48, 26, 65),
        'border': (208, 96, 240),
        'glow': (220, 130, 255),
        'text': (230, 155, 255),
        'badge_bg': (160, 60, 200),
        'glow_radius': 38,
        'glow_pulse': 0.5,
        'float_amplitude': 8,
        'sparkle_count': 18,
        'ray_count': 6,
        'ray_length': 140,
        'ring_count': 2,
        'orbit_count': 4,
        'star_count': 30,
    },
    'MYTHICAL': {
        'bg_dark': (45, 10, 22),
        'bg_light': (68, 18, 35),
        'border': (255, 96, 128),
        'glow': (255, 120, 180),
        'text': (255, 150, 190),
        'badge_bg': (200, 50, 90),
        'glow_radius': 46,
        'glow_pulse': 0.6,
        'float_amplitude': 10,
        'sparkle_count': 26,
        'ray_count': 8,
        'ray_length': 160,
        'ring_count': 3,
        'orbit_count': 6,
        'star_count': 50,
    },
}

RARITY_LABELS = {
    'COMMON': 'COMMON',
    'UNCOMMON': 'UNCOMMON',
    'RARE': 'RARE',
    'EPIC': 'EPIC',
    'LEGENDARY': 'LEGENDARY',
    'MYTHICAL': 'MYTHICAL',
}

SLOT_LABELS = {
    'HEAD': 'Head', 'FACE': 'Face', 'BODY': 'Body', 'BACK': 'Back', 'FEET': 'Feet',
}

_asset_cache: dict[str, Optional[Image.Image]] = {}
_font_cache: dict[str, ImageFont.FreeTypeFont] = {}


def _load_asset(relative_path: str) -> Optional[Image.Image]:
    if relative_path in _asset_cache:
        cached = _asset_cache[relative_path]
        return cached.copy() if cached else None
    full_path = ASSETS_DIR / relative_path
    if full_path.exists():
        img = Image.open(full_path).convert('RGBA')
        _asset_cache[relative_path] = img
        return img.copy()
    _asset_cache[relative_path] = None
    return None


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if size in _font_cache:
        return _font_cache[size]
    font_path = ASSETS_DIR / 'ChunkyDunk.ttf'
    try:
        font = ImageFont.truetype(str(font_path), size)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except OSError:
            font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _resolve_item_asset(asset_path: Optional[str], category: str) -> Optional[Image.Image]:
    if not asset_path:
        return None
    if category in EQUIPMENT_CATEGORIES:
        return _load_asset(f"equipment/{asset_path}")
    if category == 'FURNITURE':
        return _load_asset(f"rooms/furniture/{asset_path}")
    return _load_asset(asset_path)


def _detect_content_bounds(img: Image.Image, padding: int = 2):
    data = img.getdata()
    w, h = img.size
    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if data[y * w + x][3] > 10:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < 0:
        return None
    min_x = max(0, min_x - padding)
    min_y = max(0, min_y - padding)
    max_x = min(w - 1, max_x + padding)
    max_y = min(h - 1, max_y + padding)
    return (min_x, min_y, max_x + 1, max_y + 1)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines = []
    current = ''
    for word in words:
        test = f"{current} {word}".strip()
        try:
            tw = font.getlength(test)
        except AttributeError:
            tw = len(test) * 7
        if tw <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


STROKE_OFFSETS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
GLOW_OFFSETS_1 = STROKE_OFFSETS
GLOW_OFFSETS_2 = [(-2, -2), (-2, 0), (-2, 2), (0, -2), (0, 2), (2, -2), (2, 0), (2, 2),
                  (-1, -2), (1, -2), (-2, -1), (2, -1), (-2, 1), (2, 1), (-1, 2), (1, 2)]


def _draw_outlined_text(draw, pos, text, font, fill=(255, 255, 255),
                         outline=(0, 0, 0), stroke_width=1):
    x, y = pos
    for sw in range(1, stroke_width + 1):
        for dx, dy in STROKE_OFFSETS:
            draw.text((x + dx * sw, y + dy * sw), text, fill=outline, font=font)
    draw.text((x, y), text, fill=fill, font=font)


def _draw_glowing_text(draw, pos, text, font, fill=(255, 255, 255),
                        glow_color=(255, 255, 255), outline=(0, 0, 0)):
    """Render text with a colored neon glow halo + black outline."""
    x, y = pos
    gc2 = (*glow_color[:3], 25)
    for dx, dy in GLOW_OFFSETS_2:
        draw.text((x + dx, y + dy), text, fill=gc2, font=font)
    gc1 = (*glow_color[:3], 50)
    for dx, dy in GLOW_OFFSETS_1:
        draw.text((x + dx, y + dy), text, fill=gc1, font=font)
    for dx, dy in STROKE_OFFSETS:
        draw.text((x + dx, y + dy), text, fill=outline, font=font)
    draw.text((x, y), text, fill=fill, font=font)


def _draw_light_rays(canvas: Image.Image, cx: int, cy: int, angle_offset: float,
                     count: int, length: int, color: tuple):
    """Draw rotating semi-transparent light ray wedges from a center point."""
    if count <= 0:
        return
    ray_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    ray_draw = ImageDraw.Draw(ray_layer)
    wedge_half_angle = math.pi / (count * 3)
    for i in range(count):
        angle = angle_offset + (2 * math.pi * i / count)
        a1 = angle - wedge_half_angle
        a2 = angle + wedge_half_angle
        tip_x = cx + int(math.cos(angle) * length)
        tip_y = cy + int(math.sin(angle) * length)
        left_x = cx + int(math.cos(a1) * length * 0.95)
        left_y = cy + int(math.sin(a1) * length * 0.95)
        right_x = cx + int(math.cos(a2) * length * 0.95)
        right_y = cy + int(math.sin(a2) * length * 0.95)
        ray_color = (*color[:3], 28)
        ray_draw.polygon([(cx, cy), (left_x, left_y), (tip_x, tip_y), (right_x, right_y)],
                         fill=ray_color)
    ray_layer = ray_layer.filter(ImageFilter.GaussianBlur(radius=6))
    canvas.alpha_composite(ray_layer)


def _draw_energy_ring(canvas: Image.Image, cx: int, cy: int, radius: float,
                      max_radius: float, color: tuple, width: int = 2):
    """Draw an expanding circle that fades as it grows."""
    if radius <= 0 or radius > max_radius:
        return
    fade = 1.0 - (radius / max_radius)
    alpha = int(55 * fade)
    if alpha < 5:
        return
    ring_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring_layer)
    r = int(radius)
    ring_draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)],
                      outline=(*color[:3], alpha), width=width)
    canvas.alpha_composite(ring_layer)


def _draw_orbiting_particles(canvas: Image.Image, cx: int, cy: int,
                              orbit_rx: int, orbit_ry: int, base_angle: float,
                              count: int, color: tuple):
    """Draw bright dots orbiting around a center on an elliptical path."""
    if count <= 0:
        return
    draw = ImageDraw.Draw(canvas)
    for i in range(count):
        angle = base_angle + (2 * math.pi * i / count)
        px = cx + int(math.cos(angle) * orbit_rx)
        py = cy + int(math.sin(angle) * orbit_ry)
        draw.ellipse([(px - 3, py - 3), (px + 3, py + 3)],
                     fill=(*color[:3], 200))
        draw.ellipse([(px - 1, py - 1), (px + 1, py + 1)],
                     fill=(255, 255, 255, 240))


def _generate_star_field(count: int, seed: int = 99) -> list[tuple]:
    """Pre-generate a list of (x_frac, y_frac, size, brightness) for background stars."""
    rng = random.Random(seed)
    stars = []
    for _ in range(count):
        stars.append((
            rng.random(),
            rng.random(),
            rng.choice([1, 1, 1, 2, 2, 3]),
            rng.randint(60, 180),
        ))
    return stars


def _draw_star_field(draw: ImageDraw.ImageDraw, stars: list, drift_x: float, drift_y: float,
                     area_w: int, area_h: int, color: tuple):
    """Draw drifting background stars."""
    for xf, yf, size, brightness in stars:
        sx = int((xf * area_w + drift_x) % area_w)
        sy = int((yf * area_h + drift_y) % area_h)
        c = (*color[:3], brightness)
        if size == 1:
            draw.point((sx, sy), fill=c)
        else:
            draw.ellipse([(sx, sy), (sx + size - 1, sy + size - 1)], fill=c)


def _generate_sparkles(count: int, seed: int = 42) -> list[dict]:
    """Pre-generate sparkle particle state for animation."""
    rng = random.Random(seed)
    sparkles = []
    for _ in range(count):
        sparkles.append({
            'x': rng.random(),
            'y': rng.random(),
            'speed': 0.02 + rng.random() * 0.04,
            'size': rng.choice([2, 2, 3, 3, 4, 5]),
            'brightness': rng.randint(120, 240),
            'phase': rng.random() * math.pi * 2,
        })
    return sparkles


def _draw_rising_sparkles(canvas: Image.Image, sparkles: list, frame_progress: float,
                           area_x: int, area_y: int, area_w: int, area_h: int,
                           color: tuple):
    """Draw sparkle particles that drift upward and twinkle."""
    draw = ImageDraw.Draw(canvas)
    for s in sparkles:
        y_offset = (s['y'] - s['speed'] * frame_progress * FRAMES) % 1.0
        sy = area_y + int(y_offset * area_h)
        sx = area_x + int(s['x'] * area_w)
        twinkle = 0.5 + 0.5 * math.sin(s['phase'] + frame_progress * math.pi * 4)
        alpha = int(s['brightness'] * twinkle)
        if alpha < 20:
            continue
        c = (*color[:3], alpha)
        sz = s['size']
        cx, cy = sx, sy
        draw.point((cx, cy), fill=(*color[:3], min(255, alpha + 40)))
        for d in range(1, sz):
            a2 = max(15, alpha - d * 35)
            c2 = (*color[:3], a2)
            draw.point((cx + d, cy), fill=c2)
            draw.point((cx - d, cy), fill=c2)
            draw.point((cx, cy + d), fill=c2)
            draw.point((cx, cy - d), fill=c2)


def _draw_rarity_badge(draw: ImageDraw.ImageDraw, x: int, y: int,
                        rarity: str, theme: dict):
    """Draw a prominent pill-shaped rarity badge."""
    label = RARITY_LABELS.get(rarity, rarity)
    font = _get_font(22)
    try:
        tw = font.getlength(label)
    except AttributeError:
        tw = len(label) * 14
    pad_x, pad_y = 20, 5
    bw = int(tw) + pad_x * 2
    bh = 34
    badge_bg = (*theme['badge_bg'], 160)
    badge_border = (*theme['border'], 200)
    draw.rounded_rectangle([(x, y), (x + bw, y + bh)], radius=6,
                           fill=badge_bg, outline=badge_border, width=1)
    text_x = x + pad_x
    text_y = y + pad_y
    draw.text((text_x, text_y), label, fill=(255, 255, 255), font=font)
    return bh


def _make_prismatic_bg(frame_idx: int, base_dark: tuple, base_light: tuple) -> Image.Image:
    """Generate a background with subtle hue shifting for Mythical rarity."""
    hue_shift = math.sin(frame_idx * math.pi * 2 / FRAMES) * 15
    bg = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(bg)
    for y in range(CARD_H):
        t = y / CARD_H
        r = int(base_dark[0] * (1 - t) + base_light[0] * t + hue_shift)
        g = int(base_dark[1] * (1 - t) + base_light[1] * t - abs(hue_shift) * 0.3)
        b = int(base_dark[2] * (1 - t) + base_light[2] * t + hue_shift * 0.6)
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        draw.line([(0, y), (CARD_W - 1, y)], fill=(r, g, b, 255))
    return bg


def _make_gradient_bg(dark: tuple, light: tuple) -> Image.Image:
    """Generate a static vertical gradient background."""
    bg = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(bg)
    for y in range(CARD_H):
        t = y / CARD_H
        r = int(dark[0] * (1 - t) + light[0] * t)
        g = int(dark[1] * (1 - t) + light[1] * t)
        b = int(dark[2] * (1 - t) + light[2] * t)
        draw.line([(0, y), (CARD_W - 1, y)], fill=(r, g, b, 255))
    return bg


def _prepare_item_sprite(asset_path: Optional[str], category: str) -> Optional[Image.Image]:
    """Load, auto-crop, and upscale an item sprite."""
    item_img = _resolve_item_asset(asset_path, category)
    if not item_img:
        return None
    bounds = _detect_content_bounds(item_img)
    cropped = item_img.crop(bounds) if bounds else item_img
    cw, ch = cropped.size
    scale = min(ITEM_DISPLAY_SIZE / cw, ITEM_DISPLAY_SIZE / ch)
    new_w = max(1, int(cw * scale))
    new_h = max(1, int(ch * scale))
    return cropped.resize((new_w, new_h), Image.NEAREST)


def _compose_text_layer(item_name: str, rarity: str, category: str,
                         slot: Optional[str], description: str,
                         owner_count: int, market_low: Optional[int],
                         theme: dict) -> Image.Image:
    """Pre-render the static text area onto an RGBA layer (reused across frames)."""
    layer = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    text_x = ITEM_AREA_W + 32
    text_y = 24

    name_font = _get_font(38)
    _draw_glowing_text(draw, (text_x, text_y), item_name, name_font,
                        fill=(255, 255, 255), glow_color=theme['glow'],
                        outline=(0, 0, 0))
    text_y += 52

    detail_font = _get_font(22)
    cat_label = category.replace('_', ' ').title() if category else ''
    slot_label = SLOT_LABELS.get(slot, '') if slot else ''
    if cat_label and slot_label:
        info_line = f"{cat_label}  |  {slot_label}"
    elif cat_label:
        info_line = cat_label
    else:
        info_line = ''
    if info_line:
        draw.text((text_x, text_y), info_line, fill=(150, 155, 170), font=detail_font)
        text_y += 32

    badge_h = _draw_rarity_badge(draw, text_x, text_y, rarity, theme)
    text_y += badge_h + 16

    if description:
        desc_font = _get_font(22)
        max_desc_w = CARD_W - text_x - 32
        desc_display = description[:100] + ('...' if len(description) > 100 else '')
        lines = _wrap_text(desc_display, desc_font, max_desc_w)
        for line in lines[:3]:
            draw.text((text_x, text_y), line, fill=(130, 135, 150), font=desc_font)
            text_y += 28

    stat_font = _get_font(22)
    stat_parts = []
    if owner_count > 0:
        stat_parts.append(f"{owner_count:,} owned")
    if market_low is not None and market_low > 0:
        stat_parts.append(f"Market: {market_low:,}G")
    if stat_parts:
        text_y = max(text_y + 4, CARD_H - 42)
        stat_line = "  |  ".join(stat_parts)
        draw.text((text_x, text_y), stat_line, fill=(100, 105, 120), font=stat_font)

    # Divider line
    div_x = ITEM_AREA_W + 8
    draw.line([(div_x, 24), (div_x, CARD_H - 24)],
              fill=(*theme['border'], 70), width=2)

    return layer


def render_drop_card(
    item_name: str,
    rarity: str,
    category: str,
    asset_path: Optional[str] = None,
    description: str = '',
    slot: Optional[str] = None,
    gold_price: Optional[int] = None,
    owner_count: int = 0,
    market_low: Optional[int] = None,
) -> Optional[bytes]:
    """Render an animated drop card GIF for an item drop notification.

    Returns GIF bytes, or None if rendering fails.
    """
    try:
        theme = RARITY_THEMES.get(rarity, RARITY_THEMES['COMMON'])
        rarity_idx = RARITY_ORDER.index(rarity) if rarity in RARITY_ORDER else 0
        is_mythical = rarity == 'MYTHICAL'

        item_sprite = _prepare_item_sprite(asset_path, category)

        card_item_cx = ITEM_AREA_W // 2
        card_item_cy = CARD_H // 2
        fx_cx = card_item_cx + EFFECT_PAD
        fx_cy = card_item_cy + EFFECT_PAD

        static_bg = _make_gradient_bg(theme['bg_dark'], theme['bg_light'])

        stars = _generate_star_field(theme['star_count'], seed=hash(item_name) & 0xFFFF)
        sparkles = _generate_sparkles(theme['sparkle_count'], seed=(hash(item_name) >> 8) & 0xFFFF)

        text_layer = _compose_text_layer(item_name, rarity, category, slot,
                                          description, owner_count, market_low, theme)

        card_mask = Image.new('L', (CARD_W, CARD_H), 0)
        card_mask_draw = ImageDraw.Draw(card_mask)
        card_mask_draw.rounded_rectangle([(0, 0), (CARD_W - 1, CARD_H - 1)],
                                          radius=CORNER_RADIUS, fill=255)

        gif_frames = []

        for f in range(FRAMES):
            t = f / FRAMES
            angle = t * 2 * math.pi

            # 1. Card background (CARD_W x CARD_H) with stars baked in
            if is_mythical:
                card_bg = _make_prismatic_bg(f, theme['bg_dark'], theme['bg_light'])
            else:
                card_bg = static_bg.copy()

            if stars:
                star_draw = ImageDraw.Draw(card_bg)
                _draw_star_field(star_draw, stars, t * 30, t * 15,
                                 CARD_W, CARD_H, theme['glow'])

            # 2. Full canvas with dark outer fill
            frame = Image.new('RGBA', (FULL_W, FULL_H), (*OUTER_BG, 255))

            # 3. Paste card background into center using rounded mask
            card_bg_masked = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
            card_bg_masked.paste(card_bg, (0, 0), card_mask)
            frame.alpha_composite(card_bg_masked, (EFFECT_PAD, EFFECT_PAD))

            # 4. Light rays -- drawn on full canvas, bleed freely
            if theme['ray_count'] > 0:
                ray_angle = angle * 0.3
                ray_color = theme['glow']
                if is_mythical:
                    hue = t * math.pi * 2
                    ray_color = (
                        int(200 + 55 * math.sin(hue)),
                        int(100 + 55 * math.sin(hue + 2.1)),
                        int(150 + 55 * math.sin(hue + 4.2)),
                    )
                _draw_light_rays(frame, fx_cx, fx_cy, ray_angle,
                                 theme['ray_count'], theme['ray_length'], ray_color)

            # 5. Energy rings -- drawn on full canvas, bleed freely
            max_ring_radius = 140
            for ring_i in range(theme['ring_count']):
                ring_offset = ring_i / max(theme['ring_count'], 1)
                ring_progress = (t + ring_offset) % 1.0
                ring_radius = ring_progress * max_ring_radius
                _draw_energy_ring(frame, fx_cx, fx_cy, ring_radius,
                                  max_ring_radius, theme['glow'], width=3)

            # 6. Glow halo -- drawn on full canvas, bleed freely
            glow_r = theme['glow_radius']
            if glow_r > 0 and item_sprite:
                pulse = 1.0 + theme['glow_pulse'] * math.sin(angle)
                effective_r = int(glow_r * pulse)
                sprite_w, sprite_h = item_sprite.size
                blur_r = effective_r * 2
                inner_r = max(sprite_w, sprite_h) // 2 + effective_r // 2
                glow_size = (inner_r + blur_r) * 2 + 20
                glow_layer = Image.new('RGBA', (glow_size, glow_size), (0, 0, 0, 0))
                glow_draw = ImageDraw.Draw(glow_layer)
                gc = glow_size // 2
                glow_alpha = int(55 + 25 * math.sin(angle))
                glow_draw.ellipse([(gc - inner_r, gc - inner_r),
                                   (gc + inner_r, gc + inner_r)],
                                  fill=(*theme['glow'][:3], glow_alpha))
                glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=blur_r))
                float_y_offset = int(theme['float_amplitude'] * math.sin(angle))
                gx = fx_cx - gc
                gy = fx_cy - gc + float_y_offset
                frame.alpha_composite(glow_layer, (gx, gy))

            # 7. Item sprite (floating) -- on full canvas
            if item_sprite:
                float_y = int(theme['float_amplitude'] * math.sin(angle))
                sw, sh = item_sprite.size
                ix = fx_cx - sw // 2
                iy = fx_cy - sh // 2 + float_y
                frame.alpha_composite(item_sprite, (ix, iy))

            # 8. Orbiting particles -- on full canvas, bleed freely
            if theme['orbit_count'] > 0:
                orbit_angle = angle * 0.8
                orx = 70 + (10 if is_mythical else 0)
                ory = 50 + (8 if is_mythical else 0)
                _draw_orbiting_particles(frame, fx_cx, fx_cy, orx, ory,
                                          orbit_angle, theme['orbit_count'], theme['glow'])

            # 9. Rising sparkles -- within item area (offset by PAD)
            if sparkles:
                _draw_rising_sparkles(frame, sparkles, t,
                                       EFFECT_PAD + 8, EFFECT_PAD + 8,
                                       ITEM_AREA_W - 16, CARD_H - 16,
                                       theme['glow'])

            # 10. Text layer -- composited at card position
            frame.alpha_composite(text_layer, (EFFECT_PAD, EFFECT_PAD))

            # 11. Border -- drawn at card position
            border_layer = Image.new('RGBA', (CARD_W, CARD_H), (0, 0, 0, 0))
            border_draw = ImageDraw.Draw(border_layer)
            if is_mythical:
                hue = t * math.pi * 2
                br = max(0, min(255, int(200 + 55 * math.sin(hue))))
                bg = max(0, min(255, int(80 + 55 * math.sin(hue + 2.1))))
                bb = max(0, min(255, int(120 + 55 * math.sin(hue + 4.2))))
                border_c = (br, bg, bb, 200)
            elif theme['glow_pulse'] > 0:
                pulse_alpha = int(160 + 40 * math.sin(angle))
                border_c = (*theme['border'][:3], pulse_alpha)
            else:
                border_c = (*theme['border'][:3], 180)
            border_draw.rounded_rectangle(
                [(0, 0), (CARD_W - 1, CARD_H - 1)],
                radius=CORNER_RADIUS, outline=border_c, width=BORDER_WIDTH
            )
            frame.alpha_composite(border_layer, (EFFECT_PAD, EFFECT_PAD))

            # 12. Flatten to RGB
            rgb = Image.new('RGB', (FULL_W, FULL_H), OUTER_BG)
            rgb.paste(frame, mask=frame.split()[3])
            gif_frames.append(rgb)

        output = io.BytesIO()
        gif_frames[0].save(
            output,
            format='GIF',
            save_all=True,
            append_images=gif_frames[1:],
            duration=FRAME_DURATION_MS,
            loop=0,
            optimize=False,
        )
        output.seek(0)
        return output.getvalue()

    except Exception:
        logger.exception("Failed to render drop card for %s", item_name)
        return None

# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-15
# Purpose: LionGotchi farm renderer - deeply animated version
#          Animated plant sprites, floating growth timers,
#          water particle effects, atmospheric particles,
#          enhanced sparkle/harvest effects, all inside Gameboy
# ============================================================
import io
import math
import logging
from typing import Optional
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from .renderer import PetState, draw_gameboy_ui, apply_screen_depth

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / 'assets'

# --- Gameboy frame constants ---
FRAME_W = 260
FRAME_H = 400
SCREEN_X = 30
SCREEN_Y = 36
SCREEN_W = 200
SCREEN_H = 200

# --- Animation ---
# --- AI-MODIFIED (2026-03-15) ---
# Purpose: Increased from 8 frames/280ms (3.6 FPS) to 16 frames/80ms (12.5 FPS)
NUM_FRAMES = 16
GIF_FRAME_DURATION = 80
# --- END AI-MODIFIED ---
SWAY_AMPLITUDE = 1.5
BOB_AMPLITUDE = 1.5
TWO_PI = 2 * math.pi

# --- Growth stage heights (px) for plant scaling ---
# --- AI-MODIFIED (2026-03-17) ---
# Purpose: Sized plants so they fit within all plot positions without edge clamping.
# Previous values (32-86) caused trees (137x143 sprites, nearly square) to be 82px
# wide at stage 5, overflowing edge plots and shifting trees off-center by up to 19px.
# New values keep width ≤42px (safe for all 15 plots with sway) while still being
# larger than the original developer's values (12-36) for better visibility.
# --- Original code (commented out for rollback) ---
# STAGE_HEIGHTS = {
#     0: 0,
#     1: 12,
#     2: 18,
#     3: 24,
#     4: 30,
#     5: 36,
# }
# --- End original code ---
STAGE_HEIGHTS = {
    0: 0,
    1: 18,
    2: 24,
    3: 30,
    4: 36,
    5: 44,
}
# --- END AI-MODIFIED ---

# --- Isometric plot centers (1-indexed) ---
PLOT_CENTERS = {
    1:  (40, 138),   2: (32, 154),   3: (22, 174),
    4:  (71, 138),   5: (66, 154),   6: (60, 174),
    7:  (100, 138),  8: (100, 154),  9: (100, 174),
    10: (128, 138), 11: (132, 154), 12: (139, 174),
    13: (158, 138), 14: (166, 154), 15: (176, 174),
}

# --- Seed -> animated plant sprite mapping ---
# Maps asset_prefix (from lg_farm_seeds) to a specific plant GIF
# Spread across all 5 series (a-e) for visual variety
# --- AI-MODIFIED (2026-03-15) ---
# Purpose: Tree entries removed -- trees now use rarity-colored static PNGs (20 designs x 5 colors x 5 stages).
# Only pollen/plant GIFs remain in SEED_PLANT_MAP.
SEED_PLANT_MAP = {
    'pollen:1':  'farm/plants/a_50.gif',
    'pollen:2':  'farm/plants/b_60.gif',
    'pollen:3':  'farm/plants/c_40.gif',
    'pollen:4':  'farm/plants/d_90.gif',
    'pollen:5':  'farm/plants/e_95.gif',
    'pollen:6':  'farm/plants/a_22.gif',
    'pollen:7':  'farm/plants/b_38.gif',
    'pollen:8':  'farm/plants/d_55.gif',
    'pollen:9':  'farm/plants/e_48.gif',
    'pollen:10': 'farm/plants/c_88.gif',
}
# --- END AI-MODIFIED ---

# --- Atmospheric particle presets ---
LEAF_PARTICLES = [
    (18, 35), (72, 28), (145, 42), (55, 70), (118, 52),
    (35, 95), (160, 85),
]
FIREFLY_POSITIONS = [
    (28, 55), (85, 40), (155, 65), (65, 85), (125, 48),
    (40, 110), (170, 100),
]

# --- Water drop offsets relative to plot center ---
WATER_DROP_OFFSETS = [(-4, -22), (3, -28), (-1, -16), (5, -24)]

STROKE_OFFSETS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

_asset_cache: dict[str, Optional[Image.Image]] = {}
_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _load(path: str) -> Optional[Image.Image]:
    if path in _asset_cache:
        cached = _asset_cache[path]
        return cached.copy() if cached else None
    full = ASSETS_DIR / path
    if full.exists():
        img = Image.open(full).convert('RGBA')
        _asset_cache[path] = img
        return img.copy()
    _asset_cache[path] = None
    return None


def _get_font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    fp = ASSETS_DIR / 'ChunkyDunk.ttf'
    try:
        font = ImageFont.truetype(str(fp), size)
    except OSError:
        font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _draw_outlined(draw, pos, text, font, fill=(255, 255, 255), outline=(0, 0, 0)):
    x, y = pos
    for dx, dy in STROKE_OFFSETS:
        draw.text((x + dx, y + dy), text, fill=outline, font=font)
    draw.text(pos, text, fill=fill, font=font)


# --- AI-MODIFIED (2026-03-15) ---
# Purpose: Rarity-aware tree asset lookup (20 designs x 5 colors x 5 stages = 500 PNGs)
from .gameplay import RARITY_COLOR_INDEX

def _get_tree_asset(type_id: int, stage: int, rarity: str = 'COMMON') -> str:
    color = RARITY_COLOR_INDEX.get(rarity, 1)
    idx = (type_id - 1) * 25 + (color - 1) * 5 + min(stage, 5)
    return f"farm/trees/trees_{idx:02d}.png"

RARITY_GLOW_COLOR = {
    'COMMON': None,
    'UNCOMMON': (80, 160, 255, 90),
    'RARE': (255, 60, 60, 100),
    'EPIC': (255, 215, 0, 110),
    'LEGENDARY': (255, 100, 220, 120),
}
# --- END AI-MODIFIED ---


def _get_pollen_asset(type_id: int, stage: int) -> str:
    idx = (type_id - 1) * 5 + min(stage, 5)
    return f"farm/pollen/pollen_plant_{idx:02d}.png"


def _get_plant_sprite(asset_prefix: str, plant_type: str, type_id: int, stage: int,
                      rarity: str = 'COMMON') -> Optional[Image.Image]:
    """Load plant sprite. Trees use rarity-colored PNGs; pollen uses GIFs or fallback PNGs."""
    if plant_type == 'tree' and 1 <= type_id <= 20:
        return _load(_get_tree_asset(type_id, stage, rarity))

    gif_path = SEED_PLANT_MAP.get(asset_prefix)
    if gif_path:
        img = _load(gif_path)
        if img:
            return img

    if plant_type == 'pollen':
        return _load(_get_pollen_asset(type_id, stage))
    return _load(_get_tree_asset(type_id, stage, rarity))


def _sway_offset(anim_frame: int, plot_num: int) -> int:
    """Sinusoidal horizontal sway, phase-shifted per plot for organic feel."""
    phase = ((anim_frame + plot_num * 3) % NUM_FRAMES) / NUM_FRAMES
    return int(SWAY_AMPLITUDE * math.sin(TWO_PI * phase))


def _bob_offset(anim_frame: int, plot_num: int) -> int:
    """Vertical bob for floating elements, phase-shifted per plot."""
    phase = ((anim_frame + plot_num * 5) % NUM_FRAMES) / NUM_FRAMES
    return int(BOB_AMPLITUDE * math.sin(TWO_PI * phase))


class FarmState:
    def __init__(self, plots: list[dict], is_night: bool = False,
                 just_watered: bool = False,
                 gameboy_skin: str = "gameboy/frames/gameboy-basic-01.png",
                 pet_state: Optional[PetState] = None):
        self.plots = plots
        self.is_night = is_night
        self.just_watered = just_watered
        self.gameboy_skin = gameboy_skin
        self.pet_state = pet_state


# --- AI-REPLACED (2026-03-16) ---
# Reason: Glow was a solid rectangle, making it ugly. Now uses the plant's
#   alpha channel to create a silhouette-shaped aura that follows the actual
#   outline of the tree/plant.
# What the new code does better: Glow wraps around the plant shape instead
#   of being a visible rectangle.
# --- Original code (commented out for rollback) ---
# def _draw_plants(scene, state, anim_frame):
#     ...  (drew glow as Image.new('RGBA', (glow_size, glow_h), solid_color))
# --- End original code ---

GLOW_SPREAD = 3

def _draw_plants(scene: Image.Image, state: FarmState, anim_frame: int):
    """Draw all plant sprites with growth-based scaling, sway animation, and silhouette glow."""
    for plot in state.plots:
        plot_num = plot.get('plot_num', 0) + 1
        if plot_num < 1 or plot_num > 15:
            continue

        has_seed = plot.get('seed_id') is not None and plot.get('seed_id')
        if not has_seed or plot.get('dead'):
            continue

        stage = plot.get('growth_stage', 0)
        if stage < 1:
            continue

        asset_prefix = plot.get('asset_prefix', '')
        plant_type = plot.get('plant_type', 'tree')
        type_id = plot.get('type_id', 1)
        rarity = plot.get('rarity', 'COMMON')

        plant_img = _get_plant_sprite(asset_prefix, plant_type, type_id, stage, rarity)
        if not plant_img:
            continue

        target_h = STAGE_HEIGHTS.get(stage, 20)
        if target_h <= 0:
            continue

        scale = target_h / plant_img.height
        new_w = max(1, int(plant_img.width * scale))
        plant_img = plant_img.resize((new_w, target_h), Image.Resampling.NEAREST)

        cx, cy = PLOT_CENTERS.get(plot_num, (100, 150))
        sway = _sway_offset(anim_frame, plot_num) if stage >= 2 else 0
        px = cx - new_w // 2 + sway
        py = cy - target_h + 2
        dest_x = max(0, min(px, SCREEN_W - new_w))
        dest_y = max(0, py)

        glow_color = RARITY_GLOW_COLOR.get(rarity)
        if glow_color and stage >= 2:
            pulse = 0.7 + 0.3 * math.sin(TWO_PI * ((anim_frame + plot_num * 2) % NUM_FRAMES) / NUM_FRAMES)
            alpha_val = int(glow_color[3] * pulse)
            pad = GLOW_SPREAD
            glow_w = new_w + pad * 2
            glow_h = target_h + pad * 2

            plant_alpha = plant_img.split()[3]
            glow_canvas = Image.new('RGBA', (glow_w, glow_h), (0, 0, 0, 0))
            color_fill = Image.new('RGBA', (new_w, target_h), (*glow_color[:3], alpha_val))

            for dx in range(-pad, pad + 1):
                for dy in range(-pad, pad + 1):
                    if dx * dx + dy * dy <= pad * pad + 1:
                        glow_canvas.paste(color_fill, (pad + dx, pad + dy), mask=plant_alpha)

            gx = max(0, dest_x - pad)
            gy = max(0, dest_y - pad)
            scene.alpha_composite(glow_canvas, (gx, gy))

        scene.alpha_composite(plant_img, (dest_x, dest_y))
# --- END AI-REPLACED ---


def _draw_soil(scene: Image.Image, state: FarmState):
    """Draw watered/dry soil overlays for each plot."""
    for plot in state.plots:
        plot_num = plot.get('plot_num', 0) + 1
        if plot_num < 1 or plot_num > 15:
            continue

        has_seed = plot.get('seed_id') is not None and plot.get('seed_id')
        is_watered = plot.get('is_watered', False)

        if has_seed and is_watered:
            soil = _load(f"farm/soil/watered/wateredsoil{plot_num}.png")
        else:
            soil = _load(f"farm/soil/dry/drysoil{plot_num}.png")

        if soil:
            scene.alpha_composite(soil)


def _draw_dead_skulls(scene: Image.Image, state: FarmState, anim_frame: int):
    """Draw animated skull on dead plots."""
    for plot in state.plots:
        if not plot.get('dead'):
            continue
        plot_num = plot.get('plot_num', 0) + 1
        if plot_num not in PLOT_CENTERS:
            continue
        cx, cy = PLOT_CENTERS[plot_num]
        skull_frame = (anim_frame % 5) + 1
        skull = _load(f"farm/animations/skull_{skull_frame:02d}.png")
        if skull:
            skull = skull.resize((18, 18), Image.Resampling.NEAREST)
            bob = _bob_offset(anim_frame, plot_num)
            scene.alpha_composite(skull, (cx - 9, cy - 22 + bob))


def _draw_harvest_effects(scene: Image.Image, state: FarmState, anim_frame: int):
    """Enhanced sparkle + coin for harvestable (stage 5) plants."""
    for plot in state.plots:
        has_seed = plot.get('seed_id') is not None and plot.get('seed_id')
        if not has_seed or plot.get('dead'):
            continue
        if plot.get('growth_stage', 0) < 5:
            continue

        plot_num = plot.get('plot_num', 0) + 1
        if plot_num not in PLOT_CENTERS:
            continue
        cx, cy = PLOT_CENTERS[plot_num]
        target_h = STAGE_HEIGHTS.get(5, 36)

        sparkle_frame = ((anim_frame + plot_num) % 3) + 1
        sparkle = _load(f"farm/animations/sparkle_{sparkle_frame:02d}.png")
        if sparkle:
            sp_w, sp_h = 22, 12
            sparkle_main = sparkle.resize((sp_w, sp_h), Image.Resampling.NEAREST)
            bob1 = _bob_offset(anim_frame, plot_num)
            sx = cx - sp_w // 2
            sy = cy - target_h - 6 + bob1
            scene.alpha_composite(sparkle_main, (max(0, sx), max(0, sy)))

            sparkle_frame2 = ((anim_frame + plot_num + 4) % 3) + 1
            sparkle2 = _load(f"farm/animations/sparkle_{sparkle_frame2:02d}.png")
            if sparkle2:
                sp2 = sparkle2.resize((14, 8), Image.Resampling.NEAREST)
                bob2 = _bob_offset(anim_frame + 3, plot_num + 2)
                scene.alpha_composite(sp2, (max(0, cx + 4), max(0, cy - target_h + 2 + bob2)))

        coin = _load("ui/icons/coin.png")
        if coin:
            coin_size = 10
            coin = coin.resize((coin_size, coin_size), Image.Resampling.NEAREST)
            coin_bob = _bob_offset(anim_frame + 2, plot_num)
            coin_x = cx - coin_size // 2 + 8
            coin_y = cy - target_h - 14 + coin_bob
            scene.alpha_composite(coin, (max(0, min(coin_x, SCREEN_W - coin_size)), max(0, coin_y)))


def _draw_water_effects(scene: Image.Image, draw: ImageDraw.ImageDraw,
                        state: FarmState, anim_frame: int):
    """Draw falling water drops when just_watered, blue shimmer on watered plots."""
    for plot in state.plots:
        has_seed = plot.get('seed_id') is not None and plot.get('seed_id')
        if not has_seed or plot.get('dead'):
            continue

        plot_num = plot.get('plot_num', 0) + 1
        if plot_num not in PLOT_CENTERS:
            continue
        cx, cy = PLOT_CENTERS[plot_num]

        if state.just_watered:
            for i, (dx, dy_base) in enumerate(WATER_DROP_OFFSETS):
                fall_speed = 4
                drop_phase = (anim_frame + i * 2) % NUM_FRAMES
                drop_y = dy_base + drop_phase * fall_speed
                actual_y = cy + drop_y
                actual_x = cx + dx
                if actual_y < cy - 2:
                    drop_len = 3
                    draw.line(
                        [(actual_x, actual_y), (actual_x, actual_y + drop_len)],
                        fill=(100, 160, 255, 220), width=1
                    )
                    if drop_phase >= NUM_FRAMES - 2:
                        splash_y = cy - 3
                        draw.ellipse(
                            (actual_x - 2, splash_y, actual_x + 2, splash_y + 2),
                            fill=(130, 180, 255, 150)
                        )

        elif plot.get('is_watered'):
            shimmer_alpha = 60 + int(40 * math.sin(TWO_PI * anim_frame / NUM_FRAMES + plot_num))
            shimmer = Image.new('RGBA', (14, 4), (100, 170, 255, shimmer_alpha))
            sx = cx - 7
            sy = cy - 1
            if 0 <= sx < SCREEN_W - 14 and 0 <= sy < SCREEN_H - 4:
                scene.alpha_composite(shimmer, (sx, sy))


# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Larger, clearer timer text (9px instead of 7px) with better positioning
def _draw_floating_timers(draw: ImageDraw.ImageDraw, state: FarmState, anim_frame: int):
    """Draw timer/status text floating above each plot."""
    font = _get_font(9)
    for plot in state.plots:
        timer_text = plot.get('timer_text')
        if not timer_text:
            continue

        plot_num = plot.get('plot_num', 0) + 1
        if plot_num not in PLOT_CENTERS:
            continue

        cx, cy = PLOT_CENTERS[plot_num]
        stage = plot.get('growth_stage', 0)
        target_h = STAGE_HEIGHTS.get(stage, 0)
        bob = _bob_offset(anim_frame, plot_num)

        timer_color = plot.get('timer_color', (255, 255, 255))

        text_w = draw.textlength(timer_text, font=font)
        tx = int(cx - text_w / 2)
        ty = cy - target_h - 16 + bob

        tx = max(1, min(tx, SCREEN_W - int(text_w) - 1))
        ty = max(1, ty)

        _draw_outlined(draw, (tx, ty), timer_text, font=font, fill=timer_color)
# --- END AI-MODIFIED ---


def _draw_atmosphere(draw: ImageDraw.ImageDraw, state: FarmState, anim_frame: int):
    """Draw ambient particles: drifting leaves (day) or blinking fireflies (night)."""
    if state.is_night:
        for i, (fx, fy) in enumerate(FIREFLY_POSITIONS):
            blink_phase = (anim_frame + i * 3) % NUM_FRAMES
            if blink_phase < 5:
                glow_radius = 2 if blink_phase < 3 else 1
                alpha = 220 if blink_phase < 3 else 120
                draw.ellipse(
                    (fx - glow_radius, fy - glow_radius,
                     fx + glow_radius, fy + glow_radius),
                    fill=(255, 255, 120, alpha)
                )
                if glow_radius == 2:
                    draw.ellipse(
                        (fx - 4, fy - 4, fx + 4, fy + 4),
                        fill=(255, 255, 100, 30)
                    )
    else:
        for i, (lx, ly) in enumerate(LEAF_PARTICLES):
            drift_speed = 3 + (i % 3)
            fall_speed = 1 + (i % 2)
            phase = (anim_frame + i * 2) % NUM_FRAMES
            actual_x = (lx + phase * drift_speed) % SCREEN_W
            actual_y = (ly + phase * fall_speed) % 120
            colors = [
                (110, 170, 60, 160),
                (160, 190, 50, 140),
                (130, 150, 70, 150),
                (180, 160, 40, 130),
            ]
            color = colors[i % len(colors)]
            draw.rectangle(
                (actual_x, actual_y, actual_x + 2, actual_y + 1),
                fill=color
            )
            if i % 2 == 0:
                draw.point((actual_x + 1, actual_y + 1), fill=color)


def _draw_watercan_sweep(scene: Image.Image, state: FarmState, anim_frame: int):
    """Draw watering can sweeping across planted plots when just_watered."""
    if not state.just_watered:
        return

    planted_plots = [
        p for p in state.plots
        if p.get('seed_id') and not p.get('dead')
    ]
    if not planted_plots:
        return

    sweep_idx = anim_frame % len(planted_plots)
    target_plot = planted_plots[sweep_idx]
    plot_num = target_plot.get('plot_num', 0) + 1
    if plot_num not in PLOT_CENTERS:
        return

    cx, cy = PLOT_CENTERS[plot_num]
    wc_frame = (anim_frame % 3) + 1
    wc = _load(f"farm/animations/watercan_{wc_frame:02d}.png")
    if wc:
        wc = wc.resize((24, 24), Image.Resampling.NEAREST)
        scene.alpha_composite(wc, (max(0, cx - 6), max(0, cy - 32)))


# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Animated water strip at the bottom of the farm scene (y=192-199)
WATER_Y_START = 192
WATER_Y_END = 200
WATER_HIGHLIGHT_DAY = (80, 210, 245)
WATER_HIGHLIGHT_NIGHT = (70, 180, 220)

def _draw_water_strip(draw: ImageDraw.ImageDraw, state: FarmState, anim_frame: int):
    """Animate the water strip at the bottom of the farm background with waves and shimmer."""
    highlight = WATER_HIGHLIGHT_NIGHT if state.is_night else WATER_HIGHLIGHT_DAY
    wave_speed = 2

    for x in range(0, SCREEN_W, 2):
        wave_phase = (x * 0.15 + anim_frame * wave_speed * 0.4)
        wave_y = WATER_Y_START + int(1.5 * math.sin(wave_phase))

        alpha = 50 + int(30 * math.sin(wave_phase * 1.3 + anim_frame * 0.5))
        draw.line(
            [(x, wave_y), (x + 1, wave_y)],
            fill=(*highlight, alpha), width=1
        )

    for i in range(5):
        wave_x = (i * 42 + anim_frame * 3) % SCREEN_W
        wave_y_line = WATER_Y_START + 3 + (i % 3)
        wave_len = 8 + (i % 4) * 2
        alpha = 40 + int(25 * math.sin(TWO_PI * anim_frame / NUM_FRAMES + i * 1.2))
        draw.line(
            [(wave_x, wave_y_line), (wave_x + wave_len, wave_y_line)],
            fill=(*highlight, alpha), width=1
        )

    sparkle_phase = (anim_frame * 2 + 7) % NUM_FRAMES
    if sparkle_phase < 6:
        sx = (anim_frame * 13 + 40) % (SCREEN_W - 4)
        sy = WATER_Y_START + 2
        sparkle_a = 120 if sparkle_phase < 3 else 60
        draw.rectangle(
            (sx, sy, sx + 1, sy + 1),
            fill=(220, 240, 255, sparkle_a)
        )
# --- END AI-MODIFIED ---


def compose_farm_scene(state: FarmState, anim_frame: int = 0) -> Image.Image:
    """Compose a single frame of the farm scene with all effects."""
    bg_path = "farm/backgrounds/farm_night.png" if state.is_night else "farm/backgrounds/farm_day.png"
    bg = _load(bg_path)
    if bg is None:
        bg = Image.new('RGBA', (SCREEN_W, SCREEN_H), (80, 140, 60, 255))
    scene = bg.copy()

    _draw_soil(scene, state)

    _draw_plants(scene, state, anim_frame)

    _draw_dead_skulls(scene, state, anim_frame)

    _draw_harvest_effects(scene, state, anim_frame)

    draw = ImageDraw.Draw(scene)

    _draw_water_strip(draw, state, anim_frame)

    _draw_water_effects(scene, draw, state, anim_frame)

    _draw_watercan_sweep(scene, state, anim_frame)

    _draw_atmosphere(draw, state, anim_frame)

    _draw_floating_timers(draw, state, anim_frame)

    return scene


def render_farm_frame(state: FarmState) -> bytes:
    """Render the full farm view: 8-frame animated GIF inside the Gameboy frame."""
    gameboy = _load(state.gameboy_skin)
    if gameboy is None:
        gameboy = _load("gameboy/frames/gameboy-basic-01.png")
    if gameboy is None:
        gameboy = Image.new('RGBA', (FRAME_W, FRAME_H), (77, 155, 230, 255))

    gif_frames = []
    for anim_frame in range(NUM_FRAMES):
        canvas = Image.new('RGBA', (FRAME_W, FRAME_H), (0, 0, 0, 0))
        scene = compose_farm_scene(state, anim_frame)
        canvas.paste(scene, (SCREEN_X, SCREEN_Y))
        canvas.alpha_composite(gameboy)
        apply_screen_depth(canvas)

        if state.pet_state:
            draw_gameboy_ui(canvas, state.pet_state)

        rgb = Image.new('RGB', (FRAME_W, FRAME_H), (20, 20, 30))
        rgb.paste(canvas, mask=canvas.split()[3])
        gif_frames.append(rgb)

    out = io.BytesIO()
    gif_frames[0].save(out, format='GIF', save_all=True,
                        append_images=gif_frames[1:],
                        duration=GIF_FRAME_DURATION, loop=0, optimize=False)
    out.seek(0)
    return out.getvalue()


# --- AI-REPLACED (2026-03-16) ---
# Reason: Fullscreen now shows the upper half of the Gameboy frame (skin-specific bezel + screen)
#   cropped just below the screen, then upscaled 3x. This keeps the "device" look with the user's
#   chosen skin while giving a large, clear farm view. Old version showed no frame at all.
# What the new code does better: Users see their Gameboy skin in fullscreen; each skin looks unique.
# --- Original code (commented out for rollback) ---
# FULLSCREEN_SIZE = 800
#
# def render_farm_fullscreen(state: FarmState) -> bytes:
#     """Render farm scene at 800x800 with crispy nearest-neighbor upscale, no Gameboy frame."""
#     gif_frames = []
#     for anim_frame in range(NUM_FRAMES):
#         scene = compose_farm_scene(state, anim_frame)
#         upscaled = scene.resize((FULLSCREEN_SIZE, FULLSCREEN_SIZE), Image.Resampling.NEAREST)
#         rgb = Image.new('RGB', (FULLSCREEN_SIZE, FULLSCREEN_SIZE), (20, 20, 30))
#         rgb.paste(upscaled, mask=upscaled.split()[3])
#         gif_frames.append(rgb)
#
#     out = io.BytesIO()
#     gif_frames[0].save(out, format='GIF', save_all=True,
#                         append_images=gif_frames[1:],
#                         duration=GIF_FRAME_DURATION, loop=0, optimize=False)
#     out.seek(0)
#     return out.getvalue()
# --- End original code ---

FULLSCREEN_CROP_Y = 244
FULLSCREEN_SCALE = 3

def render_farm_fullscreen(state: FarmState) -> bytes:
    """Render farm inside the upper half of the Gameboy frame, upscaled 3x.

    The frame is cropped at y=244 (just below the screen), keeping the
    skin-specific bezel so it still looks like a device. The bottom panel
    (name, bars, currency) is cut off for a cleaner, bigger view.
    """
    gameboy = _load(state.gameboy_skin)
    if gameboy is None:
        gameboy = _load("gameboy/frames/gameboy-basic-01.png")
    if gameboy is None:
        gameboy = Image.new('RGBA', (FRAME_W, FRAME_H), (77, 155, 230, 255))

    cropped_h = min(FULLSCREEN_CROP_Y, gameboy.height)
    out_w = FRAME_W * FULLSCREEN_SCALE
    out_h = cropped_h * FULLSCREEN_SCALE

    gif_frames = []
    for anim_frame in range(NUM_FRAMES):
        canvas = Image.new('RGBA', (FRAME_W, cropped_h), (0, 0, 0, 0))

        scene = compose_farm_scene(state, anim_frame)
        canvas.paste(scene, (SCREEN_X, SCREEN_Y))

        frame_crop = gameboy.crop((0, 0, FRAME_W, cropped_h))
        canvas.alpha_composite(frame_crop)
        apply_screen_depth(canvas)

        upscaled = canvas.resize((out_w, out_h), Image.Resampling.NEAREST)

        rgb = Image.new('RGB', (out_w, out_h), (20, 20, 30))
        rgb.paste(upscaled, mask=upscaled.split()[3])
        gif_frames.append(rgb)

    out = io.BytesIO()
    gif_frames[0].save(out, format='GIF', save_all=True,
                        append_images=gif_frames[1:],
                        duration=GIF_FRAME_DURATION, loop=0, optimize=False)
    out.seek(0)
    return out.getvalue()
# --- END AI-REPLACED ---

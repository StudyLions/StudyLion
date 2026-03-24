# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: LionGotchi onboarding preview GIF renderer.
#          Generates animated showcase GIFs for the onboarding
#          tutorial, first encounter, and teaser messages using
#          the existing pet/farm rendering pipeline.
# ============================================================
import io
import math
import asyncio
import logging
from typing import Optional
from pathlib import Path

from PIL import Image, ImageDraw

from .renderer import (
    PetState,
    compose_full_scene,
    draw_gameboy_ui,
    apply_screen_depth,
    _load_asset,
    _get_font,
    _draw_outlined_text,
    FRAME_W, FRAME_H,
    SCREEN_X, SCREEN_Y, SCREEN_W, SCREEN_H,
    ANIMATION_FRAMES, GIF_FRAME_DURATION,
)
from .farm_renderer import FarmState, compose_farm_scene

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / 'assets'

SPARKLE_OFFSETS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

UPSCALE = 2
OUT_W = FRAME_W * UPSCALE
OUT_H = FRAME_H * UPSCALE


def _draw_sparkle(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple):
    pts = []
    for angle_deg in range(0, 360, 45):
        angle = math.radians(angle_deg)
        r = size if angle_deg % 90 == 0 else size // 3
        pts.append((cx + int(r * math.cos(angle)), cy + int(r * math.sin(angle))))
    if len(pts) >= 3:
        draw.polygon(pts, fill=color)


def _draw_hearts(draw: ImageDraw.ImageDraw, frame_idx: int, positions: list[tuple]):
    font = _get_font(14)
    for i, (bx, by) in enumerate(positions):
        phase = (frame_idx * 2 + i * 3) % 16
        y = by - phase * 4
        alpha = max(0, 255 - phase * 16)
        if alpha <= 0:
            continue
        wobble = int(math.sin(phase * 0.6 + i) * 6)
        _draw_outlined_text(
            draw, (bx + wobble, y), "\u2665", font,
            fill=(255, 100, 120, alpha), outline=(120, 30, 40, alpha)
        )


def _render_gameboy_gif(state: PetState, overlay_fn=None, frames: int = 8,
                        duration: int = 200) -> bytes:
    gameboy = _load_asset(state.gameboy_skin)
    if gameboy is None:
        gameboy = _load_asset("gameboy/frames/gameboy-basic-01.png")
    if gameboy is None:
        gameboy = Image.new('RGBA', (FRAME_W, FRAME_H), (77, 155, 230, 255))

    gif_frames = []
    for frame_idx in range(frames):
        canvas = Image.new('RGBA', (FRAME_W, FRAME_H), (0, 0, 0, 0))
        scene = compose_full_scene(state, frame_idx % ANIMATION_FRAMES)
        canvas.paste(scene, (SCREEN_X, SCREEN_Y))
        canvas.alpha_composite(gameboy)
        apply_screen_depth(canvas)
        draw_gameboy_ui(canvas, state)

        if overlay_fn:
            overlay = Image.new('RGBA', (FRAME_W, FRAME_H), (0, 0, 0, 0))
            overlay_fn(ImageDraw.Draw(overlay), frame_idx, overlay)
            canvas.alpha_composite(overlay)

        upscaled = canvas.resize((OUT_W, OUT_H), Image.Resampling.NEAREST)
        rgb = Image.new('RGB', (OUT_W, OUT_H), (20, 20, 30))
        rgb.paste(upscaled, mask=upscaled.split()[3])
        gif_frames.append(rgb)

    output = io.BytesIO()
    gif_frames[0].save(
        output, format='GIF', save_all=True,
        append_images=gif_frames[1:],
        duration=duration, loop=0, optimize=False,
    )
    output.seek(0)
    return output.getvalue()


def _render_welcome() -> bytes:
    state = PetState(
        pet_name="Leo",
        guild_name="",
        level=12,
        food=8, bath=8, sleep=7, life=8,
        gold=4280, gems=150,
        expression="happy",
        room_prefix="rooms/castle",
        room_furniture={
            'wall': 'rooms/castle/wall_1.png',
            'floor': 'rooms/castle/floor_1.png',
            'mat': 'rooms/castle/carpet_1.png',
            'bed': 'rooms/castle/bed_1.png',
            'chair': 'rooms/castle/chair_1.png',
            'table': 'rooms/castle/desk_1.png',
            'lamp': 'rooms/castle/lamp_1.png',
        },
        equipped_items={
            'head': 'equipment/hats/crown.png',
            'back': 'equipment/wings/angel_wings_gold.png',
        },
        gameboy_skin="gameboy/frames/gameboy-candy-01.png",
    )

    sparkle_pos = [
        (45, 50), (200, 65), (55, 180), (185, 170),
        (120, 45), (80, 140), (175, 120), (140, 190),
    ]
    heart_pos = [
        (50, 100), (195, 90), (100, 60), (165, 155),
    ]

    def overlay(draw, frame_idx, overlay_img):
        for i, (sx, sy) in enumerate(sparkle_pos):
            phase = (frame_idx + i * 2) % 8
            size = max(2, 7 - phase)
            alpha = max(0, 255 - phase * 28)
            dy = -phase * 3
            _draw_sparkle(draw, sx, sy + dy, size, (255, 240, 100, alpha))
        _draw_hearts(draw, frame_idx, heart_pos)

    return _render_gameboy_gif(state, overlay_fn=overlay, frames=8, duration=200)


def _render_care() -> bytes:
    state = PetState(
        pet_name="Mochi",
        guild_name="",
        level=5,
        food=4, bath=3, sleep=6, life=5,
        gold=820, gems=25,
        expression="default",
        room_prefix="rooms/default",
        room_furniture={
            'wall': 'rooms/default/wall_stripe_light_blue.png',
            'floor': 'rooms/default/floor_blue.png',
            'mat': 'rooms/default/mat_blue.png',
            'bed': 'rooms/default/bed_red.png',
            'chair': 'rooms/default/chair_brown.png',
            'table': 'rooms/default/table_brown.png',
            'lamp': 'rooms/default/lamp_yellow.png',
            'window': 'rooms/default/window_blue.png',
        },
        equipped_items={},
        gameboy_skin="gameboy/frames/gameboy-basic-01.png",
    )

    care_sparkles = [
        (90, 80), (150, 70), (110, 150), (60, 130),
        (170, 140), (130, 60), (80, 170), (160, 100),
    ]

    def overlay(draw, frame_idx, overlay_img):
        if frame_idx >= 4:
            bar_phase = frame_idx - 4
            state.food = min(8, 4 + bar_phase)
            state.bath = min(8, 3 + bar_phase)
            for i, (sx, sy) in enumerate(care_sparkles):
                phase = (frame_idx - 4 + i) % 4
                size = max(2, 6 - phase)
                alpha = max(0, 240 - phase * 50)
                _draw_sparkle(draw, sx, sy - phase * 5, size, (120, 255, 120, alpha))

    return _render_gameboy_gif(state, overlay_fn=overlay, frames=8, duration=300)


def _render_equipment() -> bytes:
    state = PetState(
        pet_name="Titan",
        guild_name="",
        level=25,
        food=7, bath=8, sleep=8, life=8,
        gold=15400, gems=680,
        expression="happy",
        room_prefix="rooms/library",
        room_furniture={
            'wall': 'rooms/library/wall_2.png',
            'floor': 'rooms/library/floor_2.png',
            'mat': 'rooms/library/carpet_2.png',
        },
        equipped_items={
            'head': 'equipment/hats/crown2.png',
            'face': 'equipment/glasses/anonymous_mask_epic.png',
            'body': 'equipment/shirts/aot_shirt_aot_shirt_epic.png',
            'back': 'equipment/wings/butterfly_wings_gold.png',
            'feet': 'equipment/boots/boots_boots_legendary_.png',
        },
        gameboy_skin="gameboy/frames/fire/red.png",
    )

    sparkle_pos = [
        (70, 70), (170, 80), (100, 45), (190, 160),
        (50, 150), (140, 180), (210, 50), (130, 100),
    ]

    def overlay(draw, frame_idx, overlay_img):
        for i, (sx, sy) in enumerate(sparkle_pos):
            phase = (frame_idx + i * 3) % 8
            size = max(2, 8 - phase)
            alpha = max(0, 255 - phase * 30)
            colors = [
                (255, 215, 0, alpha),
                (160, 100, 255, alpha),
                (255, 100, 60, alpha),
                (80, 200, 255, alpha),
            ]
            _draw_sparkle(draw, sx, sy - phase * 2, size, colors[i % len(colors)])

    return _render_gameboy_gif(state, overlay_fn=overlay, frames=8, duration=200)


def _render_farm() -> bytes:
    plots = [
        {'plot_num': 0, 'seed_id': 1, 'growth_stage': 5, 'plant_type': 'tree',
         'type_id': 1, 'rarity': 'COMMON', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 1, 'seed_id': 2, 'growth_stage': 4, 'plant_type': 'tree',
         'type_id': 2, 'rarity': 'UNCOMMON', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 2, 'seed_id': 3, 'growth_stage': 3, 'plant_type': 'tree',
         'type_id': 3, 'rarity': 'COMMON', 'is_watered': False, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 3, 'seed_id': 4, 'growth_stage': 5, 'plant_type': 'tree',
         'type_id': 4, 'rarity': 'RARE', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 4, 'seed_id': 5, 'growth_stage': 4, 'plant_type': 'tree',
         'type_id': 5, 'rarity': 'COMMON', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 5, 'seed_id': 6, 'growth_stage': 2, 'plant_type': 'tree',
         'type_id': 6, 'rarity': 'COMMON', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 6, 'seed_id': 7, 'growth_stage': 5, 'plant_type': 'tree',
         'type_id': 7, 'rarity': 'EPIC', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 7, 'seed_id': 8, 'growth_stage': 3, 'plant_type': 'tree',
         'type_id': 8, 'rarity': 'COMMON', 'is_watered': False, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 8, 'seed_id': 9, 'growth_stage': 4, 'plant_type': 'tree',
         'type_id': 9, 'rarity': 'UNCOMMON', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 9, 'seed_id': 10, 'growth_stage': 1, 'plant_type': 'tree',
         'type_id': 10, 'rarity': 'COMMON', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 10, 'seed_id': 11, 'growth_stage': 5, 'plant_type': 'tree',
         'type_id': 11, 'rarity': 'LEGENDARY', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 11, 'seed_id': 12, 'growth_stage': 3, 'plant_type': 'tree',
         'type_id': 12, 'rarity': 'COMMON', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 12, 'seed_id': 13, 'growth_stage': 2, 'plant_type': 'tree',
         'type_id': 13, 'rarity': 'COMMON', 'is_watered': False, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 13, 'seed_id': 14, 'growth_stage': 4, 'plant_type': 'tree',
         'type_id': 14, 'rarity': 'RARE', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
        {'plot_num': 14, 'seed_id': 15, 'growth_stage': 5, 'plant_type': 'tree',
         'type_id': 15, 'rarity': 'COMMON', 'is_watered': True, 'dead': False, 'asset_prefix': ''},
    ]

    pet_state = PetState(
        pet_name="Sprout",
        level=8,
        food=7, bath=7, sleep=6, life=7,
        gold=2100, gems=90,
        expression="happy",
    )

    farm_state = FarmState(
        plots=plots,
        is_night=False,
        just_watered=False,
        gameboy_skin="gameboy/frames/flower/flower_1.png",
        pet_state=pet_state,
    )

    gameboy = _load_asset(farm_state.gameboy_skin)
    if gameboy is None:
        gameboy = _load_asset("gameboy/frames/gameboy-basic-01.png")
    if gameboy is None:
        gameboy = Image.new('RGBA', (FRAME_W, FRAME_H), (77, 155, 230, 255))

    num_frames = 8
    frame_duration = 150
    gif_frames = []

    for anim_frame in range(num_frames):
        canvas = Image.new('RGBA', (FRAME_W, FRAME_H), (0, 0, 0, 0))
        scene = compose_farm_scene(farm_state, anim_frame * 2)
        canvas.paste(scene, (SCREEN_X, SCREEN_Y))
        canvas.alpha_composite(gameboy)
        apply_screen_depth(canvas)
        draw_gameboy_ui(canvas, pet_state)

        upscaled = canvas.resize((OUT_W, OUT_H), Image.Resampling.NEAREST)
        rgb = Image.new('RGB', (OUT_W, OUT_H), (20, 20, 30))
        rgb.paste(upscaled, mask=upscaled.split()[3])
        gif_frames.append(rgb)

    output = io.BytesIO()
    gif_frames[0].save(
        output, format='GIF', save_all=True,
        append_images=gif_frames[1:],
        duration=frame_duration, loop=0, optimize=False,
    )
    output.seek(0)
    return output.getvalue()


ONBOARDING_RENDERERS = {
    'welcome': _render_welcome,
    'care': _render_care,
    'equipment': _render_equipment,
    'farm': _render_farm,
}


class OnboardingGIFs:
    """Pre-renders and caches onboarding showcase GIFs using the pet/farm pipelines."""

    def __init__(self):
        self._cache: dict[str, bytes] = {}

    async def get(self, name: str) -> bytes:
        if name not in self._cache:
            renderer = ONBOARDING_RENDERERS.get(name)
            if renderer is None:
                renderer = ONBOARDING_RENDERERS['welcome']
            self._cache[name] = await asyncio.to_thread(renderer)
        return self._cache[name]

    async def preload_all(self):
        for name in ONBOARDING_RENDERERS:
            if name not in self._cache:
                try:
                    self._cache[name] = await asyncio.to_thread(
                        ONBOARDING_RENDERERS[name]
                    )
                except Exception:
                    logger.exception(f"Failed to pre-render onboarding GIF: {name}")

    @property
    def available(self) -> list[str]:
        return list(ONBOARDING_RENDERERS.keys())

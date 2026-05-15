# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-15
# Purpose: LionGotchi Gameboy-style pet renderer
#          Composites room scene + pet + equipment inside a
#          260x400 Gameboy frame, outputs animated GIF
# ============================================================
import io
import logging
from typing import Optional
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / 'assets'

FRAME_W = 260
FRAME_H = 400

SCREEN_X = 30
SCREEN_Y = 36
SCREEN_W = 200
SCREEN_H = 200

NAME_X = 37
NAME_Y = 250
LEVEL_SLOT_X = 181
LEVEL_SLOT_Y = 247
ITEM_SLOTS_X = 65
ITEM_SLOTS_Y = 271

BAR_X = 54
BAR_Y_START = 285
BAR_SPACING = 20
# --- AI-REPLACED (2026-03-19) ---
# Reason: Stat redesign -- mood bar replaces life bar (reuses life_bars assets)
# --- Original code (commented out for rollback) ---
# BAR_ORDER = ['life', 'sleep', 'food', 'bath']
# --- End original code ---
BAR_ORDER = ['mood', 'sleep', 'food', 'bath']
# --- END AI-REPLACED ---

# --- AI-REPLACED (2026-03-20) ---
# Reason: Replace GLOBAL/SERVER labels with coin/gem icons aligned next to numbers
# --- Original code (commented out for rollback) ---
# GLOBAL_LABEL_X = 22
# GLOBAL_LABEL_Y = 369
# SERVER_LABEL_X = 157
# SERVER_LABEL_Y = 369
# CURRENCY_Y = 379
# CURRENCY_LEFT_X = 47
# CURRENCY_RIGHT_X = 182
# --- End original code ---
CURRENCY_ICON_SIZE = 12
COIN_ICON_X = 33
GEM_ICON_X = 168
CURRENCY_ICON_Y = 379
CURRENCY_Y = 379
CURRENCY_LEFT_X = 47
CURRENCY_RIGHT_X = 182
# --- END AI-REPLACED ---

ANIMATION_FRAMES = 4
GIF_FRAME_DURATION = 250

ROOM_LAYERS = ['wall', 'floor', 'mat', 'table', 'chair', 'bed', 'lamp', 'picture', 'window']

_asset_cache: dict[str, Optional[Image.Image]] = {}
_font_cache: dict[str, ImageFont.FreeTypeFont] = {}

STROKE_OFFSETS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Screen depth overlay giving the Gameboy screen a recessed 3D look
#   with inner bevel shadow, faint LCD scanlines, and glass glare highlight
_screen_depth_overlay: Optional[Image.Image] = None

def _build_screen_depth() -> Image.Image:
    """Build a 200x200 RGBA overlay with inner shadow, scanlines, and glass glare."""
    overlay = Image.new('RGBA', (SCREEN_W, SCREEN_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for d in range(6):
        t = 1 - d / 6
        tl_alpha = int(60 * t)
        br_alpha = int(28 * t)
        draw.line([(d, d), (SCREEN_W - 1 - d, d)], fill=(0, 0, 0, tl_alpha))
        draw.line([(d, d + 1), (d, SCREEN_H - 1 - d)], fill=(0, 0, 0, tl_alpha))
        draw.line([(d, SCREEN_H - 1 - d), (SCREEN_W - 1 - d, SCREEN_H - 1 - d)], fill=(0, 0, 0, br_alpha))
        draw.line([(SCREEN_W - 1 - d, d + 1), (SCREEN_W - 1 - d, SCREEN_H - 2 - d)], fill=(0, 0, 0, br_alpha))

    for y in range(0, SCREEN_H, 2):
        draw.line([(0, y), (SCREEN_W - 1, y)], fill=(0, 0, 0, 14))

    for i in range(8):
        alpha = max(1, 20 - abs(i - 4) * 4)
        x0 = 12 + i * 3
        x1 = SCREEN_W // 2 + 5 + i * 3
        draw.line([(x0, 0), (x1, SCREEN_H // 3)], fill=(255, 255, 255, alpha))

    return overlay


def apply_screen_depth(canvas: Image.Image) -> None:
    """Composite the cached screen-depth overlay onto canvas at the screen position."""
    global _screen_depth_overlay
    if _screen_depth_overlay is None:
        _screen_depth_overlay = _build_screen_depth()
    canvas.alpha_composite(_screen_depth_overlay, (SCREEN_X, SCREEN_Y))
# --- END AI-MODIFIED ---


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


def _draw_outlined_text(draw: ImageDraw.ImageDraw, pos: tuple[int, int], text: str,
                         font: ImageFont.FreeTypeFont, fill=(255, 255, 255),
                         outline=(0, 0, 0), stroke_width=1):
    """Draw text with a pixel-art style black outline by rendering at surrounding offsets."""
    x, y = pos
    for sw in range(1, stroke_width + 1):
        for dx, dy in STROKE_OFFSETS:
            draw.text((x + dx * sw, y + dy * sw), text, fill=outline, font=font)
    draw.text((x, y), text, fill=fill, font=font)


class PetState:
    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Add room_layout parameter for custom furniture positions,
    #          flips, lion position, layer order, and equipment order
    #          from the website room editor (lg_room_layout table)
    def __init__(
        self,
        pet_name: str = "Leo",
        guild_name: str = "",
        level: int = 1,
        food: int = 8,
        bath: int = 8,
        sleep: int = 8,
        life: int = 8,
        gold: int = 0,
        gems: int = 0,
        expression: str = "default",
        room_prefix: str = "rooms/default",
        room_furniture: Optional[dict] = None,
        equipped_items: Optional[dict] = None,
        gameboy_skin: str = "gameboy/frames/gameboy-basic-01.png",
        room_layout: Optional[dict] = None,
    ):
        self.pet_name = pet_name
        self.guild_name = guild_name
        self.level = level
        self.food = food
        self.bath = bath
        self.sleep = sleep
        self.life = life
        self.gold = gold
        self.gems = gems
        self.expression = expression
        self.room_prefix = room_prefix
        self.room_furniture = room_furniture or {}
        self.equipped_items = equipped_items or {}
        self.gameboy_skin = gameboy_skin
        self.room_layout = room_layout or {}
    # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Stat redesign -- expression driven by mood (avg of 3 needs) instead of individual stats
    # What the new code does better: Consistent mood-based expressions, cleaner priority
    # --- Original code (commented out for rollback) ---
    # def auto_expression(self) -> str:
    #     if self.life <= 1: return "sick"
    #     if self.sleep <= 1: return "sleeping"
    #     if self.food <= 1: return "sad"
    #     if self.bath <= 1: return "sad"
    #     return self.expression
    # --- End original code ---
    @property
    def mood(self) -> int:
        return (self.food + self.bath + self.sleep) // 3

    def auto_expression(self) -> str:
        m = self.mood
        if m == 0:
            return "sick"
        if m <= 2:
            return "sad"
        if m <= 4:
            return "sad"
        if m <= 6:
            return self.expression
        return "happy"
    # --- END AI-REPLACED ---


def compose_room_scene(state: PetState) -> Image.Image:
    scene = Image.new('RGBA', (SCREEN_W, SCREEN_H), (0, 0, 0, 255))

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Use custom layer order and apply furniture offsets/flips
    #          from room_layout when rendering the room scene
    layer_order = state.room_layout.get('layerOrder', ROOM_LAYERS)
    furniture_offsets = state.room_layout.get('furnitureOffsets', {})
    furniture_flips = state.room_layout.get('furnitureFlips', {})
    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Support per-layer scaling from the room editor
    furniture_scales = state.room_layout.get('furnitureScales', {})
    # --- END AI-MODIFIED ---

    for layer_name in layer_order:
        if layer_name not in ROOM_LAYERS:
            continue
        override = state.room_furniture.get(layer_name)
        if override:
            asset_path = override
        else:
            prefix = state.room_prefix
            candidates = [
                f"{prefix}/{layer_name}.png",
            ]
            asset_path = None
            for c in candidates:
                if (ASSETS_DIR / c).exists():
                    asset_path = c
                    break

            if asset_path is None:
                search_dir = ASSETS_DIR / prefix
                if search_dir.exists():
                    for f in search_dir.iterdir():
                        if f.stem.lower().startswith(layer_name) and f.suffix == '.png':
                            asset_path = f"{prefix}/{f.name}"
                            break

        if asset_path:
            layer = _load_asset(asset_path)
            if layer:
                if layer.size != (SCREEN_W, SCREEN_H):
                    layer = layer.resize((SCREEN_W, SCREEN_H), Image.Resampling.NEAREST)

                if furniture_flips.get(layer_name, False):
                    layer = layer.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

                # --- AI-REPLACED (2026-03-25) ---
                # Reason: Scale + offset were applied in two separate steps, each
                #   clipping to 200x200. This double-clip lost pixels that the
                #   website's single-pass canvas transform preserves.
                # What the new code does better: Combines scale centering and
                #   user offset into one composite call so clipping happens once,
                #   matching the website renderer exactly.
                # --- Original code (commented out for rollback) ---
                # layer_scale = furniture_scales.get(layer_name, 1.0)
                # if layer_scale != 1.0 and layer_scale > 0:
                #     new_w = max(1, int(SCREEN_W * layer_scale))
                #     new_h = max(1, int(SCREEN_H * layer_scale))
                #     scaled = layer.resize((new_w, new_h), Image.Resampling.NEAREST)
                #     layer = Image.new('RGBA', (SCREEN_W, SCREEN_H), (0, 0, 0, 0))
                #     paste_x = (SCREEN_W - new_w) // 2
                #     paste_y = (SCREEN_H - new_h) // 2
                #     layer.alpha_composite(scaled, (paste_x, paste_y))
                #
                # offset = furniture_offsets.get(layer_name)
                # if offset and (offset[0] != 0 or offset[1] != 0):
                #     offset_canvas = Image.new('RGBA', (SCREEN_W, SCREEN_H), (0, 0, 0, 0))
                #     ox, oy = int(offset[0]), int(offset[1])
                #     offset_canvas.alpha_composite(layer, (ox, oy))
                #     scene.alpha_composite(offset_canvas)
                # else:
                #     scene.alpha_composite(layer)
                # --- End original code ---
                layer_scale = furniture_scales.get(layer_name, 1.0)
                offset = furniture_offsets.get(layer_name)
                ox = int(offset[0]) if offset else 0
                oy = int(offset[1]) if offset else 0

                if layer_scale != 1.0 and layer_scale > 0:
                    new_w = max(1, int(SCREEN_W * layer_scale))
                    new_h = max(1, int(SCREEN_H * layer_scale))
                    scaled = layer.resize((new_w, new_h), Image.Resampling.NEAREST)
                    cx = (SCREEN_W - new_w) // 2 + ox
                    cy = (SCREEN_H - new_h) // 2 + oy
                    src_x = max(0, -cx)
                    src_y = max(0, -cy)
                    dst_x = max(0, cx)
                    dst_y = max(0, cy)
                    paste_w = min(new_w - src_x, SCREEN_W - dst_x)
                    paste_h = min(new_h - src_y, SCREEN_H - dst_y)
                    if paste_w > 0 and paste_h > 0:
                        region = scaled.crop((src_x, src_y, src_x + paste_w, src_y + paste_h))
                        scene.alpha_composite(region, (dst_x, dst_y))
                elif ox != 0 or oy != 0:
                    src_x = max(0, -ox)
                    src_y = max(0, -oy)
                    dst_x = max(0, ox)
                    dst_y = max(0, oy)
                    paste_w = min(SCREEN_W - src_x, SCREEN_W - dst_x)
                    paste_h = min(SCREEN_H - src_y, SCREEN_H - dst_y)
                    if paste_w > 0 and paste_h > 0:
                        region = layer.crop((src_x, src_y, src_x + paste_w, src_y + paste_h))
                        scene.alpha_composite(region, (dst_x, dst_y))
                else:
                    scene.alpha_composite(layer)
                # --- END AI-REPLACED ---
    # --- END AI-MODIFIED ---

    return scene


# --- AI-MODIFIED (2026-03-17) ---
# Purpose: Interleaved render sequence -- equipment drawn between lion body
#          layers instead of all on top, with per-slot position offsets and
#          animated equipment frame extraction from GIFs.
DEFAULT_RENDER_SEQUENCE = [
    {'type': 'lion', 'key': 'body'},
    {'type': 'equip', 'key': 'feet'},
    {'type': 'equip', 'key': 'body'},
    {'type': 'lion', 'key': 'head'},
    {'type': 'lion', 'key': 'expression'},
    {'type': 'equip', 'key': 'face'},
    {'type': 'lion', 'key': 'hair'},
    {'type': 'equip', 'key': 'head'},
]

SLOT_UPPER_TO_LOWER = {'HEAD': 'head', 'FACE': 'face', 'BODY': 'body', 'BACK': 'back', 'FEET': 'feet'}

_gif_frame_cache: dict[str, dict[int, Optional[Image.Image]]] = {}


def _load_equip_frame(asset_path: str, frame_idx: int) -> Optional[Image.Image]:
    """Load a specific animation frame from an equipment asset.

    For GIF files, extracts the requested frame. For PNGs, tries
    {base}_{frame_num}.png first, then falls back to the static image.
    """
    frame_num = (frame_idx % ANIMATION_FRAMES) + 1

    if asset_path.lower().endswith('.gif'):
        cache_key = asset_path
        if cache_key not in _gif_frame_cache:
            _gif_frame_cache[cache_key] = {}
            full_path = ASSETS_DIR / asset_path
            if full_path.exists():
                try:
                    from PIL import ImageSequence
                    gif = Image.open(full_path)
                    for i, gif_frame in enumerate(ImageSequence.Iterator(gif)):
                        _gif_frame_cache[cache_key][i] = gif_frame.convert('RGBA').copy()
                except Exception:
                    pass
        frames = _gif_frame_cache.get(cache_key, {})
        if frame_idx in frames:
            return frames[frame_idx].copy()
        if frames:
            return list(frames.values())[frame_idx % len(frames)].copy()
        return None

    dot_idx = asset_path.rfind('.')
    if dot_idx != -1:
        base = asset_path[:dot_idx]
        ext = asset_path[dot_idx:]
    else:
        base = asset_path
        ext = '.png'
    frame_path = f"{base}_{frame_num}{ext}"
    frame_img = _load_asset(frame_path)
    if frame_img:
        return frame_img

    return _load_asset(asset_path)


def _build_render_sequence(state: PetState) -> list[dict]:
    """Build the render sequence from room_layout, falling back to defaults."""
    saved = state.room_layout.get('renderSequence')
    equipped = state.equipped_items
    equipped_lower = set(equipped.keys()) - {'back'}

    if saved and isinstance(saved, list) and len(saved) > 0:
        result = []
        placed = set()
        for step in saved:
            stype = step.get('type', '')
            skey = step.get('key', '')
            if stype == 'lion':
                result.append({'type': 'lion', 'key': skey})
            elif stype == 'equip':
                slot_lower = SLOT_UPPER_TO_LOWER.get(skey, skey.lower())
                if slot_lower in equipped_lower:
                    result.append({'type': 'equip', 'key': slot_lower})
                    placed.add(slot_lower)

        lion_keys = {'body', 'head', 'expression', 'hair'}
        for k in ['body', 'head', 'expression', 'hair']:
            if not any(s['type'] == 'lion' and s['key'] == k for s in result):
                result.append({'type': 'lion', 'key': k})

        for slot in equipped_lower:
            if slot not in placed:
                for ds in DEFAULT_RENDER_SEQUENCE:
                    if ds['type'] == 'equip' and ds['key'] == slot:
                        before_lions = [s for s in DEFAULT_RENDER_SEQUENCE[:DEFAULT_RENDER_SEQUENCE.index(ds)]
                                        if s['type'] == 'lion']
                        if before_lions:
                            anchor = before_lions[-1]['key']
                            idx = next((i for i, s in enumerate(result)
                                       if s['type'] == 'lion' and s['key'] == anchor), -1)
                            if idx != -1:
                                result.insert(idx + 1, {'type': 'equip', 'key': slot})
                                break
                else:
                    result.append({'type': 'equip', 'key': slot})

        return result

    return [s for s in DEFAULT_RENDER_SEQUENCE
            if s['type'] == 'lion' or s['key'] in equipped_lower]


# --- Original code (commented out for rollback) ---
# def compose_pet_sprite(state: PetState, frame_idx: int) -> Image.Image:
#     frame_num = (frame_idx % ANIMATION_FRAMES) + 1
#     pet_canvas = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
#     body = _load_asset(f"lion/body/body_{frame_num}.png")
#     if body: pet_canvas.alpha_composite(body)
#     head = _load_asset(f"lion/head/head_{frame_num}.png")
#     if head: pet_canvas.alpha_composite(head)
#     hair = _load_asset(f"lion/hair/hair_{frame_num}.png")
#     if hair: pet_canvas.alpha_composite(hair)
#     expr = state.auto_expression()
#     face = _load_asset(f"lion/expressions/{expr}/face_{frame_num}.png")
#     if face: pet_canvas.alpha_composite(face)
#     equipped = state.equipped_items
#     equip_order = state.room_layout.get('equipmentOrder', ['body', 'face', 'head'])
#     for slot in equip_order:
#         if slot == 'back': continue
#         if slot in equipped:
#             item_img = _load_asset(equipped[slot])
#             if item_img:
#                 if item_img.size != (64, 64):
#                     item_img = item_img.resize((64, 64), Image.Resampling.NEAREST)
#                 pet_canvas.alpha_composite(item_img)
#     return pet_canvas
# --- End original code ---


def compose_pet_sprite(state: PetState, frame_idx: int):
    """Compose the pet sprite with equipment on a canvas tall enough to fit
    oversized equipment (e.g. 65x88 hats). Returns (image, y_offset) where
    y_offset is how many extra rows sit above the standard 64x64 area."""
    frame_num = (frame_idx % ANIMATION_FRAMES) + 1

    expr = state.auto_expression()
    equipped = state.equipped_items
    equip_offsets = state.room_layout.get('equipmentOffsets', {})
    sequence = _build_render_sequence(state)

    # --- AI-REPLACED (2026-03-24) ---
    # Reason: Fixed-size 64x64 canvas crops tall equipment (hats extend above
    #         the lion). Now uses an expanded canvas that preserves all content,
    #         with the lion offset downward to match the oversized coordinate system.
    # --- Original code (commented out for rollback) ---
    # pet_canvas = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    # ... (original compose_pet_sprite body -- see git history)
    # return pet_canvas
    # --- End original code ---

    max_h = 64
    for slot, path in equipped.items():
        if slot == 'back':
            continue
        img = _load_equip_frame(path, frame_idx)
        if img and img.height > max_h:
            max_h = img.height

    extra_top = max_h - 64
    canvas_w = 64
    canvas_h = 64 + extra_top
    pet_canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))

    for step in sequence:
        if step['type'] == 'lion':
            part = step['key']
            if part == 'expression':
                img = _load_asset(f"lion/expressions/{expr}/face_{frame_num}.png")
            else:
                img = _load_asset(f"lion/{part}/{part}_{frame_num}.png")
            if img:
                pet_canvas.alpha_composite(img, (0, extra_top))
        else:
            slot = step['key']
            if slot == 'back':
                continue
            if slot in equipped:
                item_img = _load_equip_frame(equipped[slot], frame_idx)
                if item_img:
                    iw, ih = item_img.size
                    is_oversized = (iw != 64 or ih != 64)

                    slot_upper = slot.upper()
                    offset = equip_offsets.get(slot_upper, equip_offsets.get(slot, None))
                    ox = int(offset[0]) if offset else 0
                    oy = int(offset[1]) if offset else 0
                    ox = max(-16, min(16, ox))
                    oy = max(-16, min(16, oy))

                    if is_oversized:
                        cx = (canvas_w - iw) // 2
                        cy = canvas_h - ih
                        px = cx + ox
                        py = cy + oy
                        src_l = max(0, -px)
                        src_t = max(0, -py)
                        src_r = min(iw, canvas_w - px)
                        src_b = min(ih, canvas_h - py)
                        dst_x = max(0, px)
                        dst_y = max(0, py)
                        if src_r > src_l and src_b > src_t:
                            region = item_img.crop((src_l, src_t, src_r, src_b))
                            pet_canvas.alpha_composite(region, (dst_x, dst_y))
                    else:
                        draw_x = ox
                        draw_y = extra_top + oy
                        if draw_x == 0 and draw_y == extra_top:
                            pet_canvas.alpha_composite(item_img, (0, extra_top))
                        else:
                            offset_canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
                            px = max(0, draw_x)
                            py = max(0, draw_y)
                            if draw_x < 0 or draw_y < extra_top:
                                crop_l = max(0, -draw_x)
                                crop_t = max(0, extra_top - draw_y)
                                cropped = item_img.crop((crop_l, crop_t, 64, 64))
                                offset_canvas.alpha_composite(cropped, (px, py))
                            else:
                                offset_canvas.alpha_composite(item_img, (px, py))
                            pet_canvas.alpha_composite(offset_canvas)

    return pet_canvas, extra_top
    # --- END AI-REPLACED ---


def compose_full_scene(state: PetState, frame_idx: int) -> Image.Image:
    scene = compose_room_scene(state)

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Use custom lion position from room_layout instead of
    #          hardcoded center position, and support lion horizontal flip
    lion_pos = state.room_layout.get('lionPosition')
    if lion_pos and len(lion_pos) == 2:
        lion_x, lion_y = int(lion_pos[0]), int(lion_pos[1])
    else:
        lion_x = (SCREEN_W - 80) // 2
        lion_y = SCREEN_H - 80 - 15

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Apply lionScale from room layout to the pet sprite size
    lion_scale = state.room_layout.get('lionScale', 1.0)
    pet_size = max(1, int(80 * lion_scale))

    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: BACK slot with equipment offset support
    back_path = state.equipped_items.get('back')
    if back_path:
        wings = _load_equip_frame(back_path, frame_idx)
        if wings:
            target_h = pet_size
            ratio = target_h / wings.height
            target_w = int(wings.width * ratio)
            wings_scaled = wings.resize((target_w, target_h), Image.Resampling.NEAREST)
            equip_offsets = state.room_layout.get('equipmentOffsets', {})
            back_off = equip_offsets.get('BACK', equip_offsets.get('back', [0, 0]))
            boff_x = int(back_off[0]) if back_off else 0
            boff_y = int(back_off[1]) if back_off else 0
            wx = lion_x + (pet_size - wings_scaled.width) // 2 + boff_x
            wy = lion_y - int(15 * lion_scale) + boff_y
            scene.alpha_composite(wings_scaled, (max(0, wx), max(0, wy)))
    # --- END AI-MODIFIED ---

    # --- AI-REPLACED (2026-03-24) ---
    # Reason: compose_pet_sprite now returns an expanded canvas for tall
    #         equipment. Scale proportionally and offset so the lion body
    #         stays at (lion_x, lion_y) while tall hats extend above.
    # --- Original code (commented out for rollback) ---
    # pet = compose_pet_sprite(state, frame_idx)
    # pet_scaled = pet.resize((pet_size, pet_size), Image.Resampling.NEAREST)
    # lion_flipped = state.room_layout.get('furnitureFlips', {}).get('lion', False)
    # if lion_flipped:
    #     pet_scaled = pet_scaled.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    # scene.alpha_composite(pet_scaled, (max(0, lion_x), max(0, lion_y)))
    # --- End original code ---
    pet, y_off = compose_pet_sprite(state, frame_idx)
    scale_factor = pet_size / 64
    scaled_w = max(1, int(pet.width * scale_factor))
    scaled_h = max(1, int(pet.height * scale_factor))
    pet_scaled = pet.resize((scaled_w, scaled_h), Image.Resampling.NEAREST)

    lion_flipped = state.room_layout.get('furnitureFlips', {}).get('lion', False)
    if lion_flipped:
        pet_scaled = pet_scaled.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    paste_x = lion_x
    paste_y = lion_y - int(y_off * scale_factor)

    if paste_y < 0:
        crop_top = -paste_y
        pet_scaled = pet_scaled.crop((0, crop_top, scaled_w, scaled_h))
        paste_y = 0

    scene.alpha_composite(pet_scaled, (max(0, paste_x), max(0, paste_y)))
    # --- END AI-REPLACED ---
    # --- END AI-MODIFIED ---
    # --- END AI-MODIFIED ---

    return scene


def draw_gameboy_ui(canvas: Image.Image, state: PetState):
    """Draw the standard Gameboy UI panel (name, level, bars, currency) on a canvas.
    Shared by both pet and farm renderers so the UI stays consistent."""
    draw = ImageDraw.Draw(canvas)
    font_name = _get_font(18)
    font_guild = _get_font(12)
    font_level = _get_font(14)
    font_currency = _get_font(12)

    _draw_outlined_text(draw, (NAME_X, NAME_Y), state.pet_name.upper(), font=font_name)
    if state.guild_name:
        name_w = draw.textlength(state.pet_name.upper(), font=font_name)
        _draw_outlined_text(draw, (int(NAME_X + name_w + 4), NAME_Y + 4),
                             state.guild_name[:10], font=font_guild, fill=(220, 220, 240))

    level_slot = _load_asset("ui/level_slot.png")
    if level_slot:
        canvas.alpha_composite(level_slot, (LEVEL_SLOT_X, LEVEL_SLOT_Y))
    lv_text = f"lv. {state.level:02d}"
    lv_w = draw.textlength(lv_text, font=font_level)
    _draw_outlined_text(draw, (LEVEL_SLOT_X + (54 - int(lv_w)) // 2, LEVEL_SLOT_Y + 3),
                         lv_text, font=font_level)

    item_slots = _load_asset("ui/item_slots.png")
    if item_slots:
        canvas.alpha_composite(item_slots, (ITEM_SLOTS_X, ITEM_SLOTS_Y))

    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Stat redesign -- show mood bar (derived from avg) using life bar assets
    # What the new code does better: Mood replaces life in the Gameboy display
    # --- Original code (commented out for rollback) ---
    # bar_values = {'life': state.life, 'sleep': state.sleep, 'food': state.food, 'bath': state.bath}
    # for i, bar_name in enumerate(BAR_ORDER):
    #     bar_img = _load_asset(f"ui/bars/{bar_name}_bars_{val}_8.png")
    # --- End original code ---
    mood_val = state.mood
    bar_values = {'mood': mood_val, 'sleep': state.sleep, 'food': state.food, 'bath': state.bath}
    for i, bar_name in enumerate(BAR_ORDER):
        val = bar_values[bar_name]
        asset_name = 'life' if bar_name == 'mood' else bar_name
        bar_img = _load_asset(f"ui/bars/{asset_name}_bars_{val}_8.png")
        if bar_img:
            canvas.alpha_composite(bar_img, (BAR_X, BAR_Y_START + i * BAR_SPACING))
    # --- END AI-REPLACED ---

    # --- AI-REPLACED (2026-03-20) ---
    # Reason: Show coin + gem icons aligned with currency numbers instead of GLOBAL/SERVER labels
    # What the new code does better: Uses actual coin/gem pixel-art icons next to the numbers,
    #   shows user's gems instead of server coins
    # --- Original code (commented out for rollback) ---
    # global_label = _load_asset("ui/icons/global_label.png")
    # if global_label:
    #     global_label = global_label.resize((24, 18), Image.Resampling.NEAREST)
    #     canvas.alpha_composite(global_label, (GLOBAL_LABEL_X, GLOBAL_LABEL_Y))
    # server_label = _load_asset("ui/icons/server_label.png")
    # if server_label:
    #     server_label = server_label.resize((24, 18), Image.Resampling.NEAREST)
    #     canvas.alpha_composite(server_label, (SERVER_LABEL_X, SERVER_LABEL_Y))
    # gold_text = f"{state.gold:06d}"
    # coins_text = f"{state.server_coins:06d}"
    # _draw_outlined_text(draw, (CURRENCY_LEFT_X, CURRENCY_Y), gold_text, font=font_currency)
    # _draw_outlined_text(draw, (CURRENCY_RIGHT_X, CURRENCY_Y), coins_text, font=font_currency)
    # --- End original code ---
    icon_sz = (CURRENCY_ICON_SIZE, CURRENCY_ICON_SIZE)
    coin_icon = _load_asset("ui/icons/coin.png")
    if coin_icon:
        coin_icon = coin_icon.resize(icon_sz, Image.Resampling.NEAREST)
        canvas.alpha_composite(coin_icon, (COIN_ICON_X, CURRENCY_ICON_Y))
    gem_icon = _load_asset("ui/icons/gem.png")
    if gem_icon:
        gem_icon = gem_icon.resize(icon_sz, Image.Resampling.NEAREST)
        canvas.alpha_composite(gem_icon, (GEM_ICON_X, CURRENCY_ICON_Y))

    gold_text = f"{state.gold:06d}"
    gems_text = f"{state.gems:06d}"
    _draw_outlined_text(draw, (CURRENCY_LEFT_X, CURRENCY_Y), gold_text, font=font_currency)
    _draw_outlined_text(draw, (CURRENCY_RIGHT_X, CURRENCY_Y), gems_text, font=font_currency)
    # --- END AI-REPLACED ---


def render_gameboy_frame(state: PetState) -> bytes:
    gameboy = _load_asset(state.gameboy_skin)
    if gameboy is None:
        gameboy = _load_asset("gameboy/frames/gameboy-basic-01.png")
    if gameboy is None:
        gameboy = Image.new('RGBA', (FRAME_W, FRAME_H), (77, 155, 230, 255))

    gif_frames = []

    for frame_idx in range(ANIMATION_FRAMES):
        canvas = Image.new('RGBA', (FRAME_W, FRAME_H), (0, 0, 0, 0))

        scene = compose_full_scene(state, frame_idx)
        canvas.paste(scene, (SCREEN_X, SCREEN_Y))

        canvas.alpha_composite(gameboy)
        apply_screen_depth(canvas)
        draw_gameboy_ui(canvas, state)

        rgb_frame = Image.new('RGB', (FRAME_W, FRAME_H), (20, 20, 30))
        rgb_frame.paste(canvas, mask=canvas.split()[3])
        gif_frames.append(rgb_frame)

    output = io.BytesIO()
    gif_frames[0].save(
        output,
        format='GIF',
        save_all=True,
        append_images=gif_frames[1:],
        duration=GIF_FRAME_DURATION,
        loop=0,
        optimize=False,
    )
    output.seek(0)
    return output.getvalue()


# --- AI-REPLACED (2026-03-16) ---
# Reason: Fullscreen showed a bare scene with no Gameboy frame, losing the
#   skin-specific design. Now shows the upper half of the Gameboy (bezel + screen)
#   cropped below the screen, just like the farm fullscreen renderer.
# What the new code does better: Users see their Gameboy skin in fullscreen,
#   making each skin look like a unique device.
# --- Original code (commented out for rollback) ---
# FULLSCREEN_SIZE = 800
#
# def render_fullscreen_frame(state: PetState) -> bytes:
#     """Render the pet scene at 800x800 with crispy nearest-neighbor upscale, no Gameboy frame."""
#     gif_frames = []
#
#     for frame_idx in range(ANIMATION_FRAMES):
#         scene = compose_full_scene(state, frame_idx)
#         upscaled = scene.resize((FULLSCREEN_SIZE, FULLSCREEN_SIZE), Image.Resampling.NEAREST)
#         rgb = Image.new('RGB', (FULLSCREEN_SIZE, FULLSCREEN_SIZE), (20, 20, 30))
#         rgb.paste(upscaled, mask=upscaled.split()[3])
#         gif_frames.append(rgb)
#
#     output = io.BytesIO()
#     gif_frames[0].save(
#         output,
#         format='GIF',
#         save_all=True,
#         append_images=gif_frames[1:],
#         duration=GIF_FRAME_DURATION,
#         loop=0,
#         optimize=False,
#     )
#     output.seek(0)
#     return output.getvalue()
# --- End original code ---

FULLSCREEN_CROP_Y = 244
FULLSCREEN_SCALE = 3

def render_fullscreen_frame(state: PetState) -> bytes:
    """Render pet scene inside the upper half of the Gameboy frame, upscaled 3x.

    The frame is cropped at y=244 (just below the screen), keeping the
    skin-specific bezel so it still looks like a device. The bottom panel
    (name, bars, currency) is cut off for a cleaner, bigger view.
    """
    gameboy = _load_asset(state.gameboy_skin)
    if gameboy is None:
        gameboy = _load_asset("gameboy/frames/gameboy-basic-01.png")
    if gameboy is None:
        gameboy = Image.new('RGBA', (FRAME_W, FRAME_H), (77, 155, 230, 255))

    cropped_h = min(FULLSCREEN_CROP_Y, gameboy.height)
    out_w = FRAME_W * FULLSCREEN_SCALE
    out_h = cropped_h * FULLSCREEN_SCALE

    gif_frames = []
    for frame_idx in range(ANIMATION_FRAMES):
        canvas = Image.new('RGBA', (FRAME_W, cropped_h), (0, 0, 0, 0))

        scene = compose_full_scene(state, frame_idx)
        canvas.paste(scene, (SCREEN_X, SCREEN_Y))

        frame_crop = gameboy.crop((0, 0, FRAME_W, cropped_h))
        canvas.alpha_composite(frame_crop)
        apply_screen_depth(canvas)

        upscaled = canvas.resize((out_w, out_h), Image.Resampling.NEAREST)

        rgb = Image.new('RGB', (out_w, out_h), (20, 20, 30))
        rgb.paste(upscaled, mask=upscaled.split()[3])
        gif_frames.append(rgb)

    output = io.BytesIO()
    gif_frames[0].save(
        output,
        format='GIF',
        save_all=True,
        append_images=gif_frames[1:],
        duration=GIF_FRAME_DURATION,
        loop=0,
        optimize=False,
    )
    output.seek(0)
    return output.getvalue()
# --- END AI-REPLACED ---


# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Render animated care action GIFs with text overlays, sparkle
#          particles, and bubble effects for feed/bathe/sleep/wake actions
import math
import random as _rng

ACTION_FRAME_COUNT = 8
ACTION_FRAME_DURATION = 120
ACTION_RENDER_SIZE = 800

def _draw_sparkle(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple):
    """Draw a 4-point star sparkle."""
    pts = []
    for angle_deg in range(0, 360, 45):
        angle = math.radians(angle_deg)
        r = size if angle_deg % 90 == 0 else size // 3
        pts.append((cx + int(r * math.cos(angle)), cy + int(r * math.sin(angle))))
    if len(pts) >= 3:
        draw.polygon(pts, fill=color)

def _draw_bubbles(draw: ImageDraw.ImageDraw, frame: int, base_positions: list):
    """Draw animated bubbles floating upward."""
    for bx, by, bsize in base_positions:
        y = by - frame * 18
        wobble = int(math.sin(frame * 0.8 + bx * 0.1) * 6)
        alpha = max(0, 255 - frame * 30)
        if alpha <= 0:
            continue
        x = bx + wobble
        draw.ellipse(
            [x - bsize, y - bsize, x + bsize, y + bsize],
            outline=(160, 210, 255, alpha),
            width=2,
        )
        highlight_r = max(1, bsize // 3)
        draw.ellipse(
            [x - bsize + 2, y - bsize + 2, x - bsize + 2 + highlight_r, y - bsize + 2 + highlight_r],
            fill=(220, 240, 255, alpha),
        )


def render_action_frame(state: PetState, action: str) -> bytes:
    """Render a short animated GIF with care action visual effects.

    Actions: 'feed', 'bathe', 'sleep', 'wake'
    """
    _rng.seed(42)
    sparkle_positions = [(_rng.randint(200, 600), _rng.randint(150, 500)) for _ in range(12)]
    bubble_positions = [(_rng.randint(250, 550), _rng.randint(400, 650), _rng.randint(6, 14)) for _ in range(15)]

    gif_frames = []
    font_big = _get_font(32)
    font_med = _get_font(20)

    for frame_idx in range(ACTION_FRAME_COUNT):
        scene = compose_full_scene(state, frame_idx)
        upscaled = scene.resize((ACTION_RENDER_SIZE, ACTION_RENDER_SIZE), Image.Resampling.NEAREST)
        overlay = Image.new('RGBA', (ACTION_RENDER_SIZE, ACTION_RENDER_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        t = frame_idx / ACTION_FRAME_COUNT

        if action == 'feed':
            y_float = int(300 - frame_idx * 20)
            # --- AI-MODIFIED (2026-05-15) ---
            # Purpose: Care buttons now fill to max in one click (was +2). Text label
            # updated to match. "Nom nom!" mirrors the response text.
            _draw_outlined_text(draw, (340, y_float), "Nom nom!", font=font_big,
                                fill=(255, 220, 50), outline=(80, 60, 0))
            # --- END AI-MODIFIED ---
            for i, (sx, sy) in enumerate(sparkle_positions[:8]):
                phase = (frame_idx + i) % ACTION_FRAME_COUNT
                dy = -phase * 12
                size = max(2, 8 - phase)
                alpha = max(0, 255 - phase * 30)
                _draw_sparkle(draw, sx, sy + dy, size, (255, 230, 80, alpha))

        elif action == 'bathe':
            _draw_bubbles(draw, frame_idx, bubble_positions)
            alpha = max(0, 255 - frame_idx * 25)
            y_float = int(280 - frame_idx * 8)
            _draw_outlined_text(draw, (260, y_float), "Splashhh!", font=font_big,
                                fill=(100, 200, 255, alpha), outline=(20, 60, 100, alpha))
            for i, (sx, sy) in enumerate(sparkle_positions[4:10]):
                phase = (frame_idx + i * 2) % ACTION_FRAME_COUNT
                size = max(2, 6 - phase)
                _draw_sparkle(draw, sx, sy - phase * 10, size, (180, 220, 255, max(0, 220 - phase * 30)))

        elif action == 'sleep':
            for z_idx in range(3):
                zx = 480 + z_idx * 40 + frame_idx * 8
                zy = 250 - z_idx * 50 - frame_idx * 15
                size_mult = 1.0 + z_idx * 0.3
                font_z = _get_font(int(18 * size_mult))
                alpha = max(0, 255 - frame_idx * 20 - z_idx * 30)
                _draw_outlined_text(draw, (zx, zy), "Z", font=font_z,
                                    fill=(180, 160, 255, alpha), outline=(40, 30, 80, alpha))
            for i, (sx, sy) in enumerate(sparkle_positions[:5]):
                phase = (frame_idx + i) % ACTION_FRAME_COUNT
                size = max(2, 5 - phase)
                _draw_sparkle(draw, sx + 100, sy - 100 - phase * 8, size, (160, 140, 220, max(0, 200 - phase * 30)))

        elif action == 'wake':
            y_float = int(250 - frame_idx * 5)
            alpha = min(255, frame_idx * 40 + 60)
            _draw_outlined_text(draw, (220, y_float), "Good morning!", font=font_big,
                                fill=(255, 240, 100, alpha), outline=(80, 70, 0, alpha))
            for i, (sx, sy) in enumerate(sparkle_positions):
                phase = (frame_idx + i * 2) % ACTION_FRAME_COUNT
                burst = phase * 3
                size = max(2, 4 + int(math.sin(phase * 0.5) * 4))
                _draw_sparkle(draw, sx + burst, sy - burst, size, (255, 240, 120, max(0, 255 - phase * 20)))

        upscaled.alpha_composite(overlay)
        rgb = Image.new('RGB', (ACTION_RENDER_SIZE, ACTION_RENDER_SIZE), (20, 20, 30))
        rgb.paste(upscaled, mask=upscaled.split()[3])
        gif_frames.append(rgb)

    output = io.BytesIO()
    gif_frames[0].save(
        output,
        format='GIF',
        save_all=True,
        append_images=gif_frames[1:],
        duration=ACTION_FRAME_DURATION,
        loop=0,
        optimize=False,
    )
    output.seek(0)
    return output.getvalue()
# --- END AI-MODIFIED ---

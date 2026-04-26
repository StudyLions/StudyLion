import asyncio
from io import BytesIO

from PIL import Image

from meta import LionBot
from gui.base import CardMode

from .stats import get_stats_card
from .profile import get_profile_card


card_gap = 10

# --- AI-MODIFIED (2026-04-25) ---
# Purpose: Phase 2 LionHeart Studio fix — preserve animation when combining
#          a supporter's animated profile GIF with the static stats card.
#          Previously the renderer opened the GIF, took only frame 0, and
#          saved the combined image as a static PNG, throwing the entire
#          animation away. Discord then served it as a still image because
#          the cog also hardcoded a `.png` filename.
DISCORD_DARK_BG = (49, 51, 56)
GIF_MAGIC = (b'GIF87a', b'GIF89a')


def _combine_static(profile_data: bytes, stats_data: bytes) -> BytesIO:
    """Combine non-animated profile + stats PNGs into a single PNG."""
    with BytesIO(stats_data) as stats_stream, BytesIO(profile_data) as profile_stream:
        with Image.open(stats_stream) as stats_image, Image.open(profile_stream) as profile_image:
            profile_rgba = profile_image.convert('RGBA')
            stats_rgba = stats_image.convert('RGBA')

            combined = Image.new(
                'RGBA',
                (
                    max(stats_rgba.width, profile_rgba.width),
                    profile_rgba.height + card_gap + stats_rgba.height,
                ),
                color=None,
            )
            with combined:
                combined.alpha_composite(profile_rgba)
                combined.alpha_composite(stats_rgba, (0, profile_rgba.height + card_gap))

                results = BytesIO()
                combined.save(results, format='PNG', compress_type=3, compress_level=1)
                results.seek(0)
                return results


def _combine_animated(profile_data: bytes, stats_data: bytes) -> BytesIO:
    """Combine an animated profile GIF with a static stats PNG, preserving
    the per-frame animation. Returns a BytesIO containing a multi-frame GIF.

    Each profile frame is composited with the same stats card below it, then
    flattened onto the Discord dark background and palette-quantised so the
    final GIF stays small and crisp.
    """
    profile_gif = Image.open(BytesIO(profile_data))
    n_frames = getattr(profile_gif, 'n_frames', 1)
    duration = profile_gif.info.get('duration', 90)
    loop = profile_gif.info.get('loop', 0)

    stats_image = Image.open(BytesIO(stats_data)).convert('RGBA')
    profile_w, profile_h = profile_gif.size
    stats_w, stats_h = stats_image.size
    combined_w = max(profile_w, stats_w)
    combined_h = profile_h + card_gap + stats_h
    stats_y = profile_h + card_gap

    frames_rgb = []
    for idx in range(n_frames):
        profile_gif.seek(idx)
        frame_rgba = profile_gif.convert('RGBA')

        combined = Image.new('RGBA', (combined_w, combined_h), (0, 0, 0, 0))
        combined.alpha_composite(frame_rgba)
        combined.alpha_composite(stats_image, (0, stats_y))

        bg = Image.new('RGBA', combined.size, (*DISCORD_DARK_BG, 255))
        flat = Image.alpha_composite(bg, combined)
        frames_rgb.append(flat.convert('RGB'))

    profile_gif.close()
    stats_image.close()

    out = BytesIO()
    try:
        quantized = [f.quantize(colors=128) for f in frames_rgb]
        quantized[0].save(
            out,
            format='GIF',
            save_all=True,
            append_images=quantized[1:],
            duration=duration,
            loop=loop,
            optimize=True,
            disposal=2,
        )
    except Exception:
        out.seek(0)
        out.truncate()
        frames_rgb[0].save(
            out,
            format='GIF',
            save_all=True,
            append_images=frames_rgb[1:],
            duration=duration,
            loop=loop,
            optimize=True,
        )

    out.seek(0)
    return out


async def get_full_profile(bot: LionBot, userid: int, guildid: int, mode: CardMode) -> BytesIO:
    """
    Render both profile and stats for the target member in the given mode.

    Combines the resulting cards into a single image and returns the image data.
    For LionHeart supporters whose profile renders as an animated GIF, the
    combined output is itself an animated GIF so the animation survives the
    combine step (see `_combine_animated`).
    """
    get_tasks = (
        asyncio.create_task(get_stats_card(bot, userid, guildid, mode), name='get-stats-for-combined'),
        asyncio.create_task(get_profile_card(bot, userid, guildid), name='get-profile-for-combined'),
    )
    stats_card, profile_card = await asyncio.gather(*get_tasks)

    render_tasks = (
        asyncio.create_task(stats_card.render(), name='render-stats-for-combined'),
        asyncio.create_task(profile_card.render(), name='render=profile-for-combined'),
    )

    stats_data, profile_data = await asyncio.gather(*render_tasks)

    if isinstance(profile_data, (bytes, bytearray)) and profile_data[:6] in GIF_MAGIC:
        return await asyncio.to_thread(_combine_animated, bytes(profile_data), bytes(stats_data))

    return await asyncio.to_thread(_combine_static, bytes(profile_data), bytes(stats_data))
# --- END AI-MODIFIED ---

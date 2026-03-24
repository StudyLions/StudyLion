import asyncio
from io import BytesIO

from PIL import Image

from meta import LionBot
from gui.base import CardMode

from .stats import get_stats_card
from .profile import get_profile_card


card_gap = 10


async def get_full_profile(bot: LionBot, userid: int, guildid: int, mode: CardMode) -> BytesIO:
    """
    Render both profile and stats for the target member in the given mode.

    Combines the resulting cards into a single image and returns the image data.
    """
    # Prepare cards for rendering
    get_tasks = (
        asyncio.create_task(get_stats_card(bot, userid, guildid, mode), name='get-stats-for-combined'),
        asyncio.create_task(get_profile_card(bot, userid, guildid), name='get-profile-for-combined'),
    )
    stats_card, profile_card = await asyncio.gather(*get_tasks)

    # Render cards
    render_tasks = (
        asyncio.create_task(stats_card.render(), name='render-stats-for-combined'),
        asyncio.create_task(profile_card.render(), name='render=profile-for-combined'),
    )

    # Load the card data into images
    stats_data, profile_data = await asyncio.gather(*render_tasks)
    with BytesIO(stats_data) as stats_stream, BytesIO(profile_data) as profile_stream:
        with Image.open(stats_stream) as stats_image, Image.open(profile_stream) as profile_image:
            # --- AI-REPLACED (2026-03-19) ---
            # Reason: Two bugs — (1) getbbox() returns tight content bounds smaller than
            # the actual image, (2) supporter cards render as GIF (palette mode P) which
            # is incompatible with alpha_composite (requires RGBA).
            # What the new code does better: Converts both images to RGBA and uses actual
            # image dimensions so compositing always succeeds regardless of source format.
            # --- Original code (commented out for rollback) ---
            # stats_bbox = stats_image.getbbox(alpha_only=False)
            # profile_bbox = profile_image.getbbox(alpha_only=False)
            #
            # if stats_bbox is None or profile_bbox is None:
            #     raise ValueError("Could not combine, empty stats or profile image.")
            #
            # combined = Image.new(
            #     'RGBA',
            #     (
            #         max(stats_bbox[2], profile_bbox[2]),
            #         stats_bbox[3] + card_gap + profile_bbox[3]
            #     ),
            #     color=None
            # )
            # with combined:
            #     combined.alpha_composite(profile_image)
            #     combined.alpha_composite(stats_image, (0, profile_bbox[3] + card_gap))
            # --- End original code ---
            profile_rgba = profile_image.convert('RGBA')
            stats_rgba = stats_image.convert('RGBA')

            combined = Image.new(
                'RGBA',
                (
                    max(stats_rgba.width, profile_rgba.width),
                    profile_rgba.height + card_gap + stats_rgba.height
                ),
                color=None
            )
            with combined:
                combined.alpha_composite(profile_rgba)
                combined.alpha_composite(stats_rgba, (0, profile_rgba.height + card_gap))

                results = BytesIO()
                combined.save(results, format='PNG', compress_type=3, compress_level=1)
                results.seek(0)
                return results
            # --- END AI-REPLACED ---

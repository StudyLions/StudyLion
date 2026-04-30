# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-30
# Purpose: Direct SQL access for the server-listing module.
#          We don't use the Registry/RowModel pattern here
#          because the website is the primary writer to these
#          tables -- the bot only needs simple read + targeted
#          updates (invite_code, view counts) so raw psycopg
#          queries are simpler and avoid coupling the bot's
#          schema-tracking system to a website-owned table.
# ============================================================
from typing import Optional, Any
from utils.lib import utc_now


async def fetch_listing_by_guildid(bot, guildid: int) -> Optional[dict[str, Any]]:
    """Return a single listing row as a dict, or None."""
    async with bot.db.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT
                guildid, slug, status::text AS status,
                display_name, tagline, description,
                cover_image_url, guild_icon_url, gallery_images,
                category, secondary_tags, is_study_server,
                primary_country, primary_language, audience_age,
                theme_preset, accent_color, font_family, cover_blend_mode,
                invite_code, invite_managed, invite_last_rotated,
                external_link_url, external_link_label,
                sections_enabled, nsfw_confirmed,
                submitted_at, approved_at, approved_by, rejection_reason,
                pending_changes, notification_sent_at,
                view_count, invite_click_count, promoted_until,
                created_at, updated_at
            FROM server_listings
            WHERE guildid = %s
            """,
            [guildid],
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_listing_invite(
    bot,
    guildid: int,
    *,
    invite_code: str,
) -> None:
    """Persist a new invite code on the listing. Bot is the source of
    truth for invite codes (it created them) so we do this directly."""
    async with bot.db.connection() as conn:
        await conn.execute(
            """
            UPDATE server_listings
            SET invite_code = %s,
                invite_managed = TRUE,
                invite_last_rotated = %s,
                updated_at = NOW()
            WHERE guildid = %s
            """,
            [invite_code, utc_now(), guildid],
        )


async def mark_notification_sent(bot, guildid: int) -> None:
    """Record that we posted the review embed for this listing so
    we don't double-ping Ari on the same submission."""
    async with bot.db.connection() as conn:
        await conn.execute(
            "UPDATE server_listings SET notification_sent_at = %s WHERE guildid = %s",
            [utc_now(), guildid],
        )


async def fetch_guild_name(bot, guildid: int) -> Optional[str]:
    """Convenience -- get the display guild name from guild_config."""
    async with bot.db.connection() as conn:
        cursor = await conn.execute(
            "SELECT name FROM guild_config WHERE guildid = %s",
            [guildid],
        )
        row = await cursor.fetchone()
        return row['name'] if row and row['name'] else None

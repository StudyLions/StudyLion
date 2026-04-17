# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-17
# Purpose: Continuously sync display names + usernames + avatars
#          from Discord gateway events into the database, so the
#          dashboard members list stops showing "User ...XXXX"
#          placeholders for users we already know about.
#
# Design notes
# ------------
# - on_member_join: full touch via fetch_member (creates row if needed,
#   then writes display_name + name + avatar_hash).
# - on_member_update: only touches members.display_name. Skips the DB
#   entirely if the display name didn't change. Uses cache-only lookup
#   so we don't create members rows for nicknames in guilds where the
#   user was never tracked.
# - on_user_update: only touches user_config.name + user_config.avatar_hash.
#   Skips the DB if neither changed. Cache-only lookup, with a direct
#   UPDATE-only fallback that touches zero rows when the user isn't in
#   our DB. This avoids inserting user_config rows for the millions of
#   Discord users we technically can see but don't track.
# ============================================================
import logging

import discord

from meta import LionBot, LionCog
from meta.logger import log_wrap

from . import babel

logger = logging.getLogger(__name__)
_p = babel._p


def _avatar_key(user) -> str | None:
    """Return the avatar hash key for a Discord user/member, or None."""
    avatar = getattr(user, 'avatar', None)
    return avatar.key if avatar else None


class NameSyncCog(LionCog):
    """
    Keeps `members.display_name`, `user_config.name`, and
    `user_config.avatar_hash` in sync with Discord by listening to gateway
    events. Complements the one-time `/leo backfill_names` admin command.
    """

    def __init__(self, bot: LionBot):
        self.bot = bot

    @LionCog.listener('on_member_join')
    @log_wrap(action="NameSync Join")
    async def sync_on_member_join(self, member: discord.Member):
        """When a member joins, ensure their record exists with current name + avatar."""
        if member.bot:
            return
        try:
            lmember = await self.bot.core.lions.fetch_member(
                member.guild.id, member.id, member=member
            )
            await lmember.touch_discord_model(member)
            await lmember.luser.touch_discord_model(member, seen=False)
        except Exception:
            logger.exception(
                f"Failed to sync names on join for <uid:{member.id}> in <gid:{member.guild.id}>"
            )

    @LionCog.listener('on_member_update')
    @log_wrap(action="NameSync Member Update")
    async def sync_on_member_update(self, before: discord.Member, after: discord.Member):
        """When a member's nickname changes, update members.display_name (cache-only)."""
        if after.bot:
            return
        if before.display_name == after.display_name:
            return

        cached = self.bot.core.lions.lion_members.get((after.guild.id, after.id), None)
        if cached is not None:
            try:
                await cached.touch_discord_model(after)
            except Exception:
                logger.exception(
                    f"Failed to sync nickname for <uid:{after.id}> in <gid:{after.guild.id}>"
                )
            return

        try:
            await self.bot.core.data.Member.table.update_where(
                guildid=after.guild.id, userid=after.id
            ).set(display_name=after.display_name)
        except Exception:
            logger.exception(
                f"Failed direct UPDATE of display_name for <uid:{after.id}> in <gid:{after.guild.id}>"
            )

    @LionCog.listener('on_user_update')
    @log_wrap(action="NameSync User Update")
    async def sync_on_user_update(self, before: discord.User, after: discord.User):
        """When a user's name or avatar changes, update user_config (cache-only)."""
        if after.bot:
            return
        before_key = _avatar_key(before)
        after_key = _avatar_key(after)
        if before.name == after.name and before_key == after_key:
            return

        cached = self.bot.core.lions.lion_users.get(after.id, None)
        if cached is not None:
            try:
                await cached.touch_discord_model(after, seen=False)
            except Exception:
                logger.exception(
                    f"Failed to sync user fields for <uid:{after.id}>"
                )
            return

        try:
            await self.bot.core.data.User.table.update_where(userid=after.id).set(
                name=after.name,
                avatar_hash=after_key,
            )
        except Exception:
            logger.exception(
                f"Failed direct UPDATE of user_config for <uid:{after.id}>"
            )

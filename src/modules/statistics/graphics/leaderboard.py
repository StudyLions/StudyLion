from meta import LionBot

from gui.cards import LeaderboardCard
from gui.base import CardMode


async def get_leaderboard_card(
    bot: LionBot, highlightid: int, guildid: int,
    mode: CardMode,
    entry_data: list[tuple[int, int, int]],  # userid, position, time
    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Accept pre-fetched guild for cross-shard autopost support
    guild=None,
    # --- END AI-MODIFIED ---
):
    """
    Render a leaderboard card with given parameters.
    """
    # --- AI-REPLACED (2026-03-22) ---
    # Reason: Use passed-in guild object when available (cross-shard)
    # What the new code does better: Allows callers to pass a pre-fetched guild
    # --- Original code (commented out for rollback) ---
    # guild = bot.get_guild(guildid)
    # if guild is None:
    #     raise ValueError("Attempting to build leaderboard for non-existent guild!")
    # --- End original code ---
    if guild is None:
        guild = bot.get_guild(guildid)
    if guild is None:
        raise ValueError("Attempting to build leaderboard for non-existent guild!")
    # --- END AI-REPLACED ---

    # Need to do two passes here in case we need to do a db request for the avatars or names
    avatars = {}
    names = {}
    missing = []
    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Ensure names are never None (causes PIL TypeError in renderer)
    for userid, _, _ in entry_data:
        if guild and (member := guild.get_member(userid)):
            avatars[userid] = member.avatar.key if member.avatar else None
            names[userid] = member.display_name or str(userid)
        elif (user := bot.get_user(userid)):
            avatars[userid] = user.avatar.key if user.avatar else None
            names[userid] = user.display_name or str(userid)
        elif (user_data := bot.core.data.User._cache_.get((userid,))):
            avatars[userid] = user_data.avatar_hash
            names[userid] = user_data.name or str(userid)
        else:
            missing.append(userid)
    # --- END AI-MODIFIED ---

    if missing:
        # We were unable to retrieve information for some userids
        # Bulk-fetch missing users from data
        data = await bot.core.data.User.fetch_where(userid=missing)
        for user_data in data:
            avatars[user_data.userid] = user_data.avatar_hash
            names[user_data.userid] = user_data.name or 'Unknown'
            missing.remove(user_data.userid)

    if missing:
        # Some of the users were missing from data
        # This should be impossible (by FKEY constraints on sessions)
        # But just in case...
        for userid in missing:
            avatars[userid] = None
            names[userid] = str(userid)

    # --- AI-MODIFIED (2026-03-20) ---
    # Purpose: Fetch supporter status for leaderboard flair (golden star)
    supporter_tiers = {}
    premium_cog = bot.get_cog('PremiumCog')
    if premium_cog and hasattr(premium_cog, 'get_user_subscription_tier'):
        all_uids = [uid for uid, _, _ in entry_data]
        try:
            rows = await bot.db.fetch(
                "SELECT userid, tier FROM user_subscriptions "
                "WHERE userid = ANY($1::bigint[]) AND status = 'ACTIVE' AND tier != 'NONE'",
                all_uids,
            )
            for row in rows:
                supporter_tiers[row['userid']] = row['tier']
        except Exception:
            pass

    highlight = None
    entries = []
    for userid, position, duration in entry_data:
        entries.append(
            (userid, position, duration, names[userid], (userid, avatars[userid]),
             userid in supporter_tiers)
        )
        if userid == highlightid:
            highlight = position
    # --- END AI-MODIFIED ---

    # Request Card

    skin = await bot.get_cog('CustomSkinCog').get_skinargs_for(
        guildid, None, LeaderboardCard.card_id
    )
    card = LeaderboardCard(
        skin=skin | {'mode': mode},
        server_name=guild.name or str(guildid),
        entries=entries,
        highlight=highlight
    )
    return card

from meta import LionBot

from gui.cards import LeaderboardCard
from gui.base import CardMode


async def get_leaderboard_card(
    bot: LionBot, highlightid: int, guildid: int,
    mode: CardMode,
    entry_data: list[tuple[int, int, int]],  # userid, position, time
):
    """
    Render a leaderboard card with given parameters.
    """
    guild = bot.get_guild(guildid)
    if guild is None:
        raise ValueError("Attempting to build leaderboard for non-existent guild!")

    # Need to do two passes here in case we need to do a db request for the avatars or names
    avatars = {}
    names = {}
    missing = []
    for userid, _, _ in entry_data:
        if guild and (member := guild.get_member(userid)):
            avatars[userid] = member.avatar.key if member.avatar else None
            names[userid] = member.display_name
        elif (user := bot.get_user(userid)):
            avatars[userid] = user.avatar.key if user.avatar else None
            names[userid] = user.display_name
        elif (user_data := bot.core.data.User._cache_.get((userid,))):
            avatars[userid] = user_data.avatar_hash
            names[userid] = user_data.name
        else:
            missing.append(userid)

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

    highlight = None
    entries = []
    for userid, position, duration in entry_data:
        entries.append(
            (userid, position, duration, names[userid], (userid, avatars[userid]))
        )
        if userid == highlightid:
            highlight = position

    # Request Card

    skin = await bot.get_cog('CustomSkinCog').get_skinargs_for(
        guildid, None, LeaderboardCard.card_id
    )
    card = LeaderboardCard(
        skin=skin | {'mode': mode},
        server_name=guild.name,
        entries=entries,
        highlight=highlight
    )
    return card

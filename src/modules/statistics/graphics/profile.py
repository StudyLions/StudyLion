from typing import Optional, TYPE_CHECKING
from datetime import datetime, timedelta

import discord

from meta import LionBot
from gui.cards import ProfileCard

from modules.ranks.cog import RankCog
from modules.ranks.utils import format_stat_range
from ..achievements import get_achievements_for

if TYPE_CHECKING:
    from ..cog import StatsCog


async def get_profile_card(bot: LionBot, userid: int, guildid: int):
    ranks: Optional[RankCog] = bot.get_cog('RankCog')
    stats: Optional[StatsCog] = bot.get_cog('StatsCog')
    if ranks is None or stats is None:
        raise ValueError("Cannot get profile card without ranks and stats cog loaded.")

    guild = bot.get_guild(guildid)
    if guild is None:
        raise ValueError(f"Cannot get profile card without guild {guildid}")

    lion = await bot.core.lions.fetch_member(guildid, userid)
    luser = lion.luser
    member = await lion.fetch_member()

    if member:
        username = (member.display_name, '#' + str(member.discriminator))
        avatar = member.avatar.key if member.avatar else member.default_avatar.key
    else:
        username = (lion.data.display_name, "#????")
        avatar = luser.data.avatar_hash

    profile_badges = await stats.data.ProfileTag.fetch_tags(guildid, userid)

    # Fetch current and next guild rank
    season_rank = await ranks.get_member_rank(guildid, userid)
    rank_type = lion.lguild.config.get('rank_type').value
    crank = season_rank.current_rank
    nrank = season_rank.next_rank
    if crank:
        roleid = crank.roleid
        role = guild.get_role(roleid)
        name = role.name if role else 'Unknown Rank'
        minimum = crank.required
        maximum = nrank.required if nrank else None
        rangestr = format_stat_range(rank_type, minimum, maximum)
        if maximum is None:
            rangestr = f"≥ {rangestr}"
        current_rank = (name, rangestr)

        if maximum:
            rank_progress = (season_rank.stat - minimum) / (maximum - minimum)
        else:
            rank_progress = 1
    else:
        current_rank = None
        rank_progress = 0

    if nrank:
        roleid = nrank.roleid
        role = guild.get_role(roleid)
        name = role.name if role else 'Unknown Rank'
        minimum = nrank.required

        guild_ranks = await ranks.get_guild_ranks(guildid)
        nnrank = next((rank for rank in guild_ranks if rank.required > nrank.required), None)
        maximum = nnrank.required if nnrank else None
        rangestr = format_stat_range(rank_type, minimum, maximum)
        if maximum is None:
            rangestr = f"≥ {rangestr}"
        next_rank = (name, rangestr)
    else:
        next_rank = None

    achievements = await get_achievements_for(bot, guildid, userid)
    achieved = tuple(ach.emoji_index for ach in achievements if ach.achieved)

    skin = await bot.get_cog('CustomSkinCog').get_skinargs_for(
        guildid, userid, ProfileCard.card_id
    )

    card = ProfileCard(
        user=username,
        avatar=(userid, avatar),
        coins=lion.data.coins, gems=luser.data.gems, gifts=0,
        profile_badges=profile_badges,
        achievements=achieved,
        current_rank=current_rank,
        rank_progress=rank_progress,
        next_rank=next_rank,
        skin=skin,
    )
    return card

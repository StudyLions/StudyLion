from typing import Optional
import asyncio
import datetime
from weakref import WeakValueDictionary

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.app_commands.transformers import AppCommandOptionType
from cachetools import LRUCache

from meta import LionBot, LionContext, LionCog
from meta.logger import log_wrap
from wards import high_management_ward, high_management_iward
from core.data import RankType
from utils.ui import ChoicedEnum, Transformed
from utils.lib import utc_now, replace_multiple
from utils.ratelimits import Bucket, limit_concurrency
from utils.data import TemporaryTable
from modules.economy.cog import Economy
from modules.economy.data import TransactionType


from . import babel, logger
from .data import RankData, AnyRankData
from .settings import RankSettings
from .ui import RankOverviewUI, RankConfigUI, RankRefreshUI
from .utils import rank_model_from_type, format_stat_range

_p = babel._p


"""
Update mechanics?

Cache rank list per guild.
Rebuild rank list when ranks are updated through command or UI.

Cache recent member season statistics.
Flush the cached member season statistics when season is updated or reset.
Also cache current member ranks.

Expose interface get_rank(guildid, userid) which hits cache
Expose get_season_time(guildid, userid) which hits cache

Handle voice session ending
Handle xp added
Handle message sessions ending
 - We can even do these individually
 - As long as we hit cache all the way through the season stat process...


Alternatively, we can add a season_stats database cached table
And let the database handle it.
Of course, every time the season changes, we need to recompute all member statistics.
If we do this with database triggers, we will have to make a single database request each time anyway.

The season_stats table would make leaderboard computation faster though.
And it would make the initial loading for each user a bit faster.
Let's shelve it for now, potential premature optimisation.
We will need local caching for season stats anyway.

On startup, we can compute and memmoize season times for all active members?
Some 2-4k of them per shard.

Current update mechanics are highly not thread safe.
Even with locking, relying on the SeasonRank to stay up to date
but only handle each session event _once_ seems fragile.

Alternatively with a SeasonStats table, could use db as source of truth
and simply trigger a batch-update on event.
"""


class RankTypeChoice(ChoicedEnum):
    VOICE = (_p('cmd:configure_ranks|param:rank_type|choice:voice', "Voice"), RankType.VOICE)
    XP = (_p('cmd:configure_ranks|param:rank_type|choice:xp', "XP"), RankType.XP)
    MESSAGE = (_p('cmd:configure_ranks|param:rank_type|choice:message', "Message"), RankType.MESSAGE)

    @property
    def choice_name(self):
        return self.value[0]

    @property
    def choice_value(self):
        return self.name


class SeasonRank:
    """
    Cached season rank information for a given member.
    """
    __slots__ = (
        'guildid',
        'userid',
        'current_rank',
        'next_rank',
        'stat_type',
        'stat',
        'last_updated',
        'rankrow'
    )

    def __init__(self, guildid, userid, current_rank, next_rank, stat_type, stat, rankrow):
        self.guildid: int = guildid
        self.userid: int = userid

        self.current_rank: AnyRankData = current_rank
        self.next_rank: AnyRankData = next_rank

        self.stat_type: RankType = stat_type
        self.stat: int = stat

        self.last_updated = utc_now()
        self.rankrow = rankrow


class RankCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

        self.data = bot.db.load_registry(RankData())
        self.settings = RankSettings()

        # --- AI-MODIFIED (2026-03-25) ---
        # Purpose: Cache keys changed from guildid to (guildid, rank_type) for multi-rank-type support
        # Cached guild ranks: (guildid, rank_type) -> list[Rank]
        self._guild_ranks = {}
        # Cached member SeasonRanks: (guildid, rank_type) -> LRUCache(userid -> SeasonRank)
        self._member_ranks = {}
        # --- END AI-MODIFIED ---

        # Weakly referenced Locks for each guild to serialise rank actions
        self._rank_locks: dict[int, asyncio.Lock] = WeakValueDictionary()

    async def cog_load(self):
        await self.data.init()

        self.bot.core.guild_config.register_model_setting(self.settings.RankStatType)
        self.bot.core.guild_config.register_model_setting(self.settings.RankChannel)
        self.bot.core.guild_config.register_model_setting(self.settings.DMRanks)

        # --- AI-MODIFIED (2026-03-25) ---
        # Purpose: Register secondary rank type toggle settings
        self.bot.core.guild_config.register_model_setting(self.settings.VoiceRanksEnabled)
        self.bot.core.guild_config.register_model_setting(self.settings.MsgRanksEnabled)
        self.bot.core.guild_config.register_model_setting(self.settings.XpRanksEnabled)
        # --- END AI-MODIFIED ---

        configcog = self.bot.get_cog('ConfigCog')
        self.crossload_group(self.configure_group, configcog.admin_config_group)

    def ranklock(self, guildid):
        lock = self._rank_locks.get(guildid, None)
        if lock is None:
            lock = self._rank_locks[guildid] = asyncio.Lock()
        logger.debug(f"Getting rank lock for guild <guildid: {guildid}> (locked: {lock.locked()})")
        return lock

    # ---------- Event handlers ----------
    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Updated cache flush to use (guildid, rank_type) keys; added secondary type handlers
    @LionCog.listener('on_guildset_season_start')
    async def handle_season_start(self, guildid, setting):
        self.flush_guild_ranks(guildid)

    @LionCog.listener('on_guildset_rank_type')
    async def handle_rank_type(self, guildid, setting):
        self.flush_guild_ranks(guildid)

    @LionCog.listener('on_guildset_voice_ranks_enabled')
    async def handle_voice_ranks_enabled(self, guildid, setting):
        self.flush_guild_ranks(guildid)

    @LionCog.listener('on_guildset_msg_ranks_enabled')
    async def handle_msg_ranks_enabled(self, guildid, setting):
        self.flush_guild_ranks(guildid)

    @LionCog.listener('on_guildset_xp_ranks_enabled')
    async def handle_xp_ranks_enabled(self, guildid, setting):
        self.flush_guild_ranks(guildid)
    # --- END AI-MODIFIED ---

    # ---------- Cog API ----------
    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Cache key changed to (guildid, rank_type); added get_enabled_rank_types
    def _get_member_cache(self, guildid: int, rank_type: RankType):
        cache_key = (guildid, rank_type)
        if (cached := self._member_ranks.get(cache_key, None)) is None:
            guild = self.bot.get_guild(guildid)
            if guild and guild.member_count and guild.member_count > 1000:
                size = guild.member_count // 10
            else:
                size = 100
            cached = LRUCache(maxsize=size)
            self._member_ranks[cache_key] = cached
        return cached

    async def get_enabled_rank_types(self, guildid: int) -> set[RankType]:
        """
        Return the set of all enabled rank types for this guild.
        Always includes the primary rank_type; secondary types included if toggled on.
        """
        lguild = await self.bot.core.lions.fetch_guild(guildid)
        primary = lguild.config.get('rank_type').value
        enabled = {primary}
        if lguild.config.get('voice_ranks_enabled').value:
            enabled.add(RankType.VOICE)
        if lguild.config.get('msg_ranks_enabled').value:
            enabled.add(RankType.MESSAGE)
        if lguild.config.get('xp_ranks_enabled').value:
            enabled.add(RankType.XP)
        return enabled
    # --- END AI-MODIFIED ---

    def _get_stats_model(self, rank_type):
        return {
            RankType.MESSAGE: self.bot.get_cog('TextTrackerCog').data.TextSessions,
            RankType.VOICE: self.bot.get_cog('StatsCog').data.VoiceSessionStats,
            RankType.XP: self.bot.get_cog('StatsCog').data.MemberExp,
        }[rank_type]

    def _get_rank_model(self, rank_type):
        return {
            RankType.MESSAGE: self.data.MsgRank,
            RankType.VOICE: self.data.VoiceRank,
            RankType.XP: self.data.XPRank,
        }[rank_type]

    def _get_rankid_column(self, rank_type):
        return {
            RankType.MESSAGE: 'current_msg_rankid',
            RankType.VOICE: 'current_voice_rankid',
            RankType.XP: 'current_xp_rankid'
        }[rank_type]

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Accept optional rank_type for multi-rank-type support; defaults to primary type
    async def get_member_rank(self, guildid: int, userid: int, rank_type: Optional[RankType] = None) -> SeasonRank:
        """
        Fetch the SeasonRank info for the given member.

        If rank_type is None, uses the guild's primary rank_type.
        Applies cache where possible.
        """
        lguild = await self.bot.core.lions.fetch_guild(guildid)
        if rank_type is None:
            rank_type = lguild.config.get('rank_type').value

        member_cache = self._get_member_cache(guildid, rank_type)
        if (season_rank := member_cache.get(userid, None)) is None:
            season_start = lguild.config.get('season_start').value or datetime.datetime(1970, 1, 1)
            stat_data = self.bot.get_cog('StatsCog').data
            text_data = self.bot.get_cog('TextTrackerCog').data
            member_row = await self.data.MemberRank.fetch_or_create(guildid, userid)
            if rank_type is RankType.VOICE:
                model = stat_data.VoiceSessionStats
                stat = (await model.study_times_since(guildid, userid, season_start))[0]
                if rankid := member_row.current_voice_rankid:
                    current_rank = await self.data.VoiceRank.fetch(rankid)
                else:
                    current_rank = None
            elif rank_type is RankType.XP:
                model = stat_data.MemberExp
                stat = (await model.xp_since(guildid, userid, season_start))[0]
                if rankid := member_row.current_xp_rankid:
                    current_rank = await self.data.XPRank.fetch(rankid)
                else:
                    current_rank = None
            elif rank_type is RankType.MESSAGE:
                model = text_data.TextSessions
                stat = (await model.member_messages_since(guildid, userid, season_start))[0]
                if rankid := member_row.current_msg_rankid:
                    current_rank = await self.data.MsgRank.fetch(rankid)
                else:
                    current_rank = None

            ranks = await self.get_guild_ranks(guildid, rank_type=rank_type)
            next_rank = None
            current = current_rank.required if current_rank is not None else 0
            next_rank = next((rank for rank in ranks if rank.required > current), None)
            season_rank = SeasonRank(guildid, userid, current_rank, next_rank, rank_type, stat, member_row)
            member_cache[userid] = season_rank
        return season_rank
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Accept optional rank_type param; cache keyed by (guildid, rank_type)
    async def get_guild_ranks(self, guildid: int, refresh=False, rank_type: Optional[RankType] = None) -> list[AnyRankData]:
        """
        Get the list of ranks of the given type in the current guild.

        If rank_type is None, uses the guild's primary rank_type.
        Hits cache where possible, unless `refresh` is set.
        """
        if rank_type is None:
            lguild = await self.bot.core.lions.fetch_guild(guildid)
            rank_type = lguild.config.get('rank_type').value

        cache_key = (guildid, rank_type)
        if refresh or (ranks := self._guild_ranks.get(cache_key, None)) is None:
            rank_model = rank_model_from_type(rank_type)
            ranks = await rank_model.fetch_where(guildid=guildid).order_by('required')
            self._guild_ranks[cache_key] = ranks
        return ranks

    def flush_guild_ranks(self, guildid: int):
        """
        Clear all rank caches for the given guild (all types).
        """
        for rt in RankType:
            self._guild_ranks.pop((guildid, rt), None)
            self._member_ranks.pop((guildid, rt), None)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Process all enabled rank types (not just primary) for message sessions
    # --- Original code (commented out for rollback) ---
    # async def on_message_session_complete(self, *session_data):
    #     for guildid, userid, messages, guild_xp in session_data:
    #         if not self.bot.get_guild(guildid):
    #             continue
    #         lguild = await self.bot.core.lions.fetch_guild(guildid)
    #         rank_type = lguild.config.get('rank_type').value
    #         if rank_type in (RankType.MESSAGE, RankType.XP):
    #             async with self.ranklock(guildid):
    #                 if (_members := self._member_ranks.get(guildid, None)) is not None and userid in _members:
    #                     session_rank = _members[userid]
    #                     session_rank.stat += messages if (rank_type is RankType.MESSAGE) else guild_xp
    #                 else:
    #                     session_rank = await self.get_member_rank(guildid, userid)
    #                 if session_rank.next_rank is not None and session_rank.stat > session_rank.next_rank.required:
    #                     task = asyncio.create_task(self.update_rank(session_rank), name='update-message-rank')
    #                 else:
    #                     task = asyncio.create_task(self._role_check(session_rank), name='rank-role-check')
    #                 await task
    # --- End original code ---
    async def on_message_session_complete(self, *session_data):
        """
        Handle batch of completed message sessions.
        Processes all enabled rank types that are driven by message activity.
        """
        for guildid, userid, messages, guild_xp in session_data:
            if not self.bot.get_guild(guildid):
                continue
            enabled = await self.get_enabled_rank_types(guildid)
            for rtype in enabled:
                if rtype not in (RankType.MESSAGE, RankType.XP):
                    continue
                stat_delta = messages if rtype is RankType.MESSAGE else guild_xp
                async with self.ranklock(guildid):
                    cache_key = (guildid, rtype)
                    if (_members := self._member_ranks.get(cache_key, None)) is not None and userid in _members:
                        session_rank = _members[userid]
                        session_rank.stat += stat_delta
                    else:
                        session_rank = await self.get_member_rank(guildid, userid, rank_type=rtype)

                    if session_rank.next_rank is not None and session_rank.stat > session_rank.next_rank.required:
                        task = asyncio.create_task(
                            self.update_rank(session_rank, rank_type=rtype), name=f'update-{rtype.name.lower()}-rank'
                        )
                    else:
                        task = asyncio.create_task(
                            self._role_check(session_rank, rank_type=rtype), name=f'{rtype.name.lower()}-role-check'
                        )
                    await task
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Accept rank_type param; only manage roles from this type's ladder;
    #          removed last_roleid from rank_roleids to prevent cross-type removal;
    #          fixed false "Manage Roles" error when to_add is None (member already has role)
    # --- Original code (commented out for rollback) ---
    # async def _role_check(self, session_rank: SeasonRank):
    #     ... [see git history for original _role_check] ...
    # --- End original code ---
    async def _role_check(self, session_rank: SeasonRank, rank_type: Optional[RankType] = None):
        """
        Update the member's rank roles for the given rank type, if required.
        Only manages roles from this type's own rank ladder.
        """
        guildid = session_rank.guildid
        guild = self.bot.get_guild(guildid)

        userid = session_rank.userid
        member = guild.get_member(userid)

        if rank_type is None:
            lguild = await self.bot.core.lions.fetch_guild(guildid)
            rank_type = lguild.config.get('rank_type').value

        if guild is not None and member is not None and guild.me.guild_permissions.manage_roles:
            ranks = await self.get_guild_ranks(guildid, rank_type=rank_type)

            crank = session_rank.current_rank
            current_roleid = crank.roleid if crank else None

            rank_roleids = {rank.roleid for rank in ranks}

            mem_roleids = {role.id: role for role in member.roles}

            to_add = guild.get_role(current_roleid) if (current_roleid and current_roleid not in mem_roleids) else None
            to_rm = [
                role for roleid, role in mem_roleids.items()
                if roleid in rank_roleids and roleid != current_roleid
            ]

            t = self.bot.translator.t
            log_errors: list[str] = []
            log_added = None
            log_removed = None

            to_rm = [role for role in to_rm if role.is_assignable()]
            if to_rm:
                try:
                    await member.remove_roles(
                        *to_rm,
                        reason="Removing Old Rank Roles",
                        atomic=True
                    )
                    roleids = ', '.join(str(role.id) for role in to_rm)
                    logger.info(
                        f"Removed old rank roles from <uid:{userid}> in <gid:{guildid}>: {roleids}"
                    )
                except discord.HTTPException as e:
                    logger.warning(
                        f"Unexpected error removing old rank roles from <uid:{member.id}> in <gid:{guild.id}>: {to_rm}",
                        exc_info=True
                    )
                    log_errors.append(t(_p(
                        'eventlog|event:rank_check|error:remove_failed',
                        "Failed to remove old rank roles: `{error}`"
                    )).format(error=str(e)))
                log_removed = '\n'.join(role.mention for role in to_rm)

            if to_add:
                if to_add.is_assignable():
                    try:
                        await member.add_roles(
                            to_add,
                            reason="Rewarding Activity Rank",
                            atomic=True
                        )
                        logger.info(
                            f"Rewarded rank role <rid:{to_add.id}> to <uid:{userid}> in <gid:{guildid}>."
                        )
                    except discord.HTTPException as e:
                        logger.warning(
                            f"Unexpected error giving <uid:{userid}> in <gid:{guildid}> "
                            f"their rank role <rid:{to_add.id}>",
                            exc_info=True
                        )
                        log_errors.append(t(_p(
                            'eventlog|event:rank_check|error:add_failed',
                            "Failed to add new rank role: `{error}`"
                        )).format(error=str(e)))
                else:
                    log_errors.append(t(_p(
                        'eventlog|event:rank_check|error:add_impossible',
                        "Could not assign new activity rank role. Lacking permissions or invalid role."
                    )))
                log_added = to_add.mention

            if to_add or to_rm:
                lguild = await self.bot.core.lions.fetch_guild(guildid)
                lguild.log_event(
                    t(_p(
                        'eventlog|event:rank_check|name',
                        "Member Activity Rank Roles Updated"
                    )),
                    memberid=member.id,
                    roles_given=log_added,
                    roles_taken=log_removed,
                    errors=log_errors,
                )
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Accept explicit rank_type; only manage this type's roles; removed last_roleid from set
    # --- Original code (commented out for rollback) ---
    # async def update_rank(self, session_rank):
    #     ... [see git history for original update_rank] ...
    # --- End original code ---
    @log_wrap(action="Update Rank")
    async def update_rank(self, session_rank, rank_type: Optional[RankType] = None):
        guildid = session_rank.guildid
        userid = session_rank.userid

        lguild = await self.bot.core.lions.fetch_guild(guildid)
        if rank_type is None:
            rank_type = lguild.config.get('rank_type').value
        ranks = await self.get_guild_ranks(guildid, rank_type=rank_type)
        new_rank = None
        for rank in ranks:
            if rank.required <= session_rank.stat:
                new_rank = rank
            else:
                break

        if new_rank is None or new_rank is session_rank.current_rank:
            return

        guild = self.bot.get_guild(guildid)
        if guild is None:
            return

        member = guild.get_member(userid)
        if member is None:
            return

        t = self.bot.translator.t
        log_errors: list[str] = []
        log_added = None
        log_removed = None

        if guild.me.guild_permissions.manage_roles:
            rank_roleids = {rank.roleid for rank in ranks}

            mem_roleids = {role.id: role for role in member.roles}

            to_add = guild.get_role(new_rank.roleid) if (new_rank.roleid not in mem_roleids) else None
            to_rm = [
                role for roleid, role in mem_roleids.items()
                if roleid in rank_roleids and roleid != new_rank.roleid
            ]

            to_rm = [role for role in to_rm if role.is_assignable()]
            if to_rm:
                try:
                    await member.remove_roles(
                        *to_rm,
                        reason="Removing Old Rank Roles",
                        atomic=True
                    )
                    roleids = ', '.join(str(role.id) for role in to_rm)
                    logger.info(
                        f"Removed old rank roles from <uid:{userid}> in <gid:{guildid}>: {roleids}"
                    )
                except discord.HTTPException as e:
                    logger.warning(
                        f"Unexpected error removing old rank roles from <uid:{member.id}> in <gid:{guild.id}>: {to_rm}",
                        exc_info=True
                    )
                    log_errors.append(t(_p(
                        'eventlog|event:new_rank|error:remove_failed',
                        "Failed to remove old rank roles: `{error}`"
                    )).format(error=str(e)))
                log_removed = '\n'.join(role.mention for role in to_rm)

            if to_add:
                if to_add.is_assignable():
                    try:
                        await member.add_roles(
                            to_add,
                            reason="Rewarding Activity Rank",
                            atomic=True
                        )
                        logger.info(
                            f"Rewarded rank role <rid:{to_add.id}> to <uid:{userid}> in <gid:{guildid}>."
                        )
                    except discord.HTTPException as e:
                        logger.warning(
                            f"Unexpected error giving <uid:{userid}> in <gid:{guildid}> "
                            f"their rank role <rid:{to_add.id}>",
                            exc_info=True
                        )
                        log_errors.append(t(_p(
                            'eventlog|event:new_rank|error:add_failed',
                            "Failed to add new rank role: `{error}`"
                        )).format(error=str(e)))
                else:
                    log_errors.append(t(_p(
                        'eventlog|event:new_rank|error:add_impossible',
                        "Could not assign new activity rank role. Lacking permissions or invalid role."
                    )))
                log_added = to_add.mention
        else:
            log_errors.append(t(_p(
                'eventlog|event:new_rank|error:permissions',
                "Could not update activity rank roles, I lack the 'Manage Roles' permission."
            )))

        column = self._get_rankid_column(rank_type)
        await session_rank.rankrow.update(
            **{column: new_rank.rankid}
        )

        session_rank.current_rank = new_rank
        session_rank.next_rank = next((rank for rank in ranks if rank.required > new_rank.required), None)

        if new_rank.reward:
            economy: Economy = self.bot.get_cog('Economy')
            await economy.data.Transaction.execute_transaction(
                TransactionType.OTHER,
                guildid=guildid,
                actorid=guild.me.id,
                from_account=None,
                to_account=userid,
                amount=new_rank.reward
            )

        try:
            await self._notify_rank_update(guildid, userid, new_rank, rank_type=rank_type)
        except discord.HTTPException:
            log_errors.append(t(_p(
                'eventlog|event:new_rank|error:notify_failed',
                "Could not notify member."
            )))

        lguild.log_event(
            t(_p(
                'eventlog|event:new_rank|name',
                "Member Achieved Activity rank"
            )),
            t(_p(
                'eventlog|event:new_rank|desc',
                "{member} earned the new activity rank {rank}"
            )).format(member=member.mention, rank=f"<@&{new_rank.roleid}>"),
            roles_given=log_added,
            roles_taken=log_removed,
            coins_earned=new_rank.reward,
            errors=log_errors,
        )
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Accept explicit rank_type parameter for multi-rank-type notification
    async def _notify_rank_update(self, guildid, userid, new_rank, rank_type: Optional[RankType] = None):
        """
        Notify the given member that they have achieved the new rank.
        """
        guild = self.bot.get_guild(guildid)
        if guild:
            member = guild.get_member(userid)
            role = guild.get_role(new_rank.roleid)
            if member and role:
                t = self.bot.translator.t
                lguild = await self.bot.core.lions.fetch_guild(guildid)
                if rank_type is None:
                    rank_type = lguild.config.get('rank_type').value
    # --- END AI-MODIFIED ---

                # Build notification embed
                rank_mapping = self.get_message_map(rank_type, guild, member, role, new_rank)
                # --- AI-MODIFIED (2026-03-21) ---
                # Purpose: Guard against None rank message (admins who didn't set a custom message)
                raw_message = new_rank.message or t(_p(
                    'event:rank_update|default_message',
                    "Congratulations {user_mention}! You achieved the **{role_name}** rank!"
                ))
                rank_message = replace_multiple(raw_message, rank_mapping)
                # --- END AI-MODIFIED ---
                embed = discord.Embed(
                    colour=discord.Colour.orange(),
                    title=t(_p(
                        'event:rank_update|embed:notify',
                        "New Activity Rank Attained!"
                    )),
                    description=rank_message
                )

                # Calculate destination
                to_dm = lguild.config.get('dm_ranks').value
                rank_channel = lguild.config.get('rank_channel').value
                sent = False

                if to_dm:
                    destination = member
                    embed.set_author(
                        name=guild.name,
                        icon_url=guild.icon.url if guild.icon else None
                    )
                    try:
                        await destination.send(embed=embed)
                        sent = True
                    except discord.HTTPException:
                        if not rank_channel:
                            raise

                # --- AI-MODIFIED (2026-03-23) ---
                # Purpose: Always send to rank channel if configured, not just as DM fallback
                # --- Original code (commented out for rollback) ---
                # if not sent and rank_channel:
                #     destination = rank_channel
                #     text = member.mention
                #     await destination.send(content=text, embed=embed)
                # --- End original code ---
                if rank_channel:
                    await rank_channel.send(content=member.mention, embed=embed)
                # --- END AI-MODIFIED ---

    def get_message_map(self,
                        rank_type: RankType,
                        guild: discord.Guild, member: discord.Member,
                        role: discord.Role, rank: AnyRankData):
        t = self.bot.translator.t
        required = format_stat_range(rank_type, rank.required, short=False)

        key_map = {
            '{role_name}': role.name if role else 'Unknown',
            '{guild_name}': guild.name,
            '{user_name}': member.name,
            '{role_id}': role.id,
            '{guild_id}': guild.id,
            '{user_id}': member.id,
            '{role_mention}': role.mention,
            '{user_mention}': member.mention,
            '{requires}': required,
        }
        return key_map

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Process voice ranks if VOICE is in the enabled set (primary or secondary)
    # --- Original code (commented out for rollback) ---
    # async def on_voice_session_complete(self, *session_data):
    #     for guildid, userid, duration, guild_xp in session_data:
    #         ...
    #         rank_type = lguild.config.get('rank_type').value
    #         if rank_type in (RankType.VOICE,):
    #             async with self.ranklock(guildid):
    #                 if (_members := self._member_ranks.get(guildid, None)) is not None and userid in _members:
    #                     session_rank = _members[userid]
    #                     ...
    #                 else:
    #                     session_rank = await self.get_member_rank(guildid, userid)
    #                 if session_rank.next_rank is not None and session_rank.stat > session_rank.next_rank.required:
    #                     task = asyncio.create_task(self.update_rank(session_rank), name='voice-rank-update')
    #                 else:
    #                     task = asyncio.create_task(self._role_check(session_rank), name='voice-role-check')
    # --- End original code ---
    @log_wrap(action="Voice Rank Hook")
    async def on_voice_session_complete(self, *session_data):
        for guildid, userid, duration, guild_xp in session_data:
            if not self.bot.get_guild(guildid):
                continue
            lguild = await self.bot.core.lions.fetch_guild(guildid)
            unranked_role_setting = await self.bot.get_cog('StatsCog').settings.UnrankedRoles.get(guildid)
            unranked_roleids = set(unranked_role_setting.data)
            guild = self.bot.get_guild(guildid)
            member = guild.get_member(userid) if guild else None
            if not member or member.bot or any(role.id in unranked_roleids for role in member.roles):
                continue
            enabled = await self.get_enabled_rank_types(guildid)
            if RankType.VOICE in enabled:
                async with self.ranklock(guildid):
                    cache_key = (guildid, RankType.VOICE)
                    if (_members := self._member_ranks.get(cache_key, None)) is not None and userid in _members:
                        session_rank = _members[userid]
                        season_start = lguild.config.get('season_start').value or datetime.datetime(1970, 1, 1)
                        stat_data = self.bot.get_cog('StatsCog').data
                        session_rank.stat = (await stat_data.VoiceSessionStats.study_times_since(
                            guildid, userid, season_start)
                        )[0]
                    else:
                        session_rank = await self.get_member_rank(guildid, userid, rank_type=RankType.VOICE)

                    if session_rank.next_rank is not None and session_rank.stat > session_rank.next_rank.required:
                        task = asyncio.create_task(
                            self.update_rank(session_rank, rank_type=RankType.VOICE), name='voice-rank-update'
                        )
                    else:
                        task = asyncio.create_task(
                            self._role_check(session_rank, rank_type=RankType.VOICE), name='voice-role-check'
                        )
                    await task
    # --- END AI-MODIFIED ---

    async def on_xp_update(self, *xp_data):
        # Currently no-op since xp is given purely by message stats
        # Implement if xp ever becomes a combination of message and voice stats
        pass

    # --- AI-MODIFIED (2026-03-25) ---
    # Purpose: Accept optional rank_type for type-safe refresh that preserves other types' data
    @log_wrap(action='interactive rank refresh')
    async def interactive_rank_refresh(self, interaction: discord.Interaction, guild: discord.Guild,
                                       rank_type: Optional[RankType] = None):
        """
        Interactively update ranks for everyone in the given guild.
        If rank_type is provided, only refreshes that type (preserving others).
        """
        t = self.bot.translator.t
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=False)
        ui = RankRefreshUI(self.bot, guild, callerid=interaction.user.id, timeout=None)
        # --- AI-MODIFIED (2026-04-05) ---
        # Purpose: Catch Forbidden on channel send and fall back to interaction followup
        try:
            await ui.send(interaction.channel)
        except discord.Forbidden:
            try:
                await interaction.followup.send(
                    "I don't have permission to send messages in this channel. "
                    "Please make sure I have the **View Channel** and **Send Messages** "
                    "permissions here, then try again.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass
            return
        # --- END AI-MODIFIED ---
        ui.start()

        # Retrieve fresh rank roles for the specified type
        if rank_type is None:
            lguild = await self.bot.core.lions.fetch_guild(guild.id)
            rank_type = lguild.config.get('rank_type').value
        ranks = await self.get_guild_ranks(guild.id, refresh=True, rank_type=rank_type)
        ui.stage_ranks = True
        ui.poke()

        # Ensure guild is chunked
        if not guild.chunked:
            try:
                members = await asyncio.wait_for(guild.chunk(), timeout=60)
            # --- AI-MODIFIED (2026-04-05) ---
            # Purpose: Also catch Forbidden on guild.chunk() alongside TimeoutError
            except (asyncio.TimeoutError, discord.Forbidden):
            # --- END AI-MODIFIED ---
                error = t(_p(
                    'rank_refresh|error:cannot_chunk|desc',
                    "Could not retrieve member list from Discord. Please try again later."
                ))
                await ui.set_error(error)
                return
        else:
            members = guild.members
        ui.stage_members = True
        ui.poke()

        roles = {rank.roleid: guild.get_role(rank.roleid) for rank in ranks}
        if not all(roles.values()):
            error = t(_p(
                'rank_refresh|error:roles_dne|desc',
                "Some ranks have invalid or deleted roles! Please remove them first."
            ))
            await ui.set_error(error)
            return

        # Check that bot has permission to assign rank roles
        failing = [role for role in roles.values() if not role.is_assignable()]
        if failing:
            error = t(_p(
                'rank_refresh|error:unassignable_roles|desc',
                "I have insufficient permissions to assign the following role(s):\n{roles}"
            )).format(roles='\n'.join(role.mention for role in failing))
            await ui.set_error(error)
            return

        ui.stage_roles = True
        ui.poke()

        # Now we are certain that all the rank roles exist and are assignable
        # Compute season start and season leaderboard
        lguild = await self.bot.core.lions.fetch_guild(guild.id)
        season_start = lguild.config.get('season_start').value
        stats_model = self._get_stats_model(rank_type)
        if season_start:
            leaderboard = await stats_model.leaderboard_since(guild.id, season_start)
        else:
            leaderboard = await stats_model.leaderboard_all(guild.id)

        # Compile map of correct ranks
        # Filtering out members who are untracked or not in server
        unranked_role_setting = await self.bot.get_cog('StatsCog').settings.UnrankedRoles.get(guild.id)
        unranked_roleids = set(unranked_role_setting.data)
        true_member_ranks: dict[int, RankData.VoiceRank | RankData.XPRank | RankData.MsgRank] = {}
        for userid, stat_total in leaderboard:
            # Check member exists
            if member := guild.get_member(userid):
                # Check member does not have unranked roles
                if not (member.bot or any(role.id in unranked_roleids for role in member.roles)):
                    # Compute member rank
                    rank = next((rank for rank in reversed(ranks) if rank.required <= stat_total), None)
                    if rank is not None:
                        true_member_ranks[userid] = rank

        # Compile maps of member roles that need removal and member roles that need adding
        to_remove: list[tuple[discord.Member, list[discord.Role]]] = []
        to_add: list[tuple[discord.Member, discord.Role]] = []
        for member in members:
            if member.bot:
                continue
            true_rank = true_member_ranks.get(member.id, None)
            true_roleid = true_rank.roleid if true_rank is not None else None
            has_true = (true_roleid is None)
            invalid = []
            for role in member.roles:
                if role.id in roles:
                    if not has_true and role.id == true_roleid:
                        has_true = True
                    else:
                        invalid.append(role)
            if invalid:
                to_remove.append((member, invalid))
            if not has_true:
                to_add.append((member, roles[true_roleid]))

        ui.stage_compute = True
        ui.to_remove = len(to_remove)
        ui.to_add = len(to_add)
        ui.poke()

        # Perform operations
        # Starting with removals
        coros = []
        bucket = Bucket(4, 5)

        for member, roles in to_remove:
            remove_coro = member.remove_roles(
                *roles,
                reason=t(_p(
                    'rank_refresh|remove_roles|audit',
                    "Removing invalid rank role."
                ))
            )
            coros.append(bucket.wrapped(remove_coro))

        index = 0
        async for task in limit_concurrency(coros, 5):
            try:
                await task
                index += 1
                ui.poke()
            except discord.HTTPException:
                error = t(_p(
                    'rank_refresh|remove_roles|small_error',
                    "*Could not remove ranks from {member}*"
                )).format(member=to_remove[index][0].mention)
                ui.errors.append(error)
                if len(ui.errors) > 10:
                    await ui.set_error(
                        t(_p(
                            'rank_refresh|remove_roles|error:too_many_issues',
                            "Too many issues occurred while removing ranks! "
                            "Please check my permissions and try again in a few minutes."
                        ))
                    )
                    return
            ui.removed += 1
            ui.poke()

        coros = []
        for member, role in to_add:
            add_coro = member.add_roles(
                role,
                reason=t(_p(
                    'rank_refresh|add_roles|audit',
                    "Adding rank role from refresh"
                ))
            )
            coros.append(bucket.wrapped(add_coro))

        index = 0
        async for task in limit_concurrency(coros, 5):
            try:
                await task
                index += 1
                ui.poke()
            except discord.HTTPException:
                error = t(_p(
                    'rank_refresh|add_roles|small_error',
                    "*Could not add {role} to {member}*"
                )).format(member=to_add[index][0].mention, role=to_add[index][1].mention)
                ui.errors.append(error)
                if len(ui.errors) > 10:
                    await ui.set_error(
                        t(_p(
                            'rank_refresh|add_roles|error:too_many_issues',
                            "Too many issues occurred while adding ranks! "
                            "Please check my permissions and try again in a few minutes."
                        ))
                    )
                    return
            ui.added += 1
            ui.poke()

        # --- AI-MODIFIED (2026-03-25) ---
        # Purpose: Type-safe refresh - update only this type's column instead of delete-all
        # --- Original code (commented out for rollback) ---
        # await self.data.MemberRank.table.delete_where(guildid=guild.id)
        # if true_member_ranks:
        #     column = self._get_rankid_column(rank_type)
        #     values = [
        #         (guild.id, memberid, rank.rankid, rank.roleid)
        #         for memberid, rank in true_member_ranks.items()
        #     ]
        #     await self.data.MemberRank.table.insert_many(
        #         ('guildid', 'userid', column, 'last_roleid'),
        #         *values
        #     )
        # --- End original code ---
        column = self._get_rankid_column(rank_type)
        await self.data.MemberRank.table.update_where(guildid=guild.id).set(**{column: None})
        if true_member_ranks:
            for memberid, rank in true_member_ranks.items():
                row = await self.data.MemberRank.fetch_or_create(guild.id, memberid)
                await row.update(**{column: rank.rankid})
        self.flush_guild_ranks(guild.id)
        # --- END AI-MODIFIED ---
        await ui.set_done()

        # Event log
        lguild.log_event(
            t(_p(
                'eventlog|event:rank_refresh|name',
                "Activity Ranks Refreshed"
            )),
            t(_p(
                'eventlog|event:rank_refresh|desc',
                "{actor} refresh member activity ranks.\n"
                "**`{removed}`** invalid rank roles removed.\n"
                "**`{added}`** new rank roles added."
            )).format(
                actor=interaction.user.mention,
                removed=ui.removed,
                added=ui.added,
            )
        )

    # ---------- Commands ----------
    @cmds.hybrid_command(name=_p('cmd:ranks', "ranks"))
    async def ranks_cmd(self, ctx: LionContext):
        """
        Command to access the Rank Overview UI.
        """
        # TODO: Add a command interface to CRUD ranks
        # For now just using the clickety interface

        # Type checking guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        ui = RankOverviewUI(self.bot, ctx.guild, ctx.author.id)
        if await high_management_iward(ctx.interaction):
            await ui.run(ctx.interaction)
            await ui.wait()
        else:
            await ui.reload()
            msg = await ui.make_message(show_note=False)
            await ctx.reply(
                **msg.send_args,
                ephemeral=True
            )

    # ----- Guild Configuration -----
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        pass

    @configure_group.command(
        name=_p('cmd:configure_ranks', "ranks"),
        description=_p('cmd:configure_ranks|desc', "Configure Activity Ranks")
    )
    @appcmds.rename(
        rank_type=RankSettings.RankStatType._display_name,
        dm_ranks=RankSettings.DMRanks._display_name,
        rank_channel=RankSettings.RankChannel._display_name,
    )
    @appcmds.describe(
        rank_type=RankSettings.RankStatType._desc,
        dm_ranks=RankSettings.DMRanks._desc,
        rank_channel=RankSettings.RankChannel._desc,
    )
    @high_management_ward
    async def configure_ranks_cmd(self, ctx: LionContext,
                                  rank_type: Optional[Transformed[RankTypeChoice, AppCommandOptionType.string]] = None,
                                  dm_ranks: Optional[bool] = None,
                                  rank_channel: Optional[discord.VoiceChannel | discord.TextChannel] = None):
        # This uses te high management ward
        # Because rank modification can potentially delete roles.
        t = self.bot.translator.t

        # Type checking guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True)

        # Retrieve settings from cache
        rank_type_setting = await self.settings.RankStatType.get(ctx.guild.id)
        dm_ranks_setting = await self.settings.DMRanks.get(ctx.guild.id)
        rank_channel_setting = await self.settings.RankChannel.get(ctx.guild.id)

        modified = set()
        if rank_type is not None:
            rank_type_setting.value = rank_type.value[1]
            modified.add(rank_type_setting)
        if dm_ranks is not None:
            dm_ranks_setting.value = dm_ranks
            modified.add(dm_ranks_setting)
        if rank_channel is not None:
            rank_channel_setting.value = rank_channel
            modified.add(rank_channel_setting)

        # Write and send update ack if required
        if modified:
            # TODO: Batch
            for setting in modified:
                await setting.write()

            lines = []
            if rank_type_setting in modified:
                lines.append(rank_type_setting.update_message)
            if (dm_ranks is not None) or (rank_channel is not None):
                if dm_ranks_setting.value:
                    if rank_channel_setting.value:
                        notif_string = t(_p(
                            'cmd:configure_ranks|response:updated|setting:notification|withdm_withchannel',
                            "Rank update notifications will be sent via **direct message** when possible, "
                            "otherwise to {channel}"
                        )).format(channel=rank_channel_setting.value.mention)
                    else:
                        notif_string = t(_p(
                            'cmd:configure_ranks|response:updated|setting:notification|withdm_nochannel',
                            "Rank update notifications will be sent via **direct message**."
                        ))
                else:
                    if rank_channel_setting.value:
                        notif_string = t(_p(
                            'cmd:configure_ranks|response:updated|setting:notification|nodm_withchannel',
                            "Rank update notifications will be sent to {channel}."
                        )).format(channel=rank_channel_setting.value.mention)
                    else:
                        notif_string = t(_p(
                            'cmd:configure_ranks|response:updated|setting:notification|nodm_nochannel',
                            "Members will not be notified when their activity rank updates."
                        ))
                lines.append(notif_string)

            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description='\n'.join(f"{self.bot.config.emojis.tick} {line}" for line in lines)
            )
            await ctx.reply(embed=embed)

        if ctx.channel.id not in RankConfigUI._listening or not modified:
            ui = RankConfigUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()

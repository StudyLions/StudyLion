from typing import Optional
import asyncio
import datetime

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

        # Cached guild ranks for all current guilds. guildid -> list[Rank]
        self._guild_ranks = {}
        # Cached member SeasonRanks for recently active members
        # guildid -> userid -> SeasonRank
        # pop the guild whenever the season is updated or the rank type changes.
        self._member_ranks = {}

    async def cog_load(self):
        await self.data.init()

        self.bot.core.guild_config.register_model_setting(self.settings.RankStatType)
        self.bot.core.guild_config.register_model_setting(self.settings.RankChannel)
        self.bot.core.guild_config.register_model_setting(self.settings.DMRanks)

        configcog = self.bot.get_cog('ConfigCog')
        self.crossload_group(self.configure_group, configcog.configure_group)

    # ---------- Event handlers ----------
    # season_start setting event handler.. clears the guild season rank cache
    @LionCog.listener('on_guildset_season_start')
    async def handle_season_start(self, guildid, setting):
        self._member_ranks.pop(guildid, None)

    # guild_leave event handler.. removes the guild from _guild_ranks and clears the season cache
    @LionCog.listener('on_guildset_rank_type')
    async def handle_rank_type(self, guildid, setting):
        self.flush_guild_ranks(guildid)

    # rank_type setting event handler.. clears the guild season rank cache and the _guild_ranks cache

    # ---------- Cog API ----------
    def _get_member_cache(self, guildid: int):
        if (cached := self._member_ranks.get(guildid, None)) is None:
            guild = self.bot.get_guild(guildid)
            if guild and guild.member_count and guild.member_count > 1000:
                size = guild.member_count // 10
            else:
                size = 100
            cached = LRUCache(maxsize=size)
            self._member_ranks[guildid] = cached
        return cached

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

    async def get_member_rank(self, guildid: int, userid: int) -> SeasonRank:
        """
        Fetch the SeasonRank info for the given member.

        Applies cache where possible.
        """
        member_cache = self._get_member_cache(guildid)
        if (season_rank := member_cache.get(userid, None)) is None:
            # Fetch season rank anew
            lguild = await self.bot.core.lions.fetch_guild(guildid)
            rank_type = lguild.config.get('rank_type').value
            # TODO: Benchmark alltime efficiency
            season_start = lguild.config.get('season_start').value or datetime.datetime(1970, 1, 1)
            stat_data = self.bot.get_cog('StatsCog').data
            text_data = self.bot.get_cog('TextTrackerCog').data
            member_row = await self.data.MemberRank.fetch_or_create(guildid, userid)
            if rank_type is RankType.VOICE:
                model = stat_data.VoiceSessionStats
                # TODO: Should probably only used saved sessions here...
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

            ranks = await self.get_guild_ranks(guildid)
            next_rank = None
            current = current_rank.required if current_rank is not None else 0
            next_rank = next((rank for rank in ranks if rank.required > current), None)
            season_rank = SeasonRank(guildid, userid, current_rank, next_rank, rank_type, stat, member_row)
            member_cache[userid] = season_rank
        return season_rank

    async def get_guild_ranks(self, guildid: int, refresh=False) -> list[AnyRankData]:
        """
        Get the list of ranks of the correct type in the current guild.

        Hits cache where possible, unless `refresh` is set.
        """
        # TODO: Fill guild rank caches on cog_load
        if refresh or (ranks := self._guild_ranks.get(guildid, None)) is None:
            lguild = await self.bot.core.lions.fetch_guild(guildid)
            rank_type = lguild.config.get('rank_type').value
            rank_model = rank_model_from_type(rank_type)
            ranks = await rank_model.fetch_where(guildid=guildid).order_by('required')
            self._guild_ranks[guildid] = ranks
        return ranks

    def flush_guild_ranks(self, guildid: int):
        """
        Clear the caches for the given guild.
        """
        self._guild_ranks.pop(guildid, None)
        self._member_ranks.pop(guildid, None)

    async def on_message_session_complete(self, *session_data):
        """
        Handle batch of completed message sessions.
        """
        tasks = []
        # TODO: Thread safety
        # TODO: Locking between refresh and individual updates
        for guildid, userid, messages, guild_xp in session_data:
            lguild = await self.bot.core.lions.fetch_guild(guildid)
            rank_type = lguild.config.get('rank_type').value
            if rank_type in (RankType.MESSAGE, RankType.XP):
                if (_members := self._member_ranks.get(guildid, None)) is not None and userid in _members:
                    session_rank = _members[userid]
                    session_rank.stat += messages if (rank_type is RankType.MESSAGE) else guild_xp
                else:
                    session_rank = await self.get_member_rank(guildid, userid)

                if session_rank.next_rank is not None and session_rank.stat > session_rank.next_rank.required:
                    tasks.append(asyncio.create_task(self.update_rank(session_rank)))
                else:
                    tasks.append(asyncio.create_task(self._role_check(session_rank)))

        if tasks:
            await asyncio.gather(*tasks)

    async def _role_check(self, session_rank: SeasonRank):
        guild = self.bot.get_guild(session_rank.guildid)
        member = guild.get_member(session_rank.userid)
        crank = session_rank.current_rank
        roleid = crank.roleid if crank else None
        last_roleid = session_rank.rankrow.last_roleid
        if guild is not None and member is not None and roleid != last_roleid:
            new_role = guild.get_role(roleid) if roleid else None
            last_role = guild.get_role(last_roleid) if last_roleid else None
            new_last_roleid = last_roleid
            if guild.me.guild_permissions.manage_roles:
                try:
                    if last_role and last_role.is_assignable():
                        await member.remove_roles(last_role)
                        new_last_roleid = None
                    if new_role and new_role.is_assignable():
                        await member.add_roles(new_role)
                        new_last_roleid = roleid
                except discord.HTTPClient:
                    pass
                if new_last_roleid != last_roleid:
                    await session_rank.rankrow.update(last_roleid=new_last_roleid)

    @log_wrap(action="Update Rank")
    async def update_rank(self, session_rank):
        # Identify target rank
        guildid = session_rank.guildid
        userid = session_rank.userid

        lguild = await self.bot.core.lions.fetch_guild(guildid)
        rank_type = lguild.config.get('rank_type').value
        ranks = await self.get_guild_ranks(guildid)
        new_rank = None
        for rank in ranks:
            if rank.required <= session_rank.stat:
                new_rank = rank
            else:
                break

        if new_rank is None or new_rank is session_rank.current_rank:
            return

        # Attempt to update role
        guild = self.bot.get_guild(guildid)
        if guild is None:
            return

        member = guild.get_member(userid)
        if member is None:
            return

        new_role = guild.get_role(new_rank.roleid)
        if last_roleid := session_rank.rankrow.last_roleid:
            last_role = guild.get_role(last_roleid)
        else:
            last_role = None

        if guild.me.guild_permissions.manage_roles:
            try:
                if last_role and last_role.is_assignable():
                    await member.remove_roles(last_role)
                    last_roleid = None
                if new_role and new_role.is_assignable():
                    await member.add_roles(new_role)
                    last_roleid = new_role.id
            except discord.HTTPException:
                # TODO: Event log either way
                pass

        # Update MemberRank row
        column = {
            RankType.MESSAGE: 'current_msg_rankid',
            RankType.VOICE: 'current_voice_rankid',
            RankType.XP: 'current_xp_rankid'
        }[rank_type]
        await session_rank.rankrow.update(
            **{column: new_rank.rankid, 'last_roleid': last_roleid}
        )

        # Update SessionRank info
        session_rank.current_rank = new_rank
        session_rank.next_rank = next((rank for rank in ranks if rank.required > new_rank.required), None)

        # Provide economy reward if required
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

        # Send notification
        await self._notify_rank_update(guildid, userid, new_rank)

    async def _notify_rank_update(self, guildid, userid, new_rank):
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
                rank_type = lguild.config.get('rank_type').value

                # Build notification embed
                rank_mapping = self.get_message_map(rank_type, guild, member, role, new_rank)
                rank_message = replace_multiple(new_rank.message, rank_mapping)
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

                if to_dm or not rank_channel:
                    destination = member
                    embed.set_author(
                        name=guild.name,
                        icon_url=guild.icon.url if guild.icon else None
                    )
                    text = None
                else:
                    destination = rank_channel
                    text = member.mention

                # Post!
                try:
                    await destination.send(embed=embed, content=text)
                except discord.HTTPException:
                    # TODO: Logging, guild logging, invalidate channel if permissions are wrong
                    pass

    def get_message_map(self,
                        rank_type: RankType,
                        guild: discord.Guild, member: discord.Member,
                        role: discord.Role, rank: AnyRankData):
        t = self.bot.translator.t
        required = format_stat_range(rank_type, rank.required, short=False)

        key_map = {
            '{role_name}': role.name,
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

    @log_wrap(action="Voice Rank Hook")
    async def on_voice_session_complete(self, *session_data):
        tasks = []
        # TODO: Thread safety
        # TODO: Locking between refresh and individual updates
        for guildid, userid, duration, guild_xp in session_data:
            lguild = await self.bot.core.lions.fetch_guild(guildid)
            unranked_role_setting = await self.bot.get_cog('StatsCog').settings.UnrankedRoles.get(guildid)
            unranked_roleids = set(unranked_role_setting.data)
            guild = self.bot.get_guild(guildid)
            member = guild.get_member(userid) if guild else None
            if not member or member.bot or any (role.id in unranked_roleids for role in member.roles):
                continue
            rank_type = lguild.config.get('rank_type').value
            if rank_type in (RankType.VOICE,):
                if (_members := self._member_ranks.get(guildid, None)) is not None and userid in _members:
                    session_rank = _members[userid]
                    # TODO: Temporary measure
                    season_start = lguild.config.get('season_start').value or datetime.datetime(1970, 1, 1)
                    stat_data = self.bot.get_cog('StatsCog').data
                    session_rank.stat = (await stat_data.VoiceSessionStats.study_times_since(
                        guildid, userid, season_start)
                    )[0]
                    # session_rank.stat += duration if (rank_type is RankType.VOICE) else guild_xp
                else:
                    session_rank = await self.get_member_rank(guildid, userid)

                if session_rank.next_rank is not None and session_rank.stat > session_rank.next_rank.required:
                    tasks.append(asyncio.create_task(self.update_rank(session_rank)))
                else:
                    tasks.append(asyncio.create_task(self._role_check(session_rank)))
        if tasks:
            await asyncio.gather(*tasks)

    async def on_xp_update(self, *xp_data):
        ...

    @log_wrap(action='interactive rank refresh')
    async def interactive_rank_refresh(self, interaction: discord.Interaction, guild: discord.Guild):
        """
        Interactively update ranks for everyone in the given guild.
        """
        t = self.bot.translator.t
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=False)
        ui = RankRefreshUI(self.bot, guild, callerid=interaction.user.id, timeout=None)
        await ui.run(interaction)

        # Retrieve fresh rank roles
        ranks = await self.get_guild_ranks(guild.id, refresh=True)
        ui.stage_ranks = True
        ui.poke()

        # Ensure guild is chunked
        if not guild.chunked:
            members = await guild.chunk()
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
            )).format(roles='\n'.join(role.mention for role in failing)),
            await ui.set_error(error)
            return

        ui.stage_roles = True
        ui.poke()

        # Now we are certain that all the rank roles exist and are assignable
        # Compute season start and season leaderboard
        lguild = await self.bot.core.lions.fetch_guild(guild.id)
        season_start = lguild.config.get('season_start').value
        rank_type = lguild.config.get('rank_type').value
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
                self.ui.errors.append(error)
                if len(self.ui.errors) > 10:
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
                self.ui.errors.append(error)
                if len(self.ui.errors) > 10:
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

        # Save correct member ranks and given roles to data
        # First clear the member rank data entirely
        await self.data.MemberRank.table.delete_where(guildid=guild.id)
        column = self._get_rankid_column(rank_type)
        values = [
            (guild.id, memberid, rank.rankid, rank.roleid)
            for memberid, rank in true_member_ranks.items()
        ]
        await self.data.MemberRank.table.insert_many(
            ('guildid', 'userid', column, 'last_roleid'),
            *values
        )
        self.flush_guild_ranks(guild.id)
        await ui.set_done()
        await ui.wait()

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
            msg = await ui.make_message()
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
    @appcmds.default_permissions(administrator=True)
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
            if dm_ranks or rank_channel:
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

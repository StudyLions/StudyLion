from typing import Optional
from cachetools import LRUCache
import itertools
import datetime
import discord

from meta import LionCog, LionBot, LionContext
from utils.data import MEMBERS
from data import WeakCache

from .data import CoreData

from .lion_guild import LionGuild
from .lion_user import LionUser
from .lion_member import LionMember


class Lions(LionCog):
    def __init__(self, bot: LionBot, data: CoreData):
        self.bot = bot
        self.data = data

        # Caches
        # Using WeakCache so strong references stay consistent
        self.lion_guilds = WeakCache(LRUCache(2500))
        self.lion_users = WeakCache(LRUCache(2000))
        self.lion_members = WeakCache(LRUCache(5000))

    async def bot_check_once(self, ctx: LionContext):
        """
        Insert the high-level Lion objects into context before command execution.

        Creates the objects if they do not already exist.
        Updates relevant saved data from the Discord models,
        and updates last seen for the LionUser (for data lifetime).
        """
        if ctx.guild:
            # TODO: Consider doing all updates in one query, maybe with a View trigger on Member
            lmember = ctx.lmember = await self.fetch_member(ctx.guild.id, ctx.author.id, ctx.author)
            await lmember.touch_discord_model(ctx.author)

            ctx.luser = lmember.luser
            await ctx.luser.touch_discord_model(ctx.author, seen=True)

            ctx.lguild = lmember.lguild
            await ctx.lguild.touch_discord_model(ctx.guild)

            ctx.alion = lmember
        else:
            ctx.lmember = ctx.alion = None
            ctx.lguild = None
            luser = ctx.luser = await self.fetch_user(ctx.author.id, ctx.author)

            await luser.touch_discord_model(ctx.author)

            ctx.alion = luser
        return True

    async def fetch_user(self, userid, user: Optional[discord.User] = None) -> LionUser:
        """
        Fetch the given LionUser, hitting cache if possible.

        Creates the LionUser if it does not exist.
        """
        if (luser := self.lion_users.get(userid, None)) is None:
            data = await self.data.User.fetch_or_create(userid)
            luser = LionUser(self.bot, data, user=user)
            self.lion_users[userid] = luser
        return luser

    async def fetch_guild(self, guildid, guild: Optional[discord.Guild] = None) -> LionGuild:
        """
        Fetch the given LionGuild, hitting cache if possible.

        Creates the LionGuild if it does not exist.
        """
        if (lguild := self.lion_guilds.get(guildid, None)) is None:
            data = await self.data.Guild.fetch_or_create(guildid)
            lguild = LionGuild(self.bot, data, guild=guild)
            self.lion_guilds[guildid] = lguild
        return lguild

    async def fetch_guilds(self, *guildids) -> dict[int, LionGuild]:
        """
        Fetch (or create) multiple LionGuilds simultaneously, using cache where possible.
        """
        guild_map = {}
        missing = set()
        for guildid in guildids:
            lguild = self.lion_guilds.get(guildid, None)
            guild_map[guildid] = lguild
            if lguild is None:
                missing.add(guildid)

        if missing:
            rows = await self.data.Guild.fetch_where(guildid=list(missing))
            missing.difference_update(row.guildid for row in rows)

            if missing:
                new_rows = await self.data.Guild.table.insert_many(
                    ('guildid',),
                    *((guildid,) for guildid in missing)
                ).with_adapter(self.data.Guild._make_rows)
                rows = itertools.chain(rows, new_rows)

            for row in rows:
                guildid = row.guildid
                self.lion_guilds[guildid] = guild_map[guildid] = LionGuild(self.bot, row)

        return guild_map

    async def fetch_users(self, *userids) -> dict[int, LionUser]:
        """
        Fetch (or create) multiple LionUsers simultaneously, using cache where possible.
        """
        user_map = {}
        missing = set()
        for userid in userids:
            luser = self.lion_users.get(userid, None)
            user_map[userid] = luser
            if luser is None:
                missing.add(userid)

        if missing:
            rows = await self.data.User.fetch_where(userid=list(missing))
            missing.difference_update(row.userid for row in rows)

            if missing:
                new_rows = await self.data.User.table.insert_many(
                    ('userid',),
                    *((userid,) for userid in missing)
                ).with_adapter(self.data.User._make_rows)
                rows = itertools.chain(rows, new_rows)

            for row in rows:
                userid = row.userid
                self.lion_users[userid] = user_map[userid] = LionUser(self.bot, row)

        return user_map

    async def fetch_member(self, guildid, userid, member: Optional[discord.Member] = None) -> LionMember:
        """
        Fetch the given LionMember, using cache for data if possible.


        Creates the LionGuild, LionUser, and LionMember if they do not already exist.
        """
        # TODO: Can we do this more efficiently with one query, while keeping cache? Multiple joins?
        key = (guildid, userid)
        if (lmember := self.lion_members.get(key, None)) is None:
            lguild = await self.fetch_guild(guildid, member.guild if member is not None else None)
            luser = await self.fetch_user(userid, member)
            data = await self.data.Member.fetch_or_create(guildid, userid)
            lmember = LionMember(self.bot, data, lguild, luser, member)
            self.lion_members[key] = lmember
        return lmember

    async def fetch_members(self, *memberids: tuple[int, int]) -> dict[tuple[int, int], LionMember]:
        """
        Fetch or create multiple members simultaneously.
        """
        member_map = {}
        missing = set()

        # Retrieve what we can from cache
        for memberid in memberids:
            lmember = self.lion_members.get(memberid, None)
            member_map[memberid] = lmember
            if lmember is None:
                missing.add(memberid)

        # Fetch or create members that weren't in cache
        if missing:
            # First fetch or create the guilds and users
            lguilds = await self.fetch_guilds(*(gid for gid, _ in missing))
            lusers = await self.fetch_users(*(uid for _, uid in missing))

            # Now attempt to load members from data
            rows = await self.data.Member.fetch_where(MEMBERS(*missing))
            missing.difference_update((row.guildid, row.userid) for row in rows)

            # Create any member rows that are still missing
            if missing:
                new_rows = await self.data.Member.table.insert_many(
                    ('guildid', 'userid'),
                    *missing
                ).with_adapter(self.data.Member._make_rows)
                rows = itertools.chain(rows, new_rows)

            # We have all the data, now construct the member objects
            for row in rows:
                key = (row.guildid, row.userid)
                self.lion_members[key] = member_map[key] = LionMember(
                    self.bot,
                    row,
                    lguilds[row.guildid],
                    lusers[row.userid]
                )

        return member_map

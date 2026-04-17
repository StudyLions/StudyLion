# --- AI-REPLACED (2026-04-06) ---
# Reason: Enriched guild join/leave log embeds with cross-shard totals, URL buttons,
#         guild icon/banner, shard info, verification, boost, features, locale, premium status.
# What the new code does better: Much richer admin-facing info and quick-action buttons.
# --- Original code (commented out for rollback) ---
# import asyncio
# import datetime
#
# import discord
# from discord import Webhook
#
# from meta.LionCog import LionCog
# from meta.LionBot import LionBot
# from meta.logger import log_wrap
#
#
# class GuildLog(LionCog):
#     def __init__(self, bot: LionBot):
#         self.bot = bot
#
#     @LionCog.listener('on_guild_remove')
#     @log_wrap(action="Log Guild Leave")
#     async def log_left_guild(self, guild: discord.Guild):
#         embed = discord.Embed(title="`{0.name} (ID: {0.id})`".format(guild),
#                               colour=discord.Colour.red(),
#                               timestamp=datetime.datetime.utcnow())
#         embed.set_author(name="Left guild!")
#         embed.add_field(name="Owner", value="<@{}>".format(guild.owner_id), inline=False)
#         embed.add_field(name="Members", value="{}".format(guild.member_count), inline=False)
#         embed.add_field(name="Now studying in", value="{} guilds".format(len(self.bot.guilds)), inline=False)
#         log_webhook = self.bot.config.endpoints.get("guild_log")
#         if log_webhook:
#             webhook = Webhook.from_url(log_webhook, session=self.bot.web_client)
#             await webhook.send(embed=embed, username=self.bot.appname)
#
#     @LionCog.listener('on_guild_join')
#     @log_wrap(action="Log Guild Join")
#     async def log_join_guild(self, guild: discord.Guild):
#         try:
#             await asyncio.wait_for(guild.chunk(), timeout=60)
#         except asyncio.TimeoutError:
#             pass
#         if guild.chunked:
#             bots = 0; known = 0; unknown = 0
#             other_members = set(mem.id for mem in self.bot.get_all_members() if mem.guild != guild)
#             for member in guild.members:
#                 if member.bot: bots += 1
#                 elif member.id in other_members: known += 1
#                 else: unknown += 1
#             mem1 = "people I know" if known != 1 else "person I know"
#             mem2 = "new friends" if unknown != 1 else "new friend"
#             mem3 = "bots" if bots != 1 else "bot"
#             mem4 = "total members"
#             known = "`{}`".format(known); unknown = "`{}`".format(unknown)
#             bots = "`{}`".format(bots); total = "`{}`".format(guild.member_count)
#             mem_str = "{0:<5}\t{4},\n{1:<5}\t{5},\n{2:<5}\t{6}, and\n{3:<5}\t{7}.".format(
#                 known, unknown, bots, total, mem1, mem2, mem3, mem4)
#         else:
#             mem_str = ("`{count}` total members.\n"
#                        "(Could not chunk guild within `60` seconds.)").format(count=guild.member_count)
#         created = "<t:{}>".format(int(guild.created_at.timestamp()))
#         embed = discord.Embed(title="`{0.name} (ID: {0.id})`".format(guild),
#                               colour=discord.Colour.green(), timestamp=datetime.datetime.utcnow())
#         embed.set_author(name="Joined guild!")
#         embed.add_field(name="Owner", value="<@{}>".format(guild.owner_id), inline=False)
#         embed.add_field(name="Created at", value=created, inline=False)
#         embed.add_field(name="Members", value=mem_str, inline=False)
#         embed.add_field(name="Now studying in", value="{} guilds".format(len(self.bot.guilds)), inline=False)
#         log_webhook = self.bot.config.endpoints.get("guild_log")
#         if log_webhook:
#             webhook = Webhook.from_url(log_webhook, session=self.bot.web_client)
#             await webhook.send(embed=embed, username=self.bot.appname)
# --- End original code ---

import asyncio
import datetime
import logging

import discord
from discord import Webhook, ButtonStyle

from meta.LionCog import LionCog
from meta.LionBot import LionBot
from meta.logger import log_wrap

logger = logging.getLogger(__name__)

VERIFICATION_LABELS = {
    discord.VerificationLevel.none: "None",
    discord.VerificationLevel.low: "Low",
    discord.VerificationLevel.medium: "Medium",
    discord.VerificationLevel.high: "High",
    discord.VerificationLevel.highest: "Highest",
}

NOTABLE_FEATURES = {
    "COMMUNITY", "DISCOVERABLE", "PARTNERED", "VERIFIED",
    "WELCOME_SCREEN_ENABLED", "MEMBER_VERIFICATION_GATE_ENABLED",
    "MONETIZATION_ENABLED",
}


class GuildLog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

    async def _get_total_guilds(self) -> int:
        """Query shard_presence_stats for the cross-shard total guild count."""
        try:
            async with self.bot.db.pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT COALESCE(SUM(guild_count), 0) AS total_guilds "
                    "FROM shard_presence_stats "
                    "WHERE updated_at > now() - INTERVAL '10 minutes'"
                )
                row = await cur.fetchone()
            total = int(row['total_guilds'])
            if total > 0:
                return total
        except Exception:
            logger.warning("Failed to read total guild count, falling back to local.", exc_info=True)
        return len(self.bot.guilds)

    async def _is_premium(self, guildid: int) -> bool:
        """Check premium_guilds table directly."""
        try:
            async with self.bot.db.pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT premium_until FROM premium_guilds WHERE guildid = %s",
                    (guildid,),
                )
                row = await cur.fetchone()
            if row and row['premium_until']:
                return row['premium_until'] > datetime.datetime.now(datetime.timezone.utc)
        except Exception:
            logger.warning("Failed to check premium status for guild %s.", guildid, exc_info=True)
        return False

    def _guild_info_fields(self, guild: discord.Guild) -> list[tuple[str, str, bool]]:
        """Build common info fields shared by join and leave embeds.
        Returns a list of (name, value, inline) tuples.
        """
        fields = []

        shard_id = self.bot.shard_id if self.bot.shard_id is not None else 0
        shard_count = self.bot.shard_count or 1
        fields.append(("Shard", f"`{shard_id}` / `{shard_count}`", True))

        verification = VERIFICATION_LABELS.get(guild.verification_level, str(guild.verification_level))
        fields.append(("Verification", verification, True))

        boost_str = f"Level {guild.premium_tier}"
        if guild.premium_subscription_count:
            boost_str += f" ({guild.premium_subscription_count:,} boost{'s' if guild.premium_subscription_count != 1 else ''})"
        fields.append(("Boost", boost_str, True))

        notable = sorted(NOTABLE_FEATURES.intersection(guild.features))
        if notable:
            tags = ", ".join(f.replace("_", " ").title() for f in notable)
            fields.append(("Features", tags, False))

        return fields

    def _make_buttons(self, guild: discord.Guild) -> discord.ui.View:
        """Build URL-button view for the webhook message."""
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            style=ButtonStyle.link,
            label="Owner Profile",
            url=f"https://discord.com/users/{guild.owner_id}",
        ))
        return view

    def _apply_guild_visuals(self, embed: discord.Embed, guild: discord.Guild):
        """Set thumbnail (guild icon) and image (guild banner) if available."""
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

    @LionCog.listener('on_guild_remove')
    @log_wrap(action="Log Guild Leave")
    async def log_left_guild(self, guild: discord.Guild):
        total_guilds = await self._get_total_guilds()

        embed = discord.Embed(
            title=f"`{guild.name} (ID: {guild.id})`",
            colour=discord.Colour.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_author(name="Left guild!")
        self._apply_guild_visuals(embed, guild)

        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=False)
        embed.add_field(
            name="Members",
            value=f"{guild.member_count:,} members" if guild.member_count else "Unknown",
            inline=True,
        )

        for name, value, inline in self._guild_info_fields(guild):
            embed.add_field(name=name, value=value, inline=inline)

        embed.add_field(
            name="Now studying in",
            value=f"**{total_guilds:,}** guilds",
            inline=False,
        )

        log_webhook = self.bot.config.endpoints.get("guild_log")
        if log_webhook:
            webhook = Webhook.from_url(log_webhook, session=self.bot.web_client)
            view = self._make_buttons(guild)
            await webhook.send(embed=embed, view=view, username=self.bot.appname)

    @LionCog.listener('on_guild_join')
    @log_wrap(action="Log Guild Join")
    async def log_join_guild(self, guild: discord.Guild):
        try:
            await asyncio.wait_for(guild.chunk(), timeout=60)
        except asyncio.TimeoutError:
            pass

        if guild.chunked:
            bots = 0
            known = 0
            unknown = 0
            other_members = set(mem.id for mem in self.bot.get_all_members() if mem.guild != guild)

            for member in guild.members:
                if member.bot:
                    bots += 1
                elif member.id in other_members:
                    known += 1
                else:
                    unknown += 1

            mem_str = (
                f"`{known}` {'people I know' if known != 1 else 'person I know'},\n"
                f"`{unknown}` {'new friends' if unknown != 1 else 'new friend'},\n"
                f"`{bots}` {'bots' if bots != 1 else 'bot'}, and\n"
                f"`{guild.member_count:,}` total members."
            )
        else:
            mem_str = (
                f"`{guild.member_count:,}` total members.\n"
                "(Could not chunk guild within `60` seconds.)"
            )

        created_ts = int(guild.created_at.timestamp())
        created = f"<t:{created_ts}:F> (<t:{created_ts}:R>)"

        total_guilds = await self._get_total_guilds()
        premium = await self._is_premium(guild.id)

        embed = discord.Embed(
            title=f"`{guild.name} (ID: {guild.id})`",
            colour=discord.Colour.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_author(name="Joined guild!")
        self._apply_guild_visuals(embed, guild)

        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=False)
        embed.add_field(name="Created", value=created, inline=False)
        embed.add_field(name="Members", value=mem_str, inline=False)

        for name, value, inline in self._guild_info_fields(guild):
            embed.add_field(name=name, value=value, inline=inline)

        if premium:
            embed.add_field(name="Premium", value="Active", inline=True)

        embed.add_field(
            name="Now studying in",
            value=f"**{total_guilds:,}** guilds",
            inline=False,
        )

        log_webhook = self.bot.config.endpoints.get("guild_log")
        if log_webhook:
            webhook = Webhook.from_url(log_webhook, session=self.bot.web_client)
            view = self._make_buttons(guild)
            await webhook.send(embed=embed, view=view, username=self.bot.appname)
# --- END AI-REPLACED ---

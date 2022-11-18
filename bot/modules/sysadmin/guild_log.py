import datetime

import discord
from discord import Webhook

from meta.LionCog import LionCog
from meta.LionBot import LionBot
from meta.logger import log_wrap


class GuildLog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

    @LionCog.listener('on_guild_remove')
    @log_wrap(action="Log Guild Leave")
    async def log_left_guild(self, guild: discord.Guild):
        # Build embed
        embed = discord.Embed(title="`{0.name} (ID: {0.id})`".format(guild),
                              colour=discord.Colour.red(),
                              timestamp=datetime.datetime.utcnow())
        embed.set_author(name="Left guild!")

        # Add more specific information about the guild
        embed.add_field(name="Owner", value="{0.name} (ID: {0.id})".format(guild.owner), inline=False)
        embed.add_field(name="Members (cached)", value="{}".format(len(guild.members)), inline=False)
        embed.add_field(name="Now studying in", value="{} guilds".format(len(self.bot.guilds)), inline=False)

        # Retrieve the guild log channel and log the event
        log_webhook = self.bot.config.endpoints.get("guild_log")
        if log_webhook:
            webhook = Webhook.from_url(log_webhook, session=self.bot.web_client)
            await webhook.send(embed=embed, username=self.bot.appname)

    @LionCog.listener('on_guild_join')
    @log_wrap(action="Log Guild Join")
    async def log_join_guild(self, guild: discord.Guild):
        owner = guild.owner

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

        mem1 = "people I know" if known != 1 else "person I know"
        mem2 = "new friends" if unknown != 1 else "new friend"
        mem3 = "bots" if bots != 1 else "bot"
        mem4 = "total members"
        known = "`{}`".format(known)
        unknown = "`{}`".format(unknown)
        bots = "`{}`".format(bots)
        total = "`{}`".format(guild.member_count)
        mem_str = "{0:<5}\t{4},\n{1:<5}\t{5},\n{2:<5}\t{6}, and\n{3:<5}\t{7}.".format(
            known,
            unknown,
            bots,
            total,
            mem1,
            mem2,
            mem3,
            mem4
        )
        created = "<t:{}>".format(int(guild.created_at.timestamp()))

        embed = discord.Embed(
            title="`{0.name} (ID: {0.id})`".format(guild),
            colour=discord.Colour.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_author(name="Joined guild!")

        embed.add_field(name="Owner", value="{0} (ID: {0.id})".format(owner), inline=False)
        embed.add_field(name="Created at", value=created, inline=False)
        embed.add_field(name="Members", value=mem_str, inline=False)
        embed.add_field(name="Now studying in", value="{} guilds".format(len(self.bot.guilds)), inline=False)

        # Retrieve the guild log channel and log the event
        log_webhook = self.bot.config.endpoints.get("guild_log")
        if log_webhook:
            webhook = Webhook.from_url(log_webhook, session=self.bot.web_client)
            await webhook.send(embed=embed, username=self.bot.appname)

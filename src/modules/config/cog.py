import discord
from discord import app_commands as appcmds
from discord.ext import commands as cmds

from meta import LionBot, LionContext, LionCog

from . import babel
from .dashboard import GuildDashboard

_p = babel._p


class DashCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

    async def cog_load(self):
        ...

    async def cog_unload(self):
        ...

    @cmds.hybrid_command(
        name="dashboard",
        description="At-a-glance view of the server's configuration."
    )
    @appcmds.guild_only
    async def dashboard_cmd(self, ctx: LionContext):
        ui = GuildDashboard(self.bot, ctx.guild, ctx.author.id, ctx.channel.id)
        await ui.run(ctx.interaction)
        await ui.wait()

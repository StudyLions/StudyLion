import logging
from typing import Optional

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.ui.button import ButtonStyle

from meta import LionBot, LionCog, LionContext
from utils.lib import error_embed
from utils.ui import LeoUI, AButton

from . import babel
from .data import StatsData
from .ui import ProfileUI, WeeklyMonthlyUI
from .settings import StatsSettings

_p = babel._p


logger = logging.getLogger(__name__)


class StatsCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(StatsData())
        self.settings = StatsSettings

    async def cog_load(self):
        await self.data.init()

        self.bot.core.user_config.register_model_setting(self.settings.UserGlobalStats)

    @cmds.hybrid_command(
        name=_p('cmd:me', "me"),
        description=_p(
            'cmd:me|desc',
            "Display your personal profile and summary statistics."
        )
    )
    async def me_cmd(self, ctx: LionContext):
        await ctx.interaction.response.defer(thinking=True)
        ui = ProfileUI(self.bot, ctx.author, ctx.guild)
        await ui.run(ctx.interaction)

    @cmds.hybrid_command(
        name=_p('cmd:stats', "stats"),
        description=_p(
            'cmd:stats|desc',
            "Weekly and monthly statistics for your recent activity."
        )
    )
    async def stats_cmd(self, ctx: LionContext):
        """
        Statistics command.
        """
        await ctx.interaction.response.defer(thinking=True)
        ui = WeeklyMonthlyUI(self.bot, ctx.author, ctx.guild)
        await ui.run(ctx.interaction)

    @cmds.hybrid_command(
        name=_p('cmd:leaderboard', "leaderboard"),
        description=_p(
            'cmd:leaderboard|desc',
            "Server leaderboard."
        )
    )
    @appcmds.guild_only
    async def leaderboard_cmd(self, ctx: LionContext):
        ...

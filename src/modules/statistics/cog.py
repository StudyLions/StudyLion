import logging
from typing import Optional

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.ui.button import ButtonStyle

from meta import LionBot, LionCog, LionContext
from utils.lib import error_embed
from utils.ui import LeoUI, AButton, utc_now
from wards import low_management_ward

from . import babel
from .data import StatsData
from .ui import ProfileUI, WeeklyMonthlyUI, LeaderboardUI
from .settings import StatisticsSettings, StatisticsConfigUI

_p = babel._p


logger = logging.getLogger(__name__)


class StatsCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(StatsData())
        self.settings = StatisticsSettings()

    async def cog_load(self):
        await self.data.init()

        self.bot.core.user_config.register_model_setting(self.settings.UserGlobalStats)
        self.bot.core.guild_config.register_model_setting(self.settings.SeasonStart)
        self.bot.core.guild_config.register_setting(self.settings.UnrankedRoles)

        configcog = self.bot.get_cog('ConfigCog')
        self.crossload_group(self.configure_group, configcog.configure_group)

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
        await ui.wait()

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
        await ui.wait()

    @cmds.hybrid_command(
        name=_p('cmd:leaderboard', "leaderboard"),
        description=_p(
            'cmd:leaderboard|desc',
            "Server leaderboard."
        )
    )
    @appcmds.guild_only
    async def leaderboard_cmd(self, ctx: LionContext):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        if not ctx.guild.chunked:
            t = self.bot.translator.t
            waiting_embed = discord.Embed(
                colour=discord.Colour.greyple(),
                description=t(_p(
                    'cmd:leaderboard|chunking|desc',
                    "Requesting server member list from Discord, please wait {loading}"
                )).format(loading=self.bot.config.emojis.loading),
                timestamp=utc_now(),
            )
            await ctx.interaction.response(embed=waiting_embed)
            await ctx.guild.chunk()
        else:
            await ctx.interaction.response.defer(thinking=True)
        ui = LeaderboardUI(self.bot, ctx.author, ctx.guild)
        await ui.run(ctx.interaction)
        await ui.wait()

    # Setting commands
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        ...

    @configure_group.command(
        name=_p('cmd:configure_statistics', "statistics"),
        description=_p('cmd:configure_statistics|desc', "Statistics configuration panel")
    )
    @appcmds.rename(
        season_start=_p('cmd:configure_statistics|param:season_start', "season_start")
    )
    @appcmds.describe(
        season_start=_p(
            'cmd:configure_statistics|param:season_start|desc',
            "Time from which to start counting activity for rank badges and season leaderboards. (YYYY-MM-DD)"
        )
    )
    @appcmds.default_permissions(manage_guild=True)
    @low_management_ward
    async def configure_statistics_cmd(self, ctx: LionContext,
                                       season_start: Optional[str] = None):
        t = self.bot.translator.t

        # Type checking guards
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # Retrieve settings, using cache where possible
        setting_season_start = await self.settings.SeasonStart.get(ctx.guild.id)

        modified = []
        if season_start is not None:
            data = await setting_season_start._parse_string(ctx.guild.id, season_start)
            setting_season_start.data = data
            await setting_season_start.write()
            modified.append(setting_season_start)

        # Send update ack
        if modified:
            # TODO
            description = t(_p(
                'cmd:configure_statistics|resp:success|desc',
                "Activity ranks and season leaderboard will now be measured from {season_start}."
            )).format(
                season_start=setting_season_start.formatted
            )
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=description
            )
            await ctx.reply(embed=embed)

        if ctx.channel.id not in StatisticsConfigUI._listening or not modified:
            # Launch setting group UI
            configui = StatisticsConfigUI(self.bot, ctx.guild.id, ctx.channel.id)
            await configui.run(ctx.interaction)
            await configui.wait()

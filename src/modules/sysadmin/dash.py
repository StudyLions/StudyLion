"""
The dashboard shows a summary of the various registered global bot settings.
"""

import discord
import discord.ext.commands as cmds

from meta import LionBot, LionCog, LionContext
from meta.app import appname
from wards import sys_admin

from settings.groups import SettingGroup


class LeoSettings(LionCog, group_name='leo'):
    __cog_is_app_commands_group__ = True
    depends = {'CoreCog'}

    def __init__(self, bot: LionBot):
        self.bot = bot

        self.bot_setting_groups: list[SettingGroup] = []

    @cmds.hybrid_command(
        name='dashboard',
        description="Global setting dashboard"
    )
    @cmds.check(sys_admin)
    async def dash_cmd(self, ctx: LionContext):
        embed = discord.Embed(
            title="System Admin Dashboard",
            colour=discord.Colour.orange()
        )
        for group in self.bot_setting_groups:
            table = await group.make_setting_table(appname)
            description = group.description.format(ctx=ctx, bot=ctx.bot).strip()
            embed.add_field(
                name=group.title.format(ctx=ctx, bot=ctx.bot),
                value=f"{description}\n{table}"
            )

        await ctx.reply(embed=embed)

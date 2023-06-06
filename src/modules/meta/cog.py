from typing import Optional
import asyncio

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from wards import low_management
from meta import LionBot, LionCog, LionContext
from utils.ui import AButton, AsComponents

from . import babel
from .helpui import HelpUI

_p = babel._p


class MetaCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

    @cmds.hybrid_command(
        name=_p('cmd:help', "help"),
        description=_p(
            'cmd:help|desc',
            "See a brief summary of my commands and features."
        )
    )
    async def help_cmd(self, ctx: LionContext):
        ui = HelpUI(
            ctx.bot,
            ctx.author,
            ctx.guild,
            show_admin=await low_management(ctx.bot, ctx.author),
        )
        await ui.run(ctx.interaction)

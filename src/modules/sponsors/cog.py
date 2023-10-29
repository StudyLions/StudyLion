from typing import Optional
import asyncio

import discord
from discord.ext import commands as cmds
import discord.app_commands as appcmds

from meta import LionCog, LionBot, LionContext
from wards import sys_admin_ward

from . import logger, babel
from .data import SponsorData
from .settings import SponsorSettings
from .settingui import SponsorUI

_p = babel._p


class SponsorCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data: SponsorData = bot.db.load_registry(SponsorData())
        self.settings = SponsorSettings

        self.whitelisted = self.settings.Whitelist._cache

    async def cog_load(self):
        await self.data.init()
        if (leo_setting_cog := self.bot.get_cog('LeoSettings')) is not None:
            leo_setting_cog.bot_setting_groups.append(self.settings)
            self.crossload_group(self.leo_group, leo_setting_cog.leo_group)

    async def do_sponsor_prompt(self, interaction: discord.Interaction):
        """
        Send the sponsor prompt as a followup to this interaction, if applicable.
        """
        if not interaction.is_expired():
            # TODO: caching
            if interaction.guild:
                whitelist = (await self.settings.Whitelist.get(self.bot.appname)).value
                if interaction.guild.id in whitelist:
                    return
                premiumcog = self.bot.get_cog('PremiumCog')
                if premiumcog and await premiumcog.is_premium_guild(interaction.guild.id):
                    return
            setting = await self.settings.SponsorPrompt.get(self.bot.appname)
            value = setting.value
            if value:
                args = setting.value_to_args(self.bot.appname, value)
                followup = interaction.followup
                await followup.send(**args.send_args, ephemeral=True)

    @cmds.hybrid_command(
        name=_p('cmd:sponsors', "sponsors"),
        description=_p(
            'cmd:sponsors|desc',
            "Check out our wonderful partners!"
        )
    )
    async def sponsor_cmd(self, ctx: LionContext):
        """
        Display the sponsors message, if set.
        """
        if ctx.interaction:
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        sponsor = await self.settings.SponsorMessage.get(self.bot.appname)
        value = sponsor.value
        if value:
            args = sponsor.value_to_args(self.bot.appname, value)
            await ctx.reply(**args.send_args)
        else:
            await ctx.reply(
                "Coming Soon!"
            )

    @LionCog.placeholder_group
    @cmds.hybrid_group("leo", with_app_command=False)
    async def leo_group(self, ctx: LionContext):
        ...

    @leo_group.command(
        name=_p(
            'cmd:leo_sponsors', "sponsors"
        ),
        description=_p(
            'cmd:leo_sponsors|desc',
            "Configure the sponsor text and whitelist."
        )
    )
    @appcmds.rename(
        sponsor_prompt=SponsorSettings.SponsorPrompt._display_name,
        sponsor_message=SponsorSettings.SponsorMessage._display_name,
    )
    @appcmds.describe(
        sponsor_prompt=SponsorSettings.SponsorPrompt._desc,
        sponsor_message=SponsorSettings.SponsorMessage._desc,
    )
    @sys_admin_ward
    async def leo_sponsors_cmd(self, ctx: LionContext,
                               sponsor_prompt: Optional[discord.Attachment] = None,
                               sponsor_message: Optional[discord.Attachment] = None,
                               ):
        """
        Open the configuration UI for sponsors, and optionally set the prompt and message.
        """
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True)
        modified = []

        if sponsor_prompt is not None:
            setting = self.settings.SponsorPrompt
            content = await setting.download_attachment(sponsor_prompt)
            instance = await setting.from_string(self.bot.appname, content)
            modified.append(instance)

        if sponsor_message is not None:
            setting = self.settings.SponsorMessage
            content = await setting.download_attachment(sponsor_message)
            instance = await setting.from_string(self.bot.appname, content)
            modified.append(instance)

        for instance in modified:
            await instance.write()

        ui = SponsorUI(self.bot, self.bot.appname, ctx.channel.id)
        await ui.run(ctx.interaction)
        await ui.wait()

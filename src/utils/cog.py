import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from meta import LionBot, LionContext, LionCog
from .ui import BasePager

from . import util_babel as babel

_p = babel._p


class MetaUtils(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

    @cmds.hybrid_group(
        name=_p('cmd:page', 'page'),
        description=_p(
            'cmd:page|desc',
            "Jump to a given page of the ouput of a previous command in this channel."
        ),
        with_app_command=False
    )
    async def page_group(self, ctx: LionContext):
        """
        No description.
        """
        pass

    async def page_jump(self, ctx: LionContext, jumper):
        pager = BasePager.get_active_pager(ctx.channel.id, ctx.author.id)
        if pager is None:
            await ctx.error_reply(
                _p('cmd:page|error:no_pager', "No pager listening in this channel!")
            )
        else:
            if ctx.interaction:
                await ctx.interaction.response.defer()
            pager.page_num = jumper(pager)
            await pager.redraw()
            if ctx.interaction:
                await ctx.interaction.delete_original_response()

    @page_group.command(
        name=_p('cmd:page_next', 'next'),
        description=_p('cmd:page_next|desc', "Jump to the next page of output.")
    )
    async def next_cmd(self, ctx: LionContext):
        await self.page_jump(ctx, lambda pager: pager.page_num + 1)

    @page_group.command(
        name=_p('cmd:page_prev', 'prev'),
        description=_p('cmd:page_prev|desc', "Jump to the previous page of output.")
    )
    async def prev_cmd(self, ctx: LionContext):
        await self.page_jump(ctx, lambda pager: pager.page_num - 1)

    @page_group.command(
        name=_p('cmd:page_first', 'first'),
        description=_p('cmd:page_first|desc', "Jump to the first page of output.")
    )
    async def first_cmd(self, ctx: LionContext):
        await self.page_jump(ctx, lambda pager: 0)

    @page_group.command(
        name=_p('cmd:page_last', 'last'),
        description=_p('cmd:page_last|desc', "Jump to the last page of output.")
    )
    async def last_cmd(self, ctx: LionContext):
        await self.page_jump(ctx, lambda pager: -1)

    @page_group.command(
        name=_p('cmd:page_select', 'select'),
        description=_p('cmd:page_select|desc', "Select a page of the output to jump to.")
    )
    @appcmds.rename(
        page=_p('cmd:page_select|param:page', 'page')
    )
    @appcmds.describe(
        page=_p('cmd:page_select|param:page|desc', "The page name or number to jump to.")
    )
    async def page_cmd(self, ctx: LionContext, page: str):
        pager = BasePager.get_active_pager(ctx.channel.id, ctx.author.id)
        if pager is None:
            await ctx.error_reply(
                _p('cmd:page_select|error:no_pager', "No pager listening in this channel!")
            )
        else:
            await pager.page_cmd(ctx.interaction, page)

    @page_cmd.autocomplete('page')
    async def page_acmpl(self, interaction: discord.Interaction, partial: str):
        pager = BasePager.get_active_pager(interaction.channel_id, interaction.user.id)
        if pager is None:
            return [
                appcmds.Choice(
                    name=_p('cmd:page_select|acmpl|error:no_pager', "No active pagers in this channel!"),
                    value=partial
                )
            ]
        else:
            return await pager.page_acmpl(interaction, partial)

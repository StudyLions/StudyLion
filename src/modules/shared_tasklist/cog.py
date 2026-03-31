# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Shared tasklist cog — lightweight /board command
# ============================================================
import discord
from discord.ext import commands as cmds

from meta import LionBot, LionCog, LionContext
from utils.lib import utc_now

from . import logger
from .data import SharedTasklistData
from .ui import BoardView


class SharedTasklistCog(LionCog):
    """
    Lightweight Discord interface for shared kanban boards.
    Heavy management (create boards, invite members, history) is on the website.
    Bot provides: view board, tick/untick tasks.
    """
    depends = {'CoreCog'}

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(SharedTasklistData())

    async def cog_load(self):
        await self.data.init()

    @cmds.hybrid_command(
        name="board",
        description="View and interact with your shared kanban boards",
    )
    async def board_cmd(self, ctx: LionContext):
        if not ctx.interaction:
            return
        await ctx.interaction.response.defer(ephemeral=True)

        userid = ctx.author.id
        member_rows = await self.data.Member.fetch_where(userid=userid)
        my_board_ids = {m.listid for m in member_rows}

        if not my_board_ids:
            embed = discord.Embed(
                title="No Boards",
                description=(
                    "You're not a member of any shared boards yet.\n\n"
                    "Create one on the [dashboard](https://lionbot-website.vercel.app/dashboard/boards)!"
                ),
                color=discord.Color.greyple()
            )
            await ctx.interaction.followup.send(embed=embed, ephemeral=True)
            return

        boards = []
        for bid in my_board_ids:
            rows = await self.data.Board.fetch_where(listid=bid, deleted_at=None)
            if rows:
                boards.append(rows[0])

        if not boards:
            embed = discord.Embed(
                title="No Boards",
                description="All your boards have been deleted.",
                color=discord.Color.greyple()
            )
            await ctx.interaction.followup.send(embed=embed, ephemeral=True)
            return

        if len(boards) == 1:
            view = BoardView(self.bot, self.data, boards[0], ctx.author)
            await view.send(ctx.interaction)
            return

        view = BoardSelectView(self.bot, self.data, boards, ctx.author)
        embed = discord.Embed(
            title="Your Boards",
            description="Select a board to view:",
            color=discord.Color.blurple()
        )
        await ctx.interaction.followup.send(embed=embed, view=view, ephemeral=True)


class BoardSelectView(discord.ui.View):
    def __init__(self, bot, data, boards, user):
        super().__init__(timeout=120)
        self.bot = bot
        self.data = data
        self.boards = boards
        self.user = user

        options = []
        for b in boards[:25]:
            options.append(discord.SelectOption(
                label=b.name[:100],
                value=str(b.listid),
                description=(b.description or "")[:100],
            ))

        select = discord.ui.Select(
            placeholder="Choose a board...",
            options=options,
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        listid = int(interaction.data["values"][0])
        board = next((b for b in self.boards if b.listid == listid), None)
        if not board:
            await interaction.response.send_message("Board not found.", ephemeral=True)
            return

        view = BoardView(self.bot, self.data, board, self.user)
        await view.send(interaction)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

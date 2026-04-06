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
from .ui import BoardView, _hex_to_discord_color, _color_to_circle

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
# LazyStr (from babel._p) is not JSON-serializable; resolve to plain str.
from . import babel
def _p(context, message):
    return str(babel._p(context, message))
# --- END AI-MODIFIED ---


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
        description=_p('cmd:board|desc', "View and interact with your shared kanban boards"),
    )
    async def board_cmd(self, ctx: LionContext):
        if not ctx.interaction:
            return
        await ctx.interaction.response.defer(ephemeral=True)

        userid = ctx.author.id
        member_rows = await self.data.Member.fetch_where(userid=userid)
        my_board_ids = {m.listid for m in member_rows}

        if not my_board_ids:
            # --- AI-MODIFIED (2026-04-01) ---
            # Purpose: Add Babel localization for text branding support
            embed = discord.Embed(
                description=_p(
                    'ui:board|no_boards',
                    "\U0001f4cb **No Boards Yet**\n\n"
                    "You're not a member of any shared boards.\n"
                    "Create one on the [dashboard](https://lionbot-website.vercel.app/dashboard/boards)!"
                ),
                color=discord.Color.light_grey()
            )
            # --- END AI-MODIFIED ---
            await ctx.interaction.followup.send(embed=embed, ephemeral=True)
            return

        boards = []
        for bid in my_board_ids:
            rows = await self.data.Board.fetch_where(listid=bid, deleted_at=None)
            if rows:
                boards.append(rows[0])

        if not boards:
            # --- AI-MODIFIED (2026-04-01) ---
            # Purpose: Add Babel localization for text branding support
            embed = discord.Embed(
                description=_p(
                    'ui:board|no_active_boards',
                    "\U0001f4cb **No Active Boards**\n\n"
                    "All your boards have been deleted.\n"
                    "Create a new one on the [dashboard](https://lionbot-website.vercel.app/dashboard/boards)!"
                ),
                color=discord.Color.light_grey()
            )
            # --- END AI-MODIFIED ---
            await ctx.interaction.followup.send(embed=embed, ephemeral=True)
            return

        if len(boards) == 1:
            view = BoardView(self.bot, self.data, boards[0], ctx.author)
            await view.send(ctx.interaction)
            return

        view = BoardSelectView(self.bot, self.data, boards, ctx.author, member_rows)

        board_lines = []
        for b in boards:
            circle = _color_to_circle(b.color)
            board_lines.append(f"{circle} **{b.name}**")
        board_list = "\n".join(board_lines)

        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Add Babel localization for text branding support
        embed = discord.Embed(
            description=_p(
                'ui:board|select_prompt',
                "\U0001f4cb **Your Boards**\n\nSelect a board to view:\n\n{board_list}"
            ).format(board_list=board_list),
            color=discord.Color.blurple()
        )
        embed.set_footer(text=(
            _p('ui:board_select|footer_plural', "{count} boards")
            if len(boards) != 1
            else _p('ui:board_select|footer_single', "{count} board")
        ).format(count=len(boards)))
        # --- END AI-MODIFIED ---
        await ctx.interaction.followup.send(embed=embed, view=view, ephemeral=True)


class BoardSelectView(discord.ui.View):
    def __init__(self, bot, data, boards, user, member_rows):
        super().__init__(timeout=120)
        self.bot = bot
        self.data = data
        self.boards = boards
        self.user = user

        role_map = {m.listid: m.role for m in member_rows}

        options = []
        for b in boards[:25]:
            role = role_map.get(b.listid, "member")
            # --- AI-MODIFIED (2026-04-01) ---
            # Purpose: Add Babel localization for text branding support
            role_label = {
                "owner": _p('ui:board_select|role:owner', "\U0001f451 Owner"),
                "editor": _p('ui:board_select|role:editor', "\u270f\ufe0f Editor"),
                "viewer": _p('ui:board_select|role:viewer', "\U0001f441\ufe0f Viewer"),
            }.get(role, role)
            # --- END AI-MODIFIED ---
            desc = f"{role_label}"
            if b.description:
                desc += f" \u2022 {b.description}"
            options.append(discord.SelectOption(
                label=b.name[:100],
                value=str(b.listid),
                description=desc[:100],
                emoji=_color_to_circle(b.color),
            ))

        select = discord.ui.Select(
            placeholder=_p('ui:board_select|placeholder', "\U0001f4cb Select a board..."),
            options=options,
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        listid = int(interaction.data["values"][0])
        board = next((b for b in self.boards if b.listid == listid), None)
        if not board:
            await interaction.response.send_message(_p('error:board_select|not_found', "Board not found."), ephemeral=True)
            return

        view = BoardView(self.bot, self.data, board, self.user)
        await view.send(interaction)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

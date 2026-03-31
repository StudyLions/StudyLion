# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Discord UI views for shared kanban boards
# ============================================================
import discord
from utils.lib import utc_now
from . import logger


COLUMN_EMOJIS = {
    0: "\U0001f4cb",  # clipboard
    1: "\U0001f504",  # arrows counterclockwise
    2: "\u2705",      # green check
}


class BoardView(discord.ui.View):
    """Displays a board embed with task toggle select menu and action buttons."""

    def __init__(self, bot, data, board, user):
        super().__init__(timeout=300)
        self.bot = bot
        self.data = data
        self.board = board
        self.user = user
        self.columns = []
        self.tasks = []
        self.message = None

    async def send(self, interaction: discord.Interaction):
        await self._load_data()
        embed = self._build_embed()

        self.clear_items()
        self._add_items()

        if interaction.response.is_done():
            self.message = await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)
            self.message = await interaction.original_response()

    async def _load_data(self):
        self.columns = await self.data.Column.fetch_where(listid=self.board.listid)
        self.columns.sort(key=lambda c: c.position)

        self.tasks = await self.data.Task.fetch_where(
            listid=self.board.listid,
            deleted_at=None,
        )

    def _build_embed(self):
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks if t.completed_at)

        embed = discord.Embed(
            title=f"{self.board.name}",
            description="",
            color=discord.Color.blurple(),
        )

        if self.board.description:
            embed.description = f"*{self.board.description}*\n\n"

        col_map = {}
        for col in self.columns:
            col_map[col.columnid] = col

        tasks_by_col = {}
        for t in self.tasks:
            cid = t.columnid or 0
            if cid not in tasks_by_col:
                tasks_by_col[cid] = []
            tasks_by_col[cid].append(t)

        for i, col in enumerate(self.columns):
            emoji = COLUMN_EMOJIS.get(i, "\U0001f4cb")
            col_tasks = tasks_by_col.get(col.columnid, [])
            col_tasks.sort(key=lambda t: t.position)

            if col_tasks:
                lines = []
                for t in col_tasks[:15]:
                    check = "\u2611" if t.completed_at else "\u2610"
                    lines.append(f"  {check} {t.content}")
                if len(col_tasks) > 15:
                    lines.append(f"  *...and {len(col_tasks) - 15} more*")
                value = "\n".join(lines)
            else:
                value = "  *No tasks*"

            embed.add_field(
                name=f"{emoji} {col.name} ({len(col_tasks)})",
                value=value,
                inline=False,
            )

        embed.set_footer(text=f"{completed}/{total} tasks complete")
        return embed

    def _add_items(self):
        incomplete = [t for t in self.tasks if not t.completed_at]
        completed_tasks = [t for t in self.tasks if t.completed_at]

        if incomplete:
            options = []
            for t in incomplete[:25]:
                options.append(discord.SelectOption(
                    label=t.content[:100],
                    value=f"complete:{t.taskid}",
                    description="Mark as complete",
                    emoji="\u2610",
                ))
            select = discord.ui.Select(
                placeholder="Mark a task as complete...",
                options=options,
                custom_id="board_toggle_task",
            )
            select.callback = self._on_toggle
            self.add_item(select)

        if completed_tasks and not incomplete:
            options = []
            for t in completed_tasks[:25]:
                options.append(discord.SelectOption(
                    label=t.content[:100],
                    value=f"uncomplete:{t.taskid}",
                    description="Mark as incomplete",
                    emoji="\u2611",
                ))
            select = discord.ui.Select(
                placeholder="Reopen a task...",
                options=options,
                custom_id="board_untoggle_task",
            )
            select.callback = self._on_toggle
            self.add_item(select)

        refresh_btn = discord.ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            emoji="\U0001f504",
        )
        refresh_btn.callback = self._on_refresh
        self.add_item(refresh_btn)

        website_url = f"https://lionbot-website.vercel.app/dashboard/boards/{self.board.listid}"
        link_btn = discord.ui.Button(
            label="Open on Website",
            style=discord.ButtonStyle.link,
            url=website_url,
        )
        self.add_item(link_btn)

    async def _on_toggle(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        action, taskid_str = value.split(":", 1)
        taskid = int(taskid_str)

        task = next((t for t in self.tasks if t.taskid == taskid), None)
        if not task:
            await interaction.response.send_message("Task not found.", ephemeral=True)
            return

        member = await self.data.Member.fetch_where(
            listid=self.board.listid,
            userid=interaction.user.id,
        )
        if not member or member[0].role == "viewer":
            await interaction.response.send_message("You need editor access to modify tasks.", ephemeral=True)
            return

        now = utc_now()
        if action == "complete":
            await self.data.Task.table.update_where(
                taskid=taskid,
                completed_at=now,
                last_updated_at=now,
            )
            history_action = "task_completed"
        else:
            await self.data.Task.table.update_where(
                taskid=taskid,
                completed_at=None,
                last_updated_at=now,
            )
            history_action = "task_uncompleted"

        await self.data.history.insert(
            listid=self.board.listid,
            taskid=taskid,
            userid=interaction.user.id,
            action=history_action,
            details=f'{{"content": "{task.content}"}}',
        )

        await self._load_data()
        embed = self._build_embed()
        self.clear_items()
        self._add_items()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_refresh(self, interaction: discord.Interaction):
        await self._load_data()
        embed = self._build_embed()
        self.clear_items()
        self._add_items()
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

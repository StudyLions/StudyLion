# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-31
# Purpose: Discord UI views for shared kanban boards
# ============================================================
import json
import discord
from utils.lib import utc_now
from . import logger

# --- AI-MODIFIED (2026-04-01) ---
# Purpose: Add Babel localization for text branding support
# LazyStr (from babel._p) is not JSON-serializable; resolve to plain str.
from . import babel
def _p(context, message):
    return str(babel._p(context, message))
# --- END AI-MODIFIED ---


def _hex_to_discord_color(hex_str):
    """Convert a hex color string like '#6366f1' to a discord.Color."""
    if not hex_str:
        return discord.Color.blurple()
    try:
        return discord.Color(int(hex_str.lstrip("#"), 16))
    except (ValueError, TypeError):
        return discord.Color.blurple()


def _color_to_circle(hex_str):
    """Map a hex color to the closest colored circle emoji."""
    if not hex_str:
        return "\u26aa"
    try:
        r, g, b = int(hex_str[1:3], 16), int(hex_str[3:5], 16), int(hex_str[5:7], 16)
    except (ValueError, IndexError):
        return "\u26aa"
    options = [
        ((239, 68, 68), "\U0001f534"),    # red
        ((249, 115, 22), "\U0001f7e0"),   # orange
        ((234, 179, 8), "\U0001f7e1"),    # yellow
        ((34, 197, 94), "\U0001f7e2"),    # green
        ((59, 130, 246), "\U0001f535"),   # blue
        ((168, 85, 247), "\U0001f7e3"),   # purple
        ((255, 255, 255), "\u26aa"),      # white
    ]
    best, best_dist = "\u26aa", float("inf")
    for (cr, cg, cb), emoji in options:
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < best_dist:
            best, best_dist = emoji, dist
    return best


def _progress_bar(completed, total, length=12):
    """Render a text-based progress bar."""
    if total == 0:
        return "\u2500" * length + " " + _p('ui:board|no_tasks', "*No tasks*")
    pct = completed / total
    filled = round(pct * length)
    bar = "\u2501" * filled + "\u2500" * (length - filled)
    return _p(
        'ui:board|progress_bar', "`{bar}` **{completed}**/{total} done ({pct}%)"
    ).format(bar=bar, completed=completed, total=total, pct=round(pct * 100))


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
        self.members = []
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

        self.members = await self.data.Member.fetch_where(listid=self.board.listid)

    def _build_embed(self):
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks if t.completed_at)

        embed_color = _hex_to_discord_color(self.board.color)
        embed = discord.Embed(color=embed_color)

        embed.set_author(
            name=self.board.name,
            icon_url=self.user.avatar.url if self.user.avatar else None,
        )

        desc_lines = []
        if self.board.description:
            desc_lines.append(f"*{self.board.description}*")
            desc_lines.append("")

        desc_lines.append(_progress_bar(completed, total))
        desc_lines.append("")

        embed.description = "\n".join(desc_lines)

        tasks_by_col = {}
        for t in self.tasks:
            cid = t.columnid or 0
            if cid not in tasks_by_col:
                tasks_by_col[cid] = []
            tasks_by_col[cid].append(t)

        for col in self.columns:
            circle = _color_to_circle(col.color)
            col_tasks = tasks_by_col.get(col.columnid, [])
            col_tasks.sort(key=lambda t: t.position)

            if col_tasks:
                lines = []
                for t in col_tasks[:10]:
                    if t.completed_at:
                        lines.append(f"\u2003\u2714\ufe0f ~~{t.content}~~")
                    else:
                        lines.append(f"\u2003\u25fb {t.content}")
                if len(col_tasks) > 10:
                    lines.append(
                        _p('ui:board|more_tasks', "\u2003\u22ef *+{count} more*")
                        .format(count=len(col_tasks) - 10)
                    )
                value = "\n".join(lines)
            else:
                value = _p('ui:board|empty_column', "\u2003*\u2014 empty \u2014*")

            embed.add_field(
                name=f"{circle} {col.name} \u2014 {len(col_tasks)}",
                value=value,
                inline=False,
            )

        member_count = len(self.members)
        # --- AI-MODIFIED (2026-04-01) ---
        # Purpose: Add Babel localization for text branding support
        footer_parts = [(
            _p('ui:board|footer_members_plural', "\U0001f465 {count} members")
            if member_count != 1
            else _p('ui:board|footer_members_single', "\U0001f465 {count} member")
        ).format(count=member_count)]
        if self.board.updated_at:
            footer_parts.append(_p('ui:board|footer_updated', "Last updated"))
        # --- END AI-MODIFIED ---
        embed.set_footer(text=" \u2022 ".join(footer_parts))
        if self.board.updated_at:
            embed.timestamp = self.board.updated_at

        return embed

    def _add_items(self):
        incomplete = [t for t in self.tasks if not t.completed_at]
        completed_tasks = [t for t in self.tasks if t.completed_at]

        if incomplete:
            options = []
            for t in incomplete[:25]:
                col = next((c for c in self.columns if c.columnid == t.columnid), None)
                desc = _p('ui:board|task_in_column', "in {column}").format(column=col.name) if col else _p('ui:board|task_unassigned', "Unassigned")
                options.append(discord.SelectOption(
                    label=t.content[:100],
                    value=f"complete:{t.taskid}",
                    description=desc[:100],
                    emoji="\u25fb\ufe0f",
                ))
            select = discord.ui.Select(
                placeholder=_p('ui:board|mark_complete_placeholder',
                               "\u2714 Mark complete ({count} remaining)").format(count=len(incomplete)),
                options=options,
            )
            select.callback = self._on_toggle
            self.add_item(select)

        if completed_tasks:
            options = []
            for t in completed_tasks[:25]:
                col = next((c for c in self.columns if c.columnid == t.columnid), None)
                desc = _p('ui:board|task_in_column', "in {column}").format(column=col.name) if col else _p('ui:board|task_unassigned', "Unassigned")
                options.append(discord.SelectOption(
                    label=t.content[:100],
                    value=f"uncomplete:{t.taskid}",
                    description=desc[:100],
                    emoji="\u2705",
                ))
            select = discord.ui.Select(
                placeholder=_p('ui:board|reopen_placeholder',
                               "\u21a9 Reopen task ({count} done)").format(count=len(completed_tasks)),
                options=options,
            )
            select.callback = self._on_toggle
            self.add_item(select)

        refresh_btn = discord.ui.Button(
            label=_p('ui:board|button:refresh', "Refresh"),
            style=discord.ButtonStyle.secondary,
            emoji="\U0001f504",
        )
        refresh_btn.callback = self._on_refresh
        self.add_item(refresh_btn)

        website_url = f"https://lionbot-website.vercel.app/dashboard/boards/{self.board.listid}"
        link_btn = discord.ui.Button(
            label=_p('ui:board|button:manage_website', "Manage on Website"),
            style=discord.ButtonStyle.link,
            url=website_url,
            emoji="\U0001f310",
        )
        self.add_item(link_btn)

    async def _on_toggle(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        action, taskid_str = value.split(":", 1)
        taskid = int(taskid_str)

        task = next((t for t in self.tasks if t.taskid == taskid), None)
        if not task:
            await interaction.response.send_message(_p('error:board|task_not_found', "Task not found."), ephemeral=True)
            return

        member = await self.data.Member.fetch_where(
            listid=self.board.listid,
            userid=interaction.user.id,
        )
        if not member or member[0].role == "viewer":
            await interaction.response.send_message(_p('error:board|editor_required', "You need editor access to modify tasks."), ephemeral=True)
            return

        now = utc_now()
        if action == "complete":
            await self.data.Task.table.update_where(
                taskid=taskid,
            ).set(completed_at=now, last_updated_at=now)
            history_action = "task_completed"
        else:
            await self.data.Task.table.update_where(
                taskid=taskid,
            ).set(completed_at=None, last_updated_at=now)
            history_action = "task_uncompleted"

        await self.data.history.insert(
            listid=self.board.listid,
            taskid=taskid,
            userid=interaction.user.id,
            action=history_action,
            details=json.dumps({"content": task.content}),
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

from typing import Optional
import re

import discord
from discord.ui.select import select, Select, SelectOption
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.text_input import TextInput, TextStyle

from meta import conf
from meta.errors import UserInputError
from utils.lib import MessageArgs, utc_now
from utils.ui import LeoUI, LeoModal, FastModal, error_handler_for, ModalRetryUI
from utils.ui.pagers import BasePager, Pager
from babel.translator import ctx_translator

from . import babel, logger
from .tasklist import Tasklist
from .data import TasklistData

_p = babel._p

checkmark = "✔"
checked_emoji = conf.emojis.task_checked
unchecked_emoji = conf.emojis.task_unchecked


class SingleEditor(FastModal):
    task: TextInput = TextInput(
        label='',
        max_length=100,
        required=True
    )

    def setup_task(self):
        t = ctx_translator.get().t
        self.task.label = t(_p('modal:tasklist_single_editor|field:task|label', "Task content"))

    parent: TextInput = TextInput(
        label='',
        max_length=10,
        required=False
    )

    def setup_parent(self):
        t = ctx_translator.get().t
        self.parent.label = t(_p(
            'modal:tasklist_single_editor|field:parent|label',
            "Parent Task"
        ))
        self.parent.placeholder = t(_p(
            'modal:tasklist_single_editor|field:parent|placeholder',
            "Enter a task number, e.g. 2.1"
        ))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup()

    def setup(self):
        self.setup_task()
        self.setup_parent()

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction: discord.Interaction, error: UserInputError):
        await ModalRetryUI(self, error.msg).respond_to(interaction)


class BulkEditor(LeoModal):
    """
    Error-handling modal for bulk-editing a tasklist.
    """
    line_regex = re.compile(r"(?P<depth>\s*)-?\s*(\[\s*(?P<check>[^]]?)\s*\]\s*)?(?P<content>.*)")

    tasklist_editor: TextInput = TextInput(
        label='',
        style=TextStyle.long,
        max_length=4000,
        required=False
    )

    def setup_tasklist_editor(self):
        t = ctx_translator.get().t
        self.tasklist_editor.label = t(_p(
            'modal:tasklist_bulk_editor|field:tasklist|label', "Tasklist"
        ))
        self.tasklist_editor.placeholder = t(_p(
            'modal:tasklist_bulk_editor|field:tasklist|placeholder',
            "- [ ] This is task 1, unfinished.\n"
            "- [x] This is task 2, finished.\n"
            "  - [ ] This is subtask 2.1."
        ))

    def __init__(self, tasklist: Tasklist, **kwargs):
        self.setup()
        super().__init__(**kwargs)

        self.tasklist = tasklist
        self.bot = tasklist.bot
        self.userid = tasklist.userid

        self.lines = self.format_tasklist()
        self.tasklist_editor.default = '\n'.join(self.lines.values())

        self._callbacks = []

    def setup(self):
        t = ctx_translator.get().t
        self.title = t(_p(
            'modal:tasklist_bulk_editor', "Tasklist Editor"
        ))
        self.setup_tasklist_editor()

    def add_callback(self, coro):
        self._callbacks.append(coro)
        return coro

    def format_tasklist(self):
        """
        Format the tasklist into lines of editable text.
        """
        labelled = self.tasklist.labelled
        lines = {}
        total_len = 0
        for label, task in labelled.items():
            prefix = '  ' * (len(label) - 1)
            box = '- [ ]' if task.completed_at is None else '- [x]'
            line = f"{prefix}{box} {task.content}"
            if total_len + len(line) > 4000:
                break
            lines[task.taskid] = line
            total_len += len(line)
        return lines

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.parse_editor()
            for coro in self._callbacks:
                await coro(interaction)
            await interaction.response.defer()
        except UserInputError as error:
            await ModalRetryUI(self, error.msg).respond_to(interaction)

    def _parser(self, task_lines):
        t = ctx_translator.get().t
        taskinfo = []  # (parent, truedepth, ticked, content)
        depthtree = []  # (depth, index)

        for line in task_lines:
            match = self.line_regex.match(line)
            if not match:
                raise UserInputError(
                    t(_p(
                        'modal:tasklist_bulk_editor|error:parse_task',
                        "Malformed taskline!\n`{input}`"
                    )).format(input=line)
                )
            depth = len(match['depth'])
            check = bool(match['check'])
            content = match['content']
            if not content:
                continue
            if len(content) > 100:
                raise UserInputError(
                    t(_p(
                        'modal:tasklist_bulk_editor|error:task_too_long',
                        "Please keep your tasks under 100 characters!"
                    ))
                )

            for i in range(len(depthtree)):
                lastdepth = depthtree[-1][0]
                if lastdepth >= depth:
                    depthtree.pop()
                if lastdepth <= depth:
                    break
            parent = depthtree[-1][1] if depthtree else None
            depthtree.append((depth, len(taskinfo)))
            taskinfo.append((parent, len(depthtree) - 1, check, content))
        return taskinfo

    async def parse_editor(self):
        # First parse each line
        new_lines = self.tasklist_editor.value.splitlines()
        taskinfo = self._parser(new_lines)

        old_info = self._parser(self.lines.values())
        same_layout = (
            len(old_info) == len(taskinfo)
            and all(info[:2] == oldinfo[:2] for (info, oldinfo) in zip(taskinfo, old_info))
        )

        # TODO: Incremental/diff editing
        conn = await self.bot.db.get_connection()
        async with conn.transaction():
            now = utc_now()

            if same_layout:
                # if the layout has not changed, just edit the tasks
                for taskid, (oldinfo, newinfo) in zip(self.lines.keys(), zip(old_info, taskinfo)):
                    args = {}
                    if oldinfo[2] != newinfo[2]:
                        args['completed_at'] = now if newinfo[2] else None
                    if oldinfo[3] != newinfo[3]:
                        args['content'] = newinfo[3]
                    if args:
                        await self.tasklist.update_tasks(taskid, **args)
            else:
                # Naive implementation clearing entire tasklist
                # Clear tasklist
                await self.tasklist.update_tasklist(deleted_at=now)

                # Create tasklist
                created = {}
                target_depth = 0
                while True:
                    to_insert = {}
                    for i, (parent, truedepth, ticked, content) in enumerate(taskinfo):
                        if truedepth == target_depth:
                            to_insert[i] = (
                                self.tasklist.userid,
                                content,
                                created[parent] if parent is not None else None,
                                now if ticked else None
                            )
                    if to_insert:
                        # Batch insert
                        tasks = await self.tasklist.data.Task.table.insert_many(
                            ('userid', 'content', 'parentid', 'completed_at'),
                            *to_insert.values()
                        )
                        for i, task in zip(to_insert.keys(), tasks):
                            created[i] = task['taskid']
                        target_depth += 1
                    else:
                        # Reached maximum depth
                        break


class TasklistUI(BasePager):
    """
    Paged UI panel for managing the tasklist.
    """
    # Cache of live tasklist widgets
    # (channelid, userid) -> Tasklist
    _live_ = {}

    def __init__(self,
                 tasklist: Tasklist,
                 channel: discord.abc.Messageable, guild: Optional[discord.Guild] = None, **kwargs):
        kwargs.setdefault('timeout', 3600)
        super().__init__(**kwargs)

        self.tasklist = tasklist
        self.bot = tasklist.bot
        self.userid = tasklist.userid
        self.channel = channel
        self.guild = guild

        # List of lists of (label, task) pairs
        self._pages = []

        self.page_num = -1
        self._channelid = channel.id
        self.current_page = None

        self._deleting = False

        self._message: Optional[discord.Message] = None

        self.button_labels()
        self.set_active()

    @classmethod
    async def fetch(cls, tasklist, channel, *args, **kwargs):
        key = (channel.id, tasklist.userid)
        if key not in cls._live_:
            self = cls(tasklist, channel, *args, **kwargs)
            cls._live_[key] = self
        return cls._live_[key]

    def access_check(self, userid):
        return userid == self.userid

    async def interaction_check(self, interaction: discord.Interaction):
        t = self.bot.translator.t
        if not self.access_check(interaction.user.id):
            embed = discord.Embed(
                description=t(_p(
                    'ui:tasklist|error:wrong_user',
                    "This is not your tasklist!"
                )),
                colour=discord.Colour.brand_red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        else:
            return True

    async def cleanup(self):
        self.set_inactive()
        self._live_.pop((self.channel.id, self.userid), None)

        if self._message is not None:
            try:
                await self._message.edit(view=None)
            except discord.HTTPException:
                pass
            self._message = None

        try:
            if self._message is not None:
                await self._message.edit(view=None)
        except discord.HTTPException:
            pass

    async def summon(self):
        """
        Refresh and re-display the tasklist widget as required.
        """
        await self.refresh()

        resend = not await self._check_recent()
        if resend and self._message:
            # Delete our current message if possible
            try:
                await self._message.delete()
            except discord.HTTPException:
                # If we cannot delete, it has probably already been deleted
                # Or we don't have permission somehow
                pass
            self._message = None

        # Redraw
        try:
            await self.redraw()
        except discord.HTTPException:
            if self._message:
                self._message = None
                await self.redraw()

    async def _check_recent(self) -> bool:
        """
        Check whether the tasklist message is a "recent" message in the channel.
        """
        if self._message is not None:
            height = 0
            async for message in self.channel.history(limit=5):
                if message.id == self._message.id:
                    return True
                if message.id < self._message.id:
                    return False
                if message.attachments or message.embeds or height > 20:
                    return False
                height += len(message.content.count('\n'))
            return False
        return False

    async def get_page(self, page_id) -> MessageArgs:
        t = self.bot.translator.t

        tasks = [t for t in self.tasklist.tasklist.values() if t.deleted_at is None]
        total = len(tasks)
        completed = sum(t.completed_at is not None for t in tasks)

        if self.guild:
            user = self.guild.get_member(self.userid)
        else:
            user = self.bot.get_user(self.userid)
        user_name = user.name if user else str(self.userid)
        user_colour = user.colour if user else discord.Color.orange()

        author = t(_p(
            'ui:tasklist|embed|author',
            "{name}'s tasklist ({completed}/{total} complete)"
        )).format(
            name=user_name,
            completed=completed,
            total=total
        )

        embed = discord.Embed(
            colour=user_colour,
        )
        embed.set_author(
            name=author,
            icon_url=user.avatar if user else None
        )

        if self._pages:
            page = self._pages[page_id % len(self._pages)]
            block = self._format_page(page)
            embed.description = "{task_block}".format(task_block=block)
        else:
            embed.description = t(_p(
                'ui:tasklist|embed|description',
                "**You have no tasks on your tasklist!**\n"
                "Add a task with `/tasklist new`, or by pressing the `New` button below."
            ))

        page_args = MessageArgs(embed=embed)
        return page_args

    async def page_cmd(self, interaction: discord.Interaction, value: str):
        return await Pager.page_cmd(self, interaction, value)

    async def page_acmpl(self, interaction: discord.Interaction, partial: str):
        return await Pager.page_acmpl(self, interaction, partial)

    def _format_page(self, page: list[tuple[tuple[int, ...], TasklistData.Task]]) -> str:
        """
        Format a single block of page data into the task codeblock.
        """
        lines = []
        numpad = max(sum(len(str(counter)) - 1 for counter in label) for label, _ in page)
        for label, task in page:
            label_string = '.'.join(map(str, label)) + '.' * (len(label) == 1)
            number = f"**`{label_string}`**"
            if len(label) > 1:
                depth = sum(len(str(c)) + 1 for c in label[:-1]) * ' '
                depth = f"`{depth}`"
            else:
                depth = ''
            task_string = "{depth}{cross}{number} {content}{cross}".format(
                depth=depth,
                number=number,
                emoji=unchecked_emoji if task.completed_at is None else checked_emoji,
                content=task.content,
                cross='~~' if task.completed_at is not None else ''
            )
            lines.append(task_string)
        return '\n'.join(lines)

    def _format_page_text(self, page: list[tuple[tuple[int, ...], TasklistData.Task]]) -> str:
        """
        Format a single block of page data into the task codeblock.
        """
        lines = []
        numpad = max(sum(len(str(counter)) - 1 for counter in label) for label, _ in page)
        for label, task in page:
            box = '[ ]' if task.completed_at is None else f"[{checkmark}]"
            task_string = "{prepad}   {depth} {content}".format(
                prepad=' ' * numpad,
                depth=(len(label) - 1) * '   ',
                content=task.content
            )
            label_string = '.'.join(map(str, label)) + '.' * (len(label) == 1)
            taskline = box + ' ' + label_string + task_string[len(label_string):]
            lines.append(taskline)
        return "```md\n{}```".format('\n'.join(lines))

    def refresh_pages(self):
        labelled = list(self.tasklist.labelled.items())
        count = len(labelled)
        pages = []

        if count > 0:
            # Break into pages
            edges = [0]
            line_ptr = 0
            while line_ptr < count:
                line_ptr += 20
                if line_ptr < count:
                    # Seek backwards to find the best parent
                    i = line_ptr - 5
                    minlabel = (i, len(labelled[i][0]))
                    while i < line_ptr:
                        i += 1
                        ilen = len(labelled[i][0])
                        if ilen <= minlabel[1]:
                            minlabel = (i, ilen)
                    line_ptr = minlabel[0]
                else:
                    line_ptr = count
                edges.append(line_ptr)

            pages = [labelled[edges[i]:edges[i+1]] for i in range(len(edges) - 1)]

        self._pages = pages
        return pages

    @select(placeholder="TOGGLE_PLACEHOLDER")
    async def toggle_selector(self, interaction: discord.Interaction, selected: Select):
        await interaction.response.defer()
        taskids = list(map(int, selected.values))
        tasks = await self.tasklist.fetch_tasks(*taskids)
        to_complete = [task for task in tasks if task.completed_at is None]
        to_uncomplete = [task for task in tasks if task.completed_at is not None]
        if to_complete:
            await self.tasklist.update_tasks(
                *(t.taskid for t in to_complete),
                cascade=True,
                completed_at=utc_now()
            )
            if self.guild:
                if (member := self.guild.get_member(self.userid)):
                    self.bot.dispatch('tasks_completed', member, *(t.taskid for t in to_complete))
        if to_uncomplete:
            await self.tasklist.update_tasks(
                *(t.taskid for t in to_uncomplete),
                completed_at=None
            )
        await self.refresh()
        await self.redraw()

    async def toggle_selector_refresh(self):
        t = self.bot.translator.t
        self.toggle_selector.placeholder = t(_p(
            'ui:tasklist|menu:toggle_selector|placeholder',
            "Select to Toggle"
        ))
        options = []
        block = self._pages[self.page_num % len(self._pages)]
        colwidth = max(sum(len(str(c)) + 1 for c in lbl) for lbl, _ in block)
        for lbl, task in block:
            value = str(task.taskid)
            lblstr = '.'.join(map(str, lbl)) + '.' * (len(lbl) == 1)
            name = f"{lblstr:<{colwidth}} {task.content}"
            emoji = unchecked_emoji if task.completed_at is None else checked_emoji
            options.append(SelectOption(label=name, value=value, emoji=emoji))

        self.toggle_selector.options = options
        self.toggle_selector.min_values = 0
        self.toggle_selector.max_values = len(options)

    @button(label="NEW_PLACEHOLDER", style=ButtonStyle.green)
    async def new_pressed(self, interaction: discord.Interaction, pressed: Button):
        t = self.bot.translator.t
        editor = SingleEditor(
            title=t(_p('ui:tasklist_single_editor|title', "Add task"))
        )

        @editor.submit_callback()
        async def create_task(interaction):
            new_task = editor.task.value
            parent = editor.parent.value
            pid = self.tasklist.parse_label(parent) if parent else None
            if parent and pid is None:
                # Could not parse
                raise UserInputError(
                    t(_p(
                        'ui:tasklist_single_editor|error:parse_parent',
                        "Could not find the given parent task number `{input}` in your tasklist."
                    )).format(input=parent)
                )
            await interaction.response.defer()
            await self.tasklist.create_task(new_task, parentid=pid)
            await self.refresh()
            await self.redraw()

        await interaction.response.send_modal(editor)

    @button(label="EDITOR_PLACEHOLDER", style=ButtonStyle.blurple)
    async def edit_pressed(self, interaction: discord.Interaction, pressed: Button):
        editor = BulkEditor(self.tasklist)

        @editor.add_callback
        async def editor_callback(interaction: discord.Interaction):
            await self.refresh()
            await self.redraw()

        await interaction.response.send_modal(editor)

    @button(label="DELETE_PLACEHOLDER", style=ButtonStyle.red)
    async def del_pressed(self, interaction: discord.Interaction, pressed: Button):
        self._deleting = 1 - self._deleting
        await interaction.response.defer()
        await self.refresh()
        await self.redraw()

    @select(placeholder="DELETE_SELECT_PLACEHOLDER")
    async def delete_selector(self, interaction: discord.Interaction, selected: Select):
        await interaction.response.defer()
        taskids = list(map(int, selected.values))
        if taskids:
            await self.tasklist.update_tasks(
                *taskids,
                cascade=True,
                deleted_at=utc_now()
            )
            await self.refresh()
            await self.redraw()

    async def delete_selector_refresh(self):
        t = self.bot.translator.t
        self.delete_selector.placeholder = t(_p('ui:tasklist|menu:delete|placeholder', "Select to Delete"))
        self.delete_selector.options = self.toggle_selector.options
        self.delete_selector.max_values = len(self.toggle_selector.options)

    @button(label="ClOSE_PLACEHOLDER", style=ButtonStyle.red)
    async def close_pressed(self, interaction: discord.Interaction, pressed: Button):
        await interaction.response.defer()
        if self._message is not None:
            try:
                await self._message.delete()
            except discord.HTTPException:
                pass
        await self.close()

    @button(label="CLEAR_PLACEHOLDER", style=ButtonStyle.red)
    async def clear_pressed(self, interaction: discord.Interaction, pressed: Button):
        await interaction.response.defer()
        await self.tasklist.update_tasklist(
            deleted_at=utc_now(),
        )
        await self.refresh()
        await self.redraw()

    def button_labels(self):
        t = self.bot.translator.t
        self.new_pressed.label = t(_p('ui:tasklist|button:new', "New"))
        self.edit_pressed.label = t(_p('ui:tasklist|button:edit', "Edit"))
        self.del_pressed.label = t(_p('ui:tasklist|button:delete', "Delete"))
        self.clear_pressed.label = t(_p('ui:tasklist|button:clear', "Clear"))
        self.close_pressed.label = t(_p('ui:tasklist|button:close', "Close"))

    async def refresh(self):
        # Refresh data
        await self.tasklist.refresh()
        self.refresh_pages()

    async def redraw(self):
        self.current_page = await self.get_page(self.page_num)

        # Refresh the layout
        if len(self._pages) > 1:
            # Paged layout
            await self.toggle_selector_refresh()
            self._layout = [
                (self.new_pressed, self.edit_pressed, self.del_pressed),
                (self.toggle_selector,),
                (self.prev_page_button, self.close_pressed, self.next_page_button)
            ]
            if self._deleting:
                await self.delete_selector_refresh()
                self._layout.append((self.delete_selector,))
                self._layout[0] = (*self._layout[0], self.clear_pressed)
        elif len(self.tasklist.tasklist) > 0:
            # Single page, with tasks
            await self.toggle_selector_refresh()
            self._layout = [
                (self.new_pressed, self.edit_pressed, self.del_pressed, self.close_pressed),
                (self.toggle_selector,),
            ]
            if self._deleting:
                await self.delete_selector_refresh()
                self._layout[0] = (*self._layout[0], self.clear_pressed)
                self._layout.append((self.delete_selector,))
        else:
            # With no tasks, nothing to select
            self._layout = [
                (self.new_pressed, self.edit_pressed, self.close_pressed)
            ]

        # Resend
        if not self._message:
            self._message = await self.channel.send(**self.current_page.send_args, view=self)
        else:
            await self._message.edit(**self.current_page.edit_args, view=self)

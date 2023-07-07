from typing import Optional
from collections import defaultdict
from enum import Enum
import asyncio
import re
from io import StringIO

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


class TasklistCaller(LeoUI):
    def __init__(self, bot, **kwargs):
        kwargs.setdefault('timeout', None)
        super().__init__(**kwargs)
        self.bot = bot
        self.tasklist_callback.label = bot.translator.t(_p(
            'ui:tasklist_caller|button:tasklist|label',
            "Open Tasklist"
        ))

    @button(label='TASKLIST_PLACEHOLDER', custom_id='open_tasklist', style=ButtonStyle.blurple)
    async def tasklist_callback(self, press: discord.Interaction, pressed: Button):
        cog = self.bot.get_cog('TasklistCog')
        await cog.call_tasklist(press)


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
        max_length=120,
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
        self.labelled = tasklist.labelled
        self.userid = tasklist.userid

        self.lines = tasklist.flatten()
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

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.parse_editor()
            for coro in self._callbacks:
                await coro(interaction)
            await interaction.response.defer()
        except UserInputError as error:
            await ModalRetryUI(self, error.msg).respond_to(interaction)

    async def parse_editor(self):
        # First parse each line
        new_lines = self.tasklist_editor.value.splitlines()
        taskinfo = self.tasklist.parse_tasklist(new_lines)

        old_info = self.tasklist.parse_tasklist(self.lines.values())
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
                await self.tasklist.write_taskinfo(taskinfo)


class UIMode(Enum):
    TOGGLE = (
        _p(
            'ui:tasklist|menu:main|mode:toggle|placeholder',
            "Select to Toggle"
        ),
        _p(
            'ui:tasklist|menu:sub|mode:toggle|placeholder',
            "Toggle from {label}.*"
        ),
    )
    EDIT = (
        _p(
            'ui:tasklist|menu:main|mode:edit|placeholder',
            "Select to Edit"
        ),
        _p(
            'ui:tasklist|menu:sub|mode:edit|placeholder',
            "Edit from {label}.*"
        ),
    )
    DELETE = (
        _p(
            'ui:tasklist|menu:main|mode:delete|placeholder',
            "Select to Delete"
        ),
        _p(
            'ui:tasklist|menu:sub|mode:delete|placeholder',
            "Delete from {label}.*"
        ),
    )

    @property
    def main_placeholder(self):
        return self.value[0]

    @property
    def sub_placeholder(self):
        return self.value[1]


class TasklistUI(BasePager):
    """
    Paged UI panel for managing the tasklist.
    """
    # Cache of live tasklist widgets
    # userid -> channelid -> TasklistUI
    _live_ = defaultdict(dict)

    def __init__(self,
                 tasklist: Tasklist,
                 channel: discord.abc.Messageable, guild: Optional[discord.Guild] = None, **kwargs):
        kwargs.setdefault('timeout', 600)
        super().__init__(**kwargs)

        self.bot = tasklist.bot
        self.tasklist = tasklist
        self.labelled = tasklist.labelled
        self.userid = tasklist.userid
        self.channel = channel
        self.guild = guild

        # List of lists of (label, task) pairs
        self._pages = []

        self.page_num = -1
        self._channelid = channel.id
        self.current_page = None

        self.mode: UIMode = UIMode.TOGGLE
        self._message: Optional[discord.Message] = None
        self._last_parentid: Optional[int] = None
        self._subtree_root: Optional[int] = None

        self.set_active()

    @property
    def this_page(self):
        return self._pages[self.page_num % len(self._pages)] if self._pages else []

    # ----- UI API -----
    @classmethod
    def fetch(cls, tasklist, channel, *args, **kwargs):
        userid = tasklist.userid
        channelid = channel.id
        if channelid not in cls._live_[userid]:
            self = cls(tasklist, channel, *args, **kwargs)
            cls._live_[userid][channelid] = self
        return cls._live_[userid][channelid]

    async def run(self, interaction: discord.Interaction):
        await self.refresh()
        await self.redraw(interaction)

    async def summon(self, force=False):
        """
        Delete, refresh, and redisplay the tasklist widget as a non-ephemeral message in the current channel.

        May raise `discord.HTTPException` (from `redraw`) if something goes wrong with the send.
        """
        await self.refresh()

        resend = force or not await self._check_recent()
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

    async def page_cmd(self, interaction: discord.Interaction, value: str):
        return await Pager.page_cmd(self, interaction, value)

    async def page_acmpl(self, interaction: discord.Interaction, partial: str):
        return await Pager.page_acmpl(self, interaction, partial)

    # ----- Utilities / Workers ------
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
                height += message.content.count('\n')
            return False
        return False

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

    def _format_options(self, task_block, make_default: Optional[int] = None) -> list[SelectOption]:
        options = []
        for lbl, task in task_block:
            value = str(task.taskid)
            lblstr = '.'.join(map(str, lbl)) + '.' * (len(lbl) == 1)
            name = f"{lblstr} {task.content[:100 - len(lblstr) - 1]}"
            emoji = unchecked_emoji if task.completed_at is None else checked_emoji
            options.append(SelectOption(label=name, value=value, emoji=emoji, default=(task.taskid == make_default)))
        return options

    def _format_parent(self, parentid) -> str:
        parentstr = ''
        if parentid is not None:
            task = self.tasklist.tasklist.get(parentid, None)
            if task:
                parent_label = self.tasklist.format_label(self.tasklist.labelid(parentid)).strip('.')
                parentstr = f"{parent_label}: {task.content}"
        return parentstr

    def _parse_parent(self, provided: str) -> Optional[int]:
        """
        Parse a provided parent field.

        May raise UserInputError if parsing fails.
        """
        t = self.bot.translator.t
        provided = provided.strip()

        if provided.split(':', maxsplit=1)[0].replace('.', '').strip().isdigit():
            # Assume task label
            label, _, _ = provided.partition(':')
            label = label.strip()
            pid = self.tasklist.parse_label(label)
            if pid is None:
                raise UserInputError(
                    t(_p(
                        'ui:tasklist_single_editor|field:parent|error:parse_id',
                        "Could not find the given parent task number `{input}` in your tasklist."
                    )).format(input=label)
                )
        elif provided:
            # Search for matching tasks
            matching = [
                task.taskid
                for task in self.tasklist.tasklist.values()
                if provided.lower() in task.content.lower()
            ]
            if len(matching) > 1:
                raise UserInputError(
                    t(_p(
                        'ui:tasklist_single_editor|field:parent|error:multiple_matching',
                        "Multiple tasks matching given parent task `{input}`. Please use a task number instead!"
                    )).format(input=provided)
                )
            elif not matching:
                raise UserInputError(
                    t(_p(
                        'ui:tasklist_single_editor|field:parent|error:no_matching',
                        "No tasks matching given parent task `{input}`."
                    )).format(input=provided)
                )
            pid = matching[0]
        else:
            pid = None

        return pid

    # ----- Components -----
    async def _toggle_menu(self, interaction: discord.Interaction, selected: Select, subtree: bool):
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

        # If the selected tasks share a parent, and we are not in the subtree menu, change the subtree root
        if taskids and not subtree:
            labelled = self.labelled
            mapper = {t.taskid: label for label, t in labelled.items()}
            shared_root = None
            for task in tasks:
                pid = task.parentid
                plabel = mapper[pid] if pid else ()
                if shared_root:
                    shared_root = tuple(i for i, j in zip(shared_root, plabel) if i == j)
                else:
                    shared_root = plabel
                if not shared_root:
                    break
            if shared_root:
                self._subtree_root = labelled[shared_root].taskid

        self.bot.dispatch('tasklist_update', userid=self.userid, channel=self.channel, summon=False)

    async def _delete_menu(self, interaction: discord.Interaction, selected: Select, subtree: bool):
        await interaction.response.defer()
        taskids = list(map(int, selected.values))
        if taskids:
            await self.tasklist.update_tasks(
                *taskids,
                cascade=True,
                deleted_at=utc_now()
            )
            self.bot.dispatch('tasklist_update', userid=self.userid, channel=self.channel, summon=False)

    async def _edit_menu(self, interaction: discord.Interaction, selected: Select, subtree: bool):
        if not selected.values:
            await interaction.response.defer()
        else:
            t = self.bot.translator.t

            taskid = int(selected.values[0])
            task = self.tasklist.tasklist[taskid]

            editor = SingleEditor(
                title=t(_p('ui:tasklist|menu:edit|modal:title', "Edit task"))
            )
            editor.parent.default = self._format_parent(task.parentid)
            editor.task.default = task.content

            @editor.submit_callback()
            async def create_task(interaction):
                new_task = editor.task.value
                new_parentid = self._parse_parent(editor.parent.value)
                await interaction.response.defer()
                if task.content != new_task or task.parentid != new_parentid:
                    await task.update(content=new_task, parentid=new_parentid)
                    self._last_parentid = new_parentid
                    if not subtree:
                        self._subtree_root = new_parentid
                    self.bot.dispatch('tasklist_update', userid=self.userid, channel=self.channel, summon=False)

            await interaction.response.send_modal(editor)

    @select(placeholder="MAIN_MENU_PLACEHOLDER")
    async def main_menu(self, interaction: discord.Interaction, selected: Select):
        if self.mode is UIMode.TOGGLE:
            await self._toggle_menu(interaction, selected, False)
        elif self.mode is UIMode.DELETE:
            await self._delete_menu(interaction, selected, False)
        elif self.mode is UIMode.EDIT:
            await self._edit_menu(interaction, selected, False)

    async def main_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.main_menu
        menu.placeholder = t(self.mode.main_placeholder)

        block = self.this_page
        options = self._format_options(block)

        menu.options = options
        menu.min_values = 0
        menu.max_values = len(options) if self.mode is not UIMode.EDIT else 1

    @select(placeholder="SUB_MENU_PLACEHOLDER")
    async def sub_menu(self, interaction: discord.Interaction, selected: Select):
        if self.mode is UIMode.TOGGLE:
            await self._toggle_menu(interaction, selected, True)
        elif self.mode is UIMode.DELETE:
            await self._delete_menu(interaction, selected, True)
        elif self.mode is UIMode.EDIT:
            await self._edit_menu(interaction, selected, True)

    async def sub_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.sub_menu

        options = []
        if self._subtree_root:
            labelled = self.labelled
            mapper = {t.taskid: label for label, t in labelled.items()}
            rootid = self._subtree_root
            rootlabel = mapper.get(rootid, ())
            if rootlabel:
                menu.placeholder = t(self.mode.sub_placeholder).format(
                    label=self.tasklist.format_label(rootlabel).strip('.'),
                )
                children = {
                    label: taskid
                    for label, taskid in labelled.items()
                    if all(i == j for i, j in zip(label, rootlabel))
                }
                this_page = self.this_page
                if len(children) <= 25:
                    # Show all the children even if they don't display on the page
                    block = list(children.items())
                else:
                    # Only show the children which display
                    page_children = [
                        (label, tid) for label, tid in this_page if label in children and tid != rootid
                    ][:24]
                    if page_children:
                        block = [(rootlabel, rootid), *page_children]
                    else:
                        block = []
                # Special case if the subtree is exactly the same as the page
                if not (len(block) == len(this_page) and all(i[0] == j[0] for i, j in zip(block, this_page))):
                    options = self._format_options(block)

        menu.options = options
        menu.min_values = 0
        menu.max_values = len(options) if self.mode is not UIMode.EDIT else 1

    @button(label='NEW_BUTTON_PLACEHOLDER', style=ButtonStyle.green, emoji=conf.emojis.task_new)
    async def new_button(self, press: discord.Interaction, pressed: Button):
        t = self.bot.translator.t
        editor = SingleEditor(
            title=t(_p('ui:tasklist_single_editor|title', "Add task"))
        )
        editor.parent.default = self._format_parent(self._last_parentid)

        @editor.submit_callback()
        async def create_task(interaction):
            new_task = editor.task.value
            parent = editor.parent.value
            pid = self._parse_parent(parent)
            self._last_parentid = pid
            self._subtree_root = pid
            await interaction.response.defer()
            await self.tasklist.create_task(new_task, parentid=pid)
            self.bot.dispatch('tasklist_update', userid=self.userid, channel=self.channel, summon=False)

        await press.response.send_modal(editor)

    async def new_button_refresh(self):
        self.new_button.label = ""

    @button(label="EDIT_MODE_PLACEHOLDER", style=ButtonStyle.blurple)
    async def edit_mode_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        self.mode = UIMode.EDIT
        await self.redraw()

    async def edit_mode_button_refresh(self):
        t = self.bot.translator.t
        button = self.edit_mode_button

        button.style = ButtonStyle.blurple if (self.mode is UIMode.EDIT) else ButtonStyle.grey
        button.label = t(_p(
            'ui:tasklist|button:edit_mode|label',
            "Edit"
        ))

    @button(label="DELETE_MODE_PLACEHOLDER", style=ButtonStyle.blurple)
    async def delete_mode_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        self.mode = UIMode.DELETE
        await self.redraw()

    async def delete_mode_button_refresh(self):
        t = self.bot.translator.t
        button = self.delete_mode_button

        button.style = ButtonStyle.blurple if (self.mode is UIMode.DELETE) else ButtonStyle.grey
        button.label = t(_p(
            'ui:tasklist|button:delete_mode|label',
            "Delete"
        ))

    @button(label="TOGGLE_MODE_PLACEHOLDER", style=ButtonStyle.blurple)
    async def toggle_mode_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        self.mode = UIMode.TOGGLE
        await self.redraw()

    async def toggle_mode_button_refresh(self):
        t = self.bot.translator.t
        button = self.toggle_mode_button

        button.style = ButtonStyle.blurple if (self.mode is UIMode.TOGGLE) else ButtonStyle.grey
        button.label = t(_p(
            'ui:tasklist|button:toggle_mode|label',
            "Toggle"
        ))

    @button(label="EDIT_BULK_PLACEHOLDER", style=ButtonStyle.blurple)
    async def edit_bulk_button(self, press: discord.Interaction, pressed: Button):
        editor = BulkEditor(self.tasklist)

        @editor.add_callback
        async def editor_callback(interaction: discord.Interaction):
            self.bot.dispatch('tasklist_update', userid=self.userid, channel=self.channel, summon=False)

        if sum(len(line) for line in editor.lines.values()) + len(editor.lines) >= 4000:
            await press.response.send_message(
                embed=discord.Embed(
                    colour=discord.Colour.brand_red(),
                    description=self.bot.translator.t(_p(
                        'ui:tasklist|button:edit_bulk|error:too_long',
                        "Your tasklist is too long to be edited in a Discord text input! "
                        "Use the save button and {cmds[tasks upload]} instead."
                    )).format(cmds=self.bot.core.mention_cache)
                ),
                ephemeral=True
            )
        else:
            await press.response.send_modal(editor)

    async def edit_bulk_button_refresh(self):
        t = self.bot.translator.t
        button = self.edit_bulk_button
        button.label = t(_p(
            'ui:tasklist|button:edit_bulk|label',
            "Bulk Edit"
        ))

    @button(label='CLEAR_PLACEHOLDER', style=ButtonStyle.red)
    async def clear_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        await self.tasklist.update_tasklist(
            deleted_at=utc_now(),
        )
        self.bot.dispatch('tasklist_update', userid=self.userid, channel=self.channel, summon=False)

    async def clear_button_refresh(self):
        self.clear_button.label = self.bot.translator.t(_p(
            'ui:tasklist|button:clear|label', "Clear Tasklist"
        ))
        self.clear_button.disabled = (len(self.labelled) == 0)

    @button(label="SAVE_PLACEHOLDER", style=ButtonStyle.grey, emoji=conf.emojis.task_save)
    async def save_button(self, press: discord.Interaction, pressed: Button):
        """
        Send the tasklist to the user as a markdown file.
        """
        t = self.bot.translator.t
        await press.response.defer(thinking=True, ephemeral=True)

        # Build the tasklist file
        contents = '\n'.join(self.tasklist.flatten().values())
        with StringIO(contents) as fp:
            fp.seek(0)
            file = discord.File(fp, filename='tasklist.md')
            contents = t(_p(
                'ui:tasklist|button:save|dm:contents',
                "Your tasklist as of {now} is attached. Click here to jump back: {jump}"
            )).format(
                now=discord.utils.format_dt(utc_now()),
                jump=press.message.jump_url
            )
            try:
                await press.user.send(contents, file=file, silent=True)
            except discord.HTTPClient:
                fp.seek(0)
                file = discord.File(fp, filename='tasklist.md')
                await press.followup.send(
                    t(_p(
                        'ui:tasklist|button:save|error:dms',
                        "Could not DM you! Do you have me blocked? Tasklist attached below."
                    )),
                    file=file
                )
            else:
                fp.seek(0)
                file = discord.File(fp, filename='tasklist.md')
                await press.followup.send(file=file)

    async def save_button_refresh(self):
        self.save_button.disabled = (len(self.labelled) == 0)
        self.save_button.label = ''

    @button(label="REFRESH_PLACEHOLDER", style=ButtonStyle.grey, emoji=conf.emojis.refresh, custom_id='open_tasklist')
    async def refresh_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        await self.refresh()
        await self.redraw()

    async def refresh_button_refresh(self):
        self.refresh_button.label = ''

    @button(label="QUIT_PLACEHOLDER", style=ButtonStyle.grey, emoji=conf.emojis.cancel)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer()
        if self._message is not None:
            try:
                await self._message.delete()
            except discord.HTTPException:
                pass
        await self.close()

    async def quit_button_refresh(self):
        self.quit_button.label = ''

    # ----- UI Flow -----
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
        self._live_[self.userid].pop(self.channel.id, None)

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
            page = self.this_page
            block = self._format_page(page)
            embed.description = "{task_block}".format(task_block=block)
        else:
            embed.description = t(_p(
                'ui:tasklist|embed|description',
                "**You have no tasks on your tasklist!**\n"
                "Add a task with {cmds[tasks new]}, or by pressing the {new_button} button below."
            )).format(
                cmds=self.bot.core.mention_cache,
                new_button=conf.emojis.task_new
            )

        page_args = MessageArgs(embed=embed)
        return page_args

    def refresh_pages(self):
        labelled = list(self.labelled.items())
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

    async def refresh(self):
        # Refresh data
        await self.tasklist.refresh()
        self.labelled = self.tasklist.labelled
        self.refresh_pages()

    async def refresh_components(self):
        if not self.labelled:
            self.mode = UIMode.TOGGLE

        await asyncio.gather(
            self.main_menu_refresh(),
            self.sub_menu_refresh(),
            self.new_button_refresh(),
            self.edit_mode_button_refresh(),
            self.delete_mode_button_refresh(),
            self.toggle_mode_button_refresh(),
            self.edit_bulk_button_refresh(),
            self.clear_button_refresh(),
            self.save_button_refresh(),
            self.refresh_button_refresh(),
            self.quit_button_refresh(),
        )

        action_row = [
            self.new_button, self.toggle_mode_button, self.edit_mode_button, self.delete_mode_button,
        ]
        if self.mode is UIMode.EDIT:
            action_row.append(self.edit_bulk_button)
        elif self.mode is UIMode.DELETE:
            action_row.append(self.clear_button)

        main_row = (self.main_menu,) if self.main_menu.options else ()
        sub_row = (self.sub_menu,) if self.sub_menu.options else ()

        if len(self._pages) > 1:
            # Multi paged layout
            self._layout = (
                action_row,
                main_row,
                sub_row,
                (self.prev_page_button, self.save_button,
                 self.refresh_button, self.quit_button, self.next_page_button)

            )
        elif len(self.tasklist.tasklist) > 0:
            # Single page, but still at least one task
            self._layout = (
                action_row,
                main_row,
                sub_row,
                (self.save_button, self.refresh_button, self.quit_button)
            )
        else:
            # No tasks
            self._layout = (
                (self.new_button, self.edit_bulk_button, self.refresh_button, self.quit_button),
            )

    async def redraw(self, interaction: Optional[discord.Interaction] = None):
        self.current_page = await self.get_page(self.page_num)
        await self.refresh_components()

        # Resend
        if interaction is not None:
            if self._message:
                try:
                    await self._message.delete()
                except discord.HTTPException:
                    pass
            self._message = await interaction.followup.send(**self.current_page.send_args, view=self)
        elif self._message:
            await self._message.edit(**self.current_page.edit_args, view=self)
        else:
            self._message = await self.channel.send(**self.current_page.send_args, view=self)

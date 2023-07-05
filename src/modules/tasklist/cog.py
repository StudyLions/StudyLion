from typing import Optional
from collections import defaultdict
import datetime as dt

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.app_commands.transformers import AppCommandOptionType as cmdopt

from meta import LionBot, LionCog, LionContext
from meta.errors import UserInputError
from utils.lib import utc_now, error_embed
from utils.ui import ChoicedEnum, Transformed, AButton

from data import Condition, NULL
from wards import low_management_ward

from . import babel, logger
from .data import TasklistData
from .tasklist import Tasklist
from .ui import TasklistUI, SingleEditor, BulkEditor, TasklistCaller
from .settings import TasklistSettings, TasklistConfigUI

_p, _np = babel._p, babel._np


MAX_LENGTH = 100


class BeforeSelection(ChoicedEnum):
    """
    Set of choices for the before arguments of `remove`.
    """
    HOUR = _p('argtype:Before|opt:HOUR', "The last hour")
    HALFDAY = _p('argtype:Before|opt:HALFDAY', "The last 12 hours")
    DAY = _p('argtype:Before|opt:DAY', "The last 24 hours")
    TODAY = _p('argtype:Before|opt:TODAY', "Today")
    YESTERDAY = _p('argtype:Before|opt:YESTERDAY', "Yesterday")
    MONDAY = _p('argtype:Before|opt:Monday', "This Monday")
    THISMONTH = _p('argtype:Before|opt:THISMONTH', "This Month")

    @property
    def choice_name(self):
        return self.value

    @property
    def choice_value(self):
        return self.name

    def needs_timezone(self):
        return self in (
            BeforeSelection.TODAY,
            BeforeSelection.YESTERDAY,
            BeforeSelection.MONDAY,
            BeforeSelection.THISMONTH
        )

    def cutoff(self, timezone):
        """
        Cut-off datetime for this period, in the given timezone.
        """
        now = dt.datetime.now(tz=timezone)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self is BeforeSelection.HOUR:
            return now - dt.timedelta(hours=1)
        elif self is BeforeSelection.HALFDAY:
            return now - dt.timedelta(hours=12)
        elif self is BeforeSelection.DAY:
            return now - dt.timedelta(hours=24)
        elif self is BeforeSelection.TODAY:
            time = day_start
        elif self is BeforeSelection.YESTERDAY:
            time = day_start - dt.timedelta(days=1)
        elif self is BeforeSelection.MONDAY:
            time = day_start - dt.timedelta(days=now.weekday)
        elif self is BeforeSelection.THISMONTH:
            time = day_start.replace(day=0)
        return time


class TasklistCog(LionCog):
    """
    Command cog for the tasklist module.

    All tasklist modification commands will summon the
    member's TasklistUI, if currently in a tasklist-enabled channel,
    or in a rented room channel (TODO).

    Commands
    --------
    /tasklist open
        Summon the TasklistUI panel for the current member.
    /tasklist new <task> [parent:str]
        Create a new task and add it to the tasklist.
    /tasklist edit [taskid:int] [content:str] [parent:str]
        With no arguments, opens up the task editor modal.
        With only `taskid` given, opens up a single modal editor for that task.
        With both `taskid` and `content` given, updates the given task content.
        If only `content` is given, errors.
    /tasklist clear
        Clears the tasklist, after confirmation.
    /tasklist remove [taskids:ranges] [created_before:dur] [updated_before:dur] [completed:bool] [cascade:bool]
        Remove tasks described by a sequence of conditions.
        Duration arguments use a time selector menu rather than a Duration type.
        With no arguments, acts like `clear`.
    /tasklist tick <taskids:ranges> [cascade:bool]
        Tick a selection of taskids, accepting ranges.
    /tasklist untick <taskids:ranges> [cascade:bool]
        Untick a selection of taskids, accepting ranges.

    Interface
    ---------
    This cog does not expose a public interface.

    Attributes
    ----------
    bot: LionBot
        The client which owns this Cog.
    data: TasklistData
        The tasklist data registry.
    babel: LocalBabel
        The LocalBabel instance for this module.
    """
    depends = {'CoreCog', 'ConfigCog', 'Economy'}

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(TasklistData())
        self.babel = babel
        self.settings = TasklistSettings()

        self.live_tasklists = TasklistUI._live_

    async def cog_load(self):
        await self.data.init()
        self.bot.core.guild_config.register_model_setting(self.settings.task_reward)
        self.bot.core.guild_config.register_model_setting(self.settings.task_reward_limit)
        self.bot.add_view(TasklistCaller(self.bot))

        configcog = self.bot.get_cog('ConfigCog')
        self.crossload_group(self.configure_group, configcog.configure_group)

    @LionCog.listener('on_tasks_completed')
    async def reward_tasks_completed(self, member: discord.Member, *taskids: int):
        conn = await self.bot.db.get_connection()
        async with conn.transaction():
            tasklist = await Tasklist.fetch(self.bot, self.data, member.id)
            tasks = await tasklist.fetch_tasks(*taskids)
            unrewarded = [task for task in tasks if not task.rewarded]
            if unrewarded:
                reward = (await self.settings.task_reward.get(member.guild.id)).value
                limit = (await self.settings.task_reward_limit.get(member.guild.id)).value

                ecog = self.bot.get_cog('Economy')
                recent = await ecog.data.TaskTransaction.count_recent_for(member.id, member.guild.id) or 0
                max_to_reward = limit - recent
                if max_to_reward > 0:
                    to_reward = unrewarded[:max_to_reward]

                    count = len(to_reward)
                    amount = count * reward
                    await ecog.data.TaskTransaction.reward_completed(member.id, member.guild.id, count, amount)
                    await tasklist.update_tasks(*(task.taskid for task in to_reward), rewarded=True)
                    logger.debug(
                        f"Rewarded <uid: {member.id}> in <gid: {member.guild.id}> "
                        f"'{amount}' coins for completing '{count}' tasks."
                    )

    async def is_tasklist_channel(self, channel) -> bool:
        if not channel.guild:
            return True
        channels = (await self.settings.tasklist_channels.get(channel.guild.id)).value
        return (channel in channels) or (channel.category in channels)

    async def call_tasklist(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        channel = interaction.channel
        guild = channel.guild
        userid = interaction.user.id

        tasklist = await Tasklist.fetch(self.bot, self.data, userid)

        if await self.is_tasklist_channel(channel):
            tasklistui = TasklistUI.fetch(tasklist, channel, guild, timeout=None)
            await tasklistui.summon(force=True)
            await interaction.delete_original_response()
        else:
            # Note that this will also close any existing listening tasklists in this channel (for this user)
            tasklistui = TasklistUI.fetch(tasklist, channel, guild, timeout=600)
            await tasklistui.run(interaction)

    @LionCog.listener('on_tasklist_update')
    async def update_listening_tasklists(self, userid, channel=None, summon=True):
        """
        Propagate a tasklist update to all persistent tasklist UIs for this user.

        If channel is given, also summons the UI if the channel is a tasklist channel.
        """
        # Do the given channel first, and summon if requested
        if channel and (tui := TasklistUI._live_[userid].get(channel.id, None)) is not None:
            try:
                if summon and await self.is_tasklist_channel(channel):
                    await tui.summon()
                else:
                    await tui.refresh()
                    await tui.redraw()
            except discord.HTTPException:
                await tui.close()

        # Now do the rest of the listening channels
        listening = TasklistUI._live_[userid]
        for cid, ui in listening.items():
            if channel and channel.id == cid:
                continue
            try:
                await ui.refresh()
                await ui.redraw()
            except discord.HTTPException:
                await tui.close()

    @cmds.hybrid_command(
        name=_p('cmd:tasklist', "tasklist"),
        description=_p(
            'cmd:tasklist|desc',
            "Open your tasklist."
        )
    )
    async def tasklist_cmd(self, ctx: LionContext):
        if not ctx.interaction:
            return
        await self.call_tasklist(ctx.interaction)

    @cmds.hybrid_group(
        name=_p('group:tasks', "tasks"),
        description=_p('group:tasks|desc', "Base command group for tasklist commands.")
    )
    async def tasklist_group(self, ctx: LionContext):
        raise NotImplementedError

    async def _task_acmpl(self, userid: int, partial: str, multi=False) -> list[appcmds.Choice]:
        """
        Generate a list of task Choices matching a given partial string.

        Supports single and multiple task matching.
        """
        t = self.bot.translator.t

        # Should usually be cached, so this won't trigger repetitive db access
        tasklist = await Tasklist.fetch(self.bot, self.data, userid)

        # Special case for an empty tasklist
        if not tasklist.tasklist:
            return [
                appcmds.Choice(
                    name=t(_p(
                        'argtype:taskid|error:no_tasks',
                        "Tasklist empty! No matching tasks."
                    )),
                    value=partial
                )
            ]

        labels = []
        idmap = {}
        for label, task in tasklist.labelled.items():
            labelstring = '.'.join(map(str, label)) + '.' * (len(label) == 1)
            taskstring = f"{labelstring} {task.content}"
            idmap[task.taskid] = labelstring
            labels.append((labelstring, taskstring))

        # Assume user is typing a label
        matching = [(label, task) for label, task in labels if label.startswith(partial)]

        # If partial does match any labels, search for partial in task content
        if not matching:
            matching = [(label, task) for label, task in labels if partial.lower() in task.lower()]

        if matching:
            # If matches were found, assume user wants one of the matches
            options = [
                appcmds.Choice(name=task_string, value=label)
                for label, task_string in matching
            ]
        elif multi and (',' in partial or '-' in partial):
            # Try parsing input as a multi-list
            try:
                parsed = tasklist.parse_labels(partial)
                multi_name = ', '.join(idmap[tid] for tid in parsed)
                if len(multi_name) > 100:
                    multi_name = multi_name[:96]
                    multi_name, _ = multi_name.rsplit(',', maxsplit=1)
                    multi_name = multi_name + ', ...'
            except UserInputError as e:
                parsed = []
                error = t(_p(
                    'argtype:taskid|error:parse_multi',
                    "(Warning: {error})"
                )).format(
                    error=e.msg
                )
                remaining = 100 - len(error)
                multi_name = f"{partial[:remaining-1]} {error}"

            multi_option = appcmds.Choice(
                name=multi_name,
                value=partial
            )
            options = [multi_option]
            # Regardless of parse status, show matches with last split, if they exist.
            if ',' in partial:
                _, last_split = partial.rsplit(',', maxsplit=1)
            else:
                last_split = partial
            if '-' in last_split:
                _, last_split = last_split.rsplit('-', maxsplit=1)
                last_split = last_split.strip(' ')
            else:
                last_split = last_split.strip(' ')
            matching = [(label, task) for label, task in labels if label.startswith(last_split)]
            if not matching:
                matching = [(label, task) for label, task in labels if last_split.lower() in task.lower()]
            options.extend(
                appcmds.Choice(name=task_string, value=label)
                for label, task_string in matching
            )
        else:
            options = [
                appcmds.Choice(
                    name=t(_p(
                        'argtype:taskid|error:no_matching',
                        "No tasks matching '{partial}'!",
                    )).format(partial=partial[:100]),
                    value=partial
                )
            ]
        return options[:25]

    async def task_acmpl(self, interaction: discord.Interaction, partial: str) -> list[appcmds.Choice]:
        """
        Shared autocomplete for single task parameters.
        """
        return await self._task_acmpl(interaction.user.id, partial, multi=False)

    async def tasks_acmpl(self, interaction: discord.Interaction, partial: str) -> list[appcmds.Choice]:
        """
        Shared autocomplete for multiple task parameters.
        """
        return await self._task_acmpl(interaction.user.id, partial, multi=True)

    @tasklist_group.command(
        name=_p('cmd:tasks_new', "new"),
        description=_p(
            'cmd:tasks_new|desc',
            "Add a new task to your tasklist."
        )
    )
    @appcmds.rename(
        content=_p('cmd:tasks_new|param:content', "task"),
        parent=_p('cmd:tasks_new|param:parent', 'parent')
    )
    @appcmds.describe(
        content=_p('cmd:tasks_new|param:content|desc', "Content of your new task."),
        parent=_p('cmd:tasks_new|param:parent', 'Parent of this task.')
    )
    async def tasklist_new_cmd(self, ctx: LionContext,
                               content: appcmds.Range[str, 1, MAX_LENGTH],
                               parent: Optional[str] = None):
        t = self.bot.translator.t
        if not ctx.interaction:
            return

        tasklist = await Tasklist.fetch(self.bot, self.data, ctx.author.id)
        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        # Fetch parent task if required
        pid = tasklist.parse_label(parent) if parent else None
        if parent and pid is None:
            # Could not parse
            await ctx.interaction.edit_original_response(
                embed=error_embed(
                    t(_p(
                        'cmd:tasks_new|error:parse_parent',
                        "Could not find parent task number `{input}` in your tasklist."
                    )).format(input=parent)
                ),
            )
            return

        # Create task
        task = await tasklist.create_task(content, parentid=pid)

        # Ack creation
        label = tasklist.labelid(task.taskid)
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            description=t(_p(
                'cmd:tasks_new|resp:success',
                "{tick} Created task `{label}`."
            )).format(tick=self.bot.config.emojis.tick, label=tasklist.format_label(label))
        )
        await ctx.interaction.edit_original_response(
            embed=embed,
            view=None if ctx.channel.id in TasklistUI._live_[ctx.author.id] else TasklistCaller(self.bot)
        )
        self.bot.dispatch('tasklist_update', userid=ctx.author.id, channel=ctx.channel)

    tasklist_new_cmd.autocomplete('parent')(task_acmpl)

    @tasklist_group.command(
        name=_p('cmd:tasks_edit', "edit"),
        description=_p(
            'cmd:tasks_edit|desc',
            "Edit a task in your tasklist."
        )
    )
    @appcmds.rename(
        taskstr=_p('cmd:tasks_edit|param:taskstr', "task"),
        new_content=_p('cmd:tasks_edit|param:new_content', "new_task"),
        new_parent=_p('cmd:tasks_edit|param:new_parent', "new_parent"),
    )
    @appcmds.describe(
        taskstr=_p('cmd:tasks_edit|param:taskstr|desc', "Which task do you want to update?"),
        new_content=_p('cmd:tasks_edit|param:new_content|desc', "What do you want to change the task to?"),
        new_parent=_p('cmd:tasks_edit|param:new_parent|desc', "Which task do you want to be the new parent?"),
    )
    async def tasklist_edit_cmd(self, ctx: LionContext,
                                taskstr: str,
                                new_content: Optional[appcmds.Range[str, 1, MAX_LENGTH]] = None,
                                new_parent: Optional[str] = None):
        t = self.bot.translator.t
        if not ctx.interaction:
            return
        tasklist = await Tasklist.fetch(self.bot, self.data, ctx.author.id)

        # Fetch task to edit
        tid = tasklist.parse_label(taskstr) if taskstr else None
        if tid is None:
            # Could not parse
            await ctx.interaction.response.send_message(
                embed=error_embed(
                    t(_p(
                        'cmd:tasks_edit|error:parse_taskstr',
                        "Could not find target task number `{input}` in your tasklist."
                    )).format(input=taskstr)
                ),
                ephemeral=True,
            )
            return

        async def handle_update(interaction, new_content, new_parent):
            # Parse new parent if given
            pid = tasklist.parse_label(new_parent) if new_parent else None
            if new_parent and not pid:
                # Could not parse
                await interaction.response.send_message(
                    embed=error_embed(
                        t(_p(
                            'cmd:tasks_edit|error:parse_parent',
                            "Could not find new parent task number `{input}` in your tasklist."
                        )).format(input=new_parent)
                    ),
                    ephemeral=True
                )
                return

            args = {}
            if new_content:
                args['content'] = new_content
            if new_parent:
                args['parentid'] = pid
            if args:
                await tasklist.update_tasks(tid, **args)

            embed = discord.Embed(
                colour=discord.Color.brand_green(),
                description=t(_p(
                    'cmd:tasks_edit|resp:success|desc',
                    "{tick} Task `{label}` updated."
                )).format(tick=self.bot.config.emojis.tick, label=tasklist.format_label(tasklist.labelid(tid))),
            )
            await ctx.interaction.edit_original_response(
                embed=embed,
                view=None if ctx.channel.id in TasklistUI._live_[ctx.author.id] else TasklistCaller(self.bot)
            )
            self.bot.dispatch('tasklist_update', userid=ctx.author.id, channel=ctx.channel)

        if new_content or new_parent:
            # Manual edit route
            await handle_update(ctx.interaction, new_content, new_parent)
        else:
            # Modal edit route
            task = tasklist.tasklist[tid]
            parent_label = tasklist.labelid(task.parentid) if task.parentid else None

            editor = SingleEditor(
                title=t(_p('ui:tasklist_single_editor|title', "Edit Task"))
            )
            editor.task.default = task.content
            editor.parent.default = tasklist.format_label(parent_label) if parent_label else None

            @editor.submit_callback()
            async def update_task(interaction: discord.Interaction):
                await handle_update(interaction, editor.task.value, editor.parent.value)

            await ctx.interaction.response.send_modal(editor)

    tasklist_edit_cmd.autocomplete('taskstr')(task_acmpl)
    tasklist_edit_cmd.autocomplete('new_parent')(task_acmpl)

    @tasklist_group.command(
        name=_p('cmd:tasks_clear', "clear"),
        description=_p('cmd:tasks_clear|desc', "Clear your tasklist.")
    )
    async def tasklist_clear_cmd(self, ctx: LionContext):
        t = ctx.bot.translator.t

        tasklist = await Tasklist.fetch(self.bot, self.data, ctx.author.id)
        await tasklist.update_tasklist(deleted_at=utc_now())
        await ctx.reply(
            t(_p(
                'cmd:tasks_clear|resp:success',
                "Your tasklist has been cleared."
            )),
            view=None if ctx.channel.id in TasklistUI._live_[ctx.author.id] else TasklistCaller(self.bot),
            ephemeral=True
        )
        self.bot.dispatch('tasklist_update', userid=ctx.author.id, channel=ctx.channel)

    @tasklist_group.command(
        name=_p('cmd:tasks_remove', "remove"),
        description=_p(
            'cmd:tasks_remove|desc',
            "Remove tasks matching all the provided conditions. (E.g. remove tasks completed before today)."
        )
    )
    @appcmds.rename(
        taskidstr=_p('cmd:tasks_remove|param:taskidstr', "tasks"),
        created_before=_p('cmd:tasks_remove|param:created_before', "created_before"),
        updated_before=_p('cmd:tasks_remove|param:updated_before', "updated_before"),
        completed=_p('cmd:tasks_remove|param:completed', "completed"),
        cascade=_p('cmd:tasks_remove|param:cascade', "cascade")
    )
    @appcmds.describe(
        taskidstr=_p(
            'cmd:tasks_remove|param:taskidstr|desc',
            "List of task numbers or ranges to remove (e.g. 1, 2, 5-7, 8.1-3, 9-)."
        ),
        created_before=_p(
            'cmd:tasks_remove|param:created_before|desc',
            "Only delete tasks created before the selected time."
        ),
        updated_before=_p(
            'cmd:tasks_remove|param:updated_before|desc',
            "Only deleted tasks update (i.e. completed or edited) before the selected time."
        ),
        completed=_p(
            'cmd:tasks_remove|param:completed',
            "Only delete tasks which are (not) complete."
        ),
        cascade=_p(
            'cmd:tasks_remove|param:cascade',
            "Whether to recursively remove subtasks of removed tasks."
        )
    )
    async def tasklist_remove_cmd(self, ctx: LionContext,
                                  taskidstr: str,
                                  created_before: Optional[Transformed[BeforeSelection, cmdopt.string]] = None,
                                  updated_before: Optional[Transformed[BeforeSelection, cmdopt.string]] = None,
                                  completed: Optional[bool] = None,
                                  cascade: bool = True):
        t = self.bot.translator.t
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        tasklist = await Tasklist.fetch(self.bot, self.data, ctx.author.id)

        conditions = []
        if taskidstr:
            try:
                taskids = tasklist.parse_labels(taskidstr)
            except UserInputError as error:
                await ctx.interaction.edit_original_response(
                    embed=error_embed(error.msg)
                )
                return

            if not taskids:
                # Explicitly error if none of the ranges matched
                await ctx.interaction.edit_original_response(
                    embed=error_embed(
                        'cmd:tasks_remove_cmd|error:no_matching',
                        "No tasks on your tasklist match `{input}`"
                    ).format(input=taskidstr)
                )
                return

            conditions.append(self.data.Task.taskid == taskids)

        if created_before is not None or updated_before is not None:
            timezone = ctx.alion.timezone
            if created_before is not None:
                conditions.append(self.data.Task.created_at <= created_before.cutoff(timezone))
            if updated_before is not None:
                conditions.append(self.data.Task.last_updated_at <= updated_before.cutoff(timezone))

        if completed is True:
            conditions.append(self.data.Task.completed_at != NULL)
        elif completed is False:
            conditions.append(self.data.Task.completed_at == NULL)

        tasks = await self.data.Task.fetch_where(*conditions, userid=ctx.author.id)
        if not tasks:
            await ctx.interaction.edit_original_response(
                embed=error_embed(
                    'cmd:tasks_remove_cmd|error:no_matching',
                    "No tasks on your tasklist matching all the given conditions!"
                ).format(input=taskidstr)
            )
            return
        taskids = [task.taskid for task in tasks]
        label = tasklist.format_label(tasklist.labelid(taskids[0]))
        await tasklist.update_tasks(*taskids, cascade=cascade, deleted_at=utc_now())

        # Ack changes and summon tasklist
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            description=t(_np(
                'cmd:tasks_remove|resp:success',
                "{tick} Deleted task `{label}`",
                "{tick} Deleted `{count}` tasks from your tasklist.",
                len(taskids)
            )).format(
                tick=self.bot.config.emojis.tick,
                label=label,
                count=len(taskids)
            )
        )
        await ctx.interaction.edit_original_response(
            embed=embed,
            view=None if ctx.channel.id in TasklistUI._live_[ctx.author.id] else TasklistCaller(self.bot)
        )
        self.bot.dispatch('tasklist_update', userid=ctx.author.id, channel=ctx.channel)

    tasklist_remove_cmd.autocomplete('taskidstr')(tasks_acmpl)

    @tasklist_group.command(
        name=_p('cmd:tasks_tick', "tick"),
        description=_p('cmd:tasks_tick|desc', "Mark the given tasks as completed.")
    )
    @appcmds.rename(
        taskidstr=_p('cmd:tasks_tick|param:taskidstr', "tasks"),
        cascade=_p('cmd:tasks_tick|param:cascade', "cascade")
    )
    @appcmds.describe(
        taskidstr=_p(
            'cmd:tasks_tick|param:taskidstr|desc',
            "List of task numbers or ranges to remove (e.g. 1, 2, 5-7, 8.1-3, 9-)."
        ),
        cascade=_p(
            'cmd:tasks_tick|param:cascade|desc',
            "Whether to also mark all subtasks as complete."
        )
    )
    async def tasklist_tick_cmd(self, ctx: LionContext, taskidstr: str, cascade: bool = True):
        t = self.bot.translator.t
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        tasklist = await Tasklist.fetch(self.bot, self.data, ctx.author.id)

        try:
            taskids = tasklist.parse_labels(taskidstr)
        except UserInputError as error:
            await ctx.interaction.edit_original_response(
                embed=error_embed(error.msg)
            )
            return

        if not taskids:
            if not taskids:
                # Explicitly error if none of the ranges matched
                await ctx.interaction.edit_original_response(
                    embed=error_embed(
                        'cmd:tasks_remove_cmd|error:no_matching',
                        "No tasks on your tasklist match `{input}`"
                    ).format(input=taskidstr)
                )
                return

        tasks = [tasklist.tasklist[taskid] for taskid in taskids]
        tasks = [task for task in tasks if task.completed_at is None]
        taskids = [task.taskid for task in tasks]
        if taskids:
            await tasklist.update_tasks(*taskids, cascade=cascade, completed_at=utc_now())
            if ctx.guild:
                self.bot.dispatch('tasks_completed', ctx.author, *taskids)

        # Ack changes and summon tasklist
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            description=t(_np(
                'cmd:tasks_tick|resp:success',
                "{tick} Marked `{label}` as complete.",
                "{tick} Marked `{count}` tasks as complete.",
                len(taskids)
            )).format(
                tick=self.bot.config.emojis.tick,
                count=len(taskids),
                label=tasklist.format_label(tasklist.labelid(taskids[0])) if taskids else '-'
            )
        )
        await ctx.interaction.edit_original_response(
            embed=embed,
            view=None if ctx.channel.id in TasklistUI._live_[ctx.author.id] else TasklistCaller(self.bot)
        )
        self.bot.dispatch('tasklist_update', userid=ctx.author.id, channel=ctx.channel)

    tasklist_tick_cmd.autocomplete('taskidstr')(tasks_acmpl)

    @tasklist_group.command(
        name=_p('cmd:tasks_untick', "untick"),
        description=_p('cmd:tasks_untick|desc', "Mark the given tasks as incomplete.")
    )
    @appcmds.rename(
        taskidstr=_p('cmd:tasks_untick|param:taskidstr', "taskids"),
        cascade=_p('cmd:tasks_untick|param:cascade', "cascade")
    )
    @appcmds.describe(
        taskidstr=_p(
            'cmd:tasks_untick|param:taskidstr|desc',
            "List of task numbers or ranges to remove (e.g. 1, 2, 5-7, 8.1-3, 9-)."
        ),
        cascade=_p(
            'cmd:tasks_untick|param:cascade|desc',
            "Whether to also mark all subtasks as incomplete."
        )
    )
    async def tasklist_untick_cmd(self, ctx: LionContext, taskidstr: str, cascade: Optional[bool] = False):
        t = self.bot.translator.t
        if not ctx.interaction:
            return

        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        tasklist = await Tasklist.fetch(self.bot, self.data, ctx.author.id)

        try:
            taskids = tasklist.parse_labels(taskidstr)
        except UserInputError as error:
            await ctx.interaction.edit_original_response(
                embed=error_embed(error.msg)
            )
            return

        if not taskids:
            # Explicitly error if none of the ranges matched
            await ctx.interaction.edit_original_response(
                embed=error_embed(
                    'cmd:tasks_remove_cmd|error:no_matching',
                    "No tasks on your tasklist match `{input}`"
                ).format(input=taskidstr)
            )
            return

        tasks = [tasklist.tasklist[taskid] for taskid in taskids]
        tasks = [task for task in tasks if task.completed_at is not None]
        taskids = [task.taskid for task in tasks]
        if taskids:
            await tasklist.update_tasks(*taskids, cascade=cascade, completed_at=None)

        # Ack changes and summon tasklist
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            description=t(_np(
                'cmd:tasks_untick|resp:success',
                "{tick} Marked `{label}` as incomplete.",
                "{tick} Marked `{count}` tasks as incomplete.",
                len(taskids)
            )).format(
                tick=self.bot.config.emojis.tick,
                count=len(taskids),
                label=tasklist.format_label(tasklist.labelid(taskids[0])) if taskids else '-'
            )
        )
        await ctx.interaction.edit_original_response(
            embed=embed,
            view=None if ctx.channel.id in TasklistUI._live_[ctx.author.id] else TasklistCaller(self.bot)
        )
        self.bot.dispatch('tasklist_update', userid=ctx.author.id, channel=ctx.channel)

    tasklist_untick_cmd.autocomplete('taskidstr')(tasks_acmpl)

    # Setting Commands
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        ...

    @configure_group.command(
        name=_p('cmd:configure_tasklist', "tasklist"),
        description=_p('cmd:configure_tasklist|desc', "Tasklist configuration panel")
    )
    @appcmds.rename(
        reward=_p('cmd:configure_tasklist|param:reward', "reward"),
        reward_limit=_p('cmd:configure_tasklist|param:reward_limit', "reward_limit")
    )
    @appcmds.describe(
        reward=TasklistSettings.task_reward._desc,
        reward_limit=TasklistSettings.task_reward_limit._desc
    )
    @appcmds.default_permissions(manage_guild=True)
    @low_management_ward
    async def configure_tasklist_cmd(self, ctx: LionContext,
                                     reward: Optional[int] = None,
                                     reward_limit: Optional[int] = None):
        t = self.bot.translator.t
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        task_reward = await self.settings.task_reward.get(ctx.guild.id)
        task_reward_limit = await self.settings.task_reward_limit.get(ctx.guild.id)

        # TODO: Batch properly
        updated = False
        if reward is not None:
            task_reward.data = reward
            await task_reward.write()
            updated = True

        if reward_limit is not None:
            task_reward_limit.data = reward_limit
            await task_reward_limit.write()
            updated = True

        # Send update ack if required
        if updated:
            description = t(_p(
                'cmd:configure_tasklist|resp:success|desc',
                "Members will now be rewarded {coin}**{amount}** for "
                "each task they complete up to a maximum of `{limit}` tasks per 24h."
            )).format(
                coin=self.bot.config.emojis.coin,
                amount=task_reward.data,
                limit=task_reward_limit.data
            )
            await ctx.reply(
                embed=discord.Embed(
                    colour=discord.Colour.brand_green(),
                    description=description
                )
            )

        if ctx.channel.id not in TasklistConfigUI._listening or not ctx.interaction.response.is_done():
            # Launch setting group UI
            configui = TasklistConfigUI(self.bot, ctx.guild.id, ctx.channel.id)
            await configui.run(ctx.interaction)
            await configui.wait()

from typing import Optional
import datetime as dt

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.app_commands.transformers import AppCommandOptionType as cmdopt

from meta import LionBot, LionCog, LionContext
from meta.errors import UserInputError
from utils.lib import utc_now, error_embed
from utils.ui import ChoicedEnum, Transformed

from data import Condition, NULL
from wards import low_management_ward

from . import babel, logger
from .data import TasklistData
from .tasklist import Tasklist
from .ui import TasklistUI, SingleEditor, BulkEditor
from .settings import TasklistSettings, TasklistConfigUI

_p = babel._p


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

    async def cog_load(self):
        await self.data.init()
        self.bot.core.guild_config.register_model_setting(self.settings.task_reward)
        self.bot.core.guild_config.register_model_setting(self.settings.task_reward_limit)

        # TODO: Better method for getting single load
        # Or better, unloading crossloaded group
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
                max_to_reward = max(limit-recent, 0)
                to_reward = unrewarded[:max_to_reward]

                count = len(to_reward)
                amount = count * reward
                await ecog.data.TaskTransaction.reward_completed(member.id, member.guild.id, count, amount)
                await tasklist.update_tasks(*(task.taskid for task in to_reward), rewarded=True)
                logger.debug(
                    f"Rewarded <uid: {member.id}> in <gid: {member.guild.id}> "
                    f"'{amount}' coins for completing '{count}' tasks."
                )

    @cmds.hybrid_group(
        name=_p('group:tasklist', "tasklist")
    )
    async def tasklist_group(self, ctx: LionContext):
        raise NotImplementedError

    async def task_acmpl(self, interaction: discord.Interaction, partial: str) -> list[appcmds.Choice]:
        t = self.bot.translator.t

        # Should usually be cached, so this won't trigger repetitive db access
        tasklist = await Tasklist.fetch(self.bot, self.data, interaction.user.id)

        labels = []
        for label, task in tasklist.labelled.items():
            labelstring = '.'.join(map(str, label)) + '.' * (len(label) == 1)
            taskstring = f"{labelstring} {task.content}"
            labels.append((labelstring, taskstring))

        matching = [(label, task) for label, task in labels if label.startswith(partial)]

        if not matching:
            matching = [(label, task) for label, task in labels if partial.lower() in task.lower()]

        if not matching:
            options = [
                appcmds.Choice(
                    name=t(_p(
                        'argtype:taskid|error:no_matching',
                        "No tasks matching '{partial}'!",
                    )).format(partial=partial[:100]),
                    value=partial
                )
            ]
        else:
            options = [
                appcmds.Choice(name=task_string, value=label)
                for label, task_string in matching
            ]
        return options[:25]

    async def is_tasklist_channel(self, channel) -> bool:
        if not channel.guild:
            return True
        channels = (await self.settings.tasklist_channels.get(channel.guild.id)).value
        return (not channels) or (channel in channels) or (channel.category in channels)

    @tasklist_group.command(
        name=_p('cmd:tasklist_open', "open"),
        description=_p(
            'cmd:tasklist_open|desc',
            "Open your tasklist."
        )
    )
    async def tasklist_open_cmd(self, ctx: LionContext):
        # TODO: Further arguments for style, e.g. gui/block/text
        if await self.is_tasklist_channel(ctx.channel):
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)
            tasklist = await Tasklist.fetch(self.bot, self.data, ctx.author.id)
            tasklistui = await TasklistUI.fetch(tasklist, ctx.channel, ctx.guild)
            await tasklistui.summon()
            await ctx.interaction.delete_original_response()
        else:
            t = self.bot.translator.t
            channels = (await self.settings.tasklist_channels.get(ctx.guild.id)).value
            viewable = [
                channel for channel in channels
                if (channel.permissions_for(ctx.author).send_messages
                    or channel.permissions_for(ctx.author).send_messages_in_threads)
            ]
            embed = discord.Embed(
                title=t(_p('cmd:tasklist_open|error:tasklist_channel|title', "Sorry, I can't do that here")),
                colour=discord.Colour.brand_red()
            )
            if viewable:
                embed.description = t(_p(
                    'cmd:tasklist_open|error:tasklist_channel|desc',
                    "Please use direct messages or one of the following channels "
                    "or categories for managing your tasks:\n{channels}"
                )).format(channels='\n'.join(channel.mention for channel in viewable))
            else:
                embed.description = t(_p(
                    'cmd:tasklist_open|error:tasklist_channel|desc',
                    "There are no channels available here where you may open your tasklist!"
                ))
            await ctx.reply(embed=embed, ephemeral=True)

    @tasklist_group.command(
        name=_p('cmd:tasklist_new', "new"),
        description=_p(
            'cmd:tasklist_new|desc',
            "Add a new task to your tasklist."
        )
    )
    @appcmds.rename(
        content=_p('cmd:tasklist_new|param:content', "task"),
        parent=_p('cmd:tasklist_new|param:parent', 'parent')
    )
    @appcmds.describe(
        content=_p('cmd:tasklist_new|param:content|desc', "Content of your new task."),
        parent=_p('cmd:tasklist_new|param:parent', 'Parent of this task.')
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
                        'cmd:tasklist_new|error:parse_parent',
                        "Could not find task number `{input}` in your tasklist."
                    )).format(input=parent)
                ),
            )
            return

        # Create task
        await tasklist.create_task(content, parentid=pid)

        if await self.is_tasklist_channel(ctx.interaction.channel):
            # summon tasklist
            tasklistui = await TasklistUI.fetch(tasklist, ctx.channel, ctx.guild)
            await tasklistui.summon()
            await ctx.interaction.delete_original_response()
        else:
            # ack creation
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:tasklist_new|resp:success',
                    "{tick} Task created successfully."
                )).format(tick=self.bot.config.emojis.tick)
            )
            await ctx.interaction.edit_original_response(embed=embed)

    @tasklist_new_cmd.autocomplete('parent')
    async def tasklist_new_cmd_parent_acmpl(self, interaction: discord.Interaction, partial: str):
        return await self.task_acmpl(interaction, partial)

    @tasklist_group.command(
        name=_p('cmd:tasklist_edit', "edit"),
        description=_p(
            'cmd:tasklist_edit|desc',
            "Edit tasks in your tasklist."
        )
    )
    @appcmds.rename(
        taskstr=_p('cmd:tasklist_edit|param:taskstr', "task"),
        new_content=_p('cmd:tasklist_edit|param:new_content', "new_task"),
        new_parent=_p('cmd:tasklist_edit|param:new_parent', "new_parent"),
    )
    @appcmds.describe(
        taskstr=_p('cmd:tasklist_edit|param:taskstr|desc', "Which task do you want to update?"),
        new_content=_p('cmd:tasklist_edit|param:new_content|desc', "What do you want to change the task to?"),
        new_parent=_p('cmd:tasklist_edit|param:new_parent|desc', "Which task do you want to be the new parent?"),
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
                        'cmd:tasklist_edit|error:parse_taskstr',
                        "Could not find task number `{input}` in your tasklist."
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
                            'cmd:tasklist_edit|error:parse_parent',
                            "Could not find task number `{input}` in your tasklist."
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

            if await self.is_tasklist_channel(ctx.channel):
                tasklistui = await TasklistUI.fetch(tasklist, ctx.channel, ctx.guild)
                await tasklistui.summon()
            else:
                embed = discord.Embed(
                    colour=discord.Color.brand_green(),
                    description=t(_p(
                        'cmd:tasklist_edit|resp:success|desc',
                        "{tick} Task updated successfully."
                    )).format(tick=self.bot.config.emojis.tick),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        if new_content or new_parent:
            # Manual edit route
            await handle_update(ctx.interaction, new_content, new_parent)
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.defer(thinking=True, ephemeral=True)
                await ctx.interaction.delete_original_response()
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
                if not interaction.response.is_done():
                    await interaction.response.defer()

            await ctx.interaction.response.send_modal(editor)

    @tasklist_edit_cmd.autocomplete('taskstr')
    async def tasklist_edit_cmd_taskstr_acmpl(self, interaction: discord.Interaction, partial: str):
        return await self.task_acmpl(interaction, partial)

    @tasklist_edit_cmd.autocomplete('new_parent')
    async def tasklist_edit_cmd_new_parent_acmpl(self, interaction: discord.Interaction, partial: str):
        return await self.task_acmpl(interaction, partial)

    @tasklist_group.command(
        name=_p('cmd:tasklist_clear', "clear"),
        description=_p('cmd:tasklist_clear|desc', "Clear your tasklist.")
    )
    async def tasklist_clear_cmd(self, ctx: LionContext):
        t = ctx.bot.translator.t

        tasklist = await Tasklist.fetch(self.bot, self.data, ctx.author.id)
        await tasklist.update_tasklist(deleted_at=utc_now())
        await ctx.reply(
            t(_p(
                'cmd:tasklist_clear|resp:success',
                "Your tasklist has been cleared."
            )),
            ephemeral=True
        )
        tasklistui = await TasklistUI.fetch(tasklist, ctx.channel, ctx.guild)
        await tasklistui.summon()

    @tasklist_group.command(
        name=_p('cmd:tasklist_remove', "remove"),
        description=_p(
            'cmd:tasklist_remove|desc',
            "Remove tasks matching all the provided conditions. (E.g. remove tasks completed before today)."
        )
    )
    @appcmds.rename(
        taskidstr=_p('cmd:tasklist_remove|param:taskidstr', "tasks"),
        created_before=_p('cmd:tasklist_remove|param:created_before', "created_before"),
        updated_before=_p('cmd:tasklist_remove|param:updated_before', "updated_before"),
        completed=_p('cmd:tasklist_remove|param:completed', "completed"),
        cascade=_p('cmd:tasklist_remove|param:cascade', "cascade")
    )
    @appcmds.describe(
        taskidstr=_p(
            'cmd:tasklist_remove|param:taskidstr|desc',
            "List of task numbers or ranges to remove (e.g. 1, 2, 5-7, 8.1-3, 9-)."
        ),
        created_before=_p(
            'cmd:tasklist_remove|param:created_before|desc',
            "Only delete tasks created before the selected time."
        ),
        updated_before=_p(
            'cmd:tasklist_remove|param:updated_before|desc',
            "Only deleted tasks update (i.e. completed or edited) before the selected time."
        ),
        completed=_p(
            'cmd:tasklist_remove|param:completed',
            "Only delete tasks which are (not) complete."
        ),
        cascade=_p(
            'cmd:tasklist_remove|param:cascade',
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
                        'cmd:tasklist_remove_cmd|error:no_matching',
                        "No tasks on your tasklist match `{input}`"
                    ).format(input=taskidstr)
                )
                return

            conditions.append(self.data.Task.taskid == taskids)

        if created_before is not None or updated_before is not None:
            # TODO: Extract timezone from user settings
            timezone = None
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
                    'cmd:tasklist_remove_cmd|error:no_matching',
                    "No tasks on your tasklist matching all the given conditions!"
                ).format(input=taskidstr)
            )
            return
        taskids = [task.taskid for task in tasks]
        await tasklist.update_tasks(*taskids, cascade=cascade, deleted_at=utc_now())

        # Ack changes or summon tasklist
        if await self.is_tasklist_channel(ctx.channel):
            # Summon tasklist
            tasklistui = await TasklistUI.fetch(tasklist, ctx.channel, ctx.guild)
            await tasklistui.summon()
            await ctx.interaction.delete_original_response()
        else:
            # Ack deletion
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:tasklist_remove|resp:success',
                    "{tick} tasks deleted."
                )).format(tick=self.bot.config.emojis.tick)
            )
            await ctx.interaction.edit_original_response(embed=embed)

    @tasklist_group.command(
        name=_p('cmd:tasklist_tick', "tick"),
        description=_p('cmd:tasklist_tick|desc', "Mark the given tasks as completed.")
    )
    @appcmds.rename(
        taskidstr=_p('cmd:tasklist_tick|param:taskidstr', "tasks"),
        cascade=_p('cmd:tasklist_tick|param:cascade', "cascade")
    )
    @appcmds.describe(
        taskidstr=_p(
            'cmd:tasklist_tick|param:taskidstr|desc',
            "List of task numbers or ranges to remove (e.g. 1, 2, 5-7, 8.1-3, 9-)."
        ),
        cascade=_p(
            'cmd:tasklist_tick|param:cascade|desc',
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
                        'cmd:tasklist_remove_cmd|error:no_matching',
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

        # Ack changes or summon tasklist
        if await self.is_tasklist_channel(ctx.channel):
            # Summon tasklist
            tasklistui = await TasklistUI.fetch(tasklist, ctx.channel, ctx.guild)
            await tasklistui.summon()
            await ctx.interaction.delete_original_response()
        else:
            # Ack edit
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:tasklist_tick|resp:success',
                    "{tick} tasks marked as complete."
                )).format(tick=self.bot.config.emojis.tick)
            )
            await ctx.interaction.edit_original_response(embed=embed)

    @tasklist_group.command(
        name=_p('cmd:tasklist_untick', "untick"),
        description=_p('cmd:tasklist_untick|desc', "Mark the given tasks as incomplete.")
    )
    @appcmds.rename(
        taskidstr=_p('cmd:tasklist_untick|param:taskidstr', "taskids"),
        cascade=_p('cmd:tasklist_untick|param:cascade', "cascade")
    )
    @appcmds.describe(
        taskidstr=_p(
            'cmd:tasklist_untick|param:taskidstr|desc',
            "List of task numbers or ranges to remove (e.g. 1, 2, 5-7, 8.1-3, 9-)."
        ),
        cascade=_p(
            'cmd:tasklist_untick|param:cascade|desc',
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
                    'cmd:tasklist_remove_cmd|error:no_matching',
                    "No tasks on your tasklist match `{input}`"
                ).format(input=taskidstr)
            )
            return

        tasks = [tasklist.tasklist[taskid] for taskid in taskids]
        tasks = [task for task in tasks if task.completed_at is not None]
        taskids = [task.taskid for task in tasks]
        if taskids:
            await tasklist.update_tasks(*taskids, cascade=cascade, completed_at=None)

        # Ack changes or summon tasklist
        if await self.is_tasklist_channel(ctx.channel):
            # Summon tasklist
            tasklistui = await TasklistUI.fetch(tasklist, ctx.channel, ctx.guild)
            await tasklistui.summon()
            await ctx.interaction.delete_original_response()
        else:
            # Ack edit
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:tasklist_untick|resp:success',
                    "{tick} tasks marked as incomplete."
                )).format(tick=self.bot.config.emojis.tick)
            )
            await ctx.interaction.edit_original_response(embed=embed)

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

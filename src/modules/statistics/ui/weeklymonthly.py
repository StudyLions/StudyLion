from typing import Optional, TypeAlias, Union
from enum import Enum, IntEnum
from datetime import timedelta, datetime
from dataclasses import dataclass
from collections import defaultdict
import asyncio
from asyncio import Future
import gc
import re

import discord
from discord.ui.button import ButtonStyle, button, Button
from discord.ui.text_input import TextInput, TextStyle
from discord.ui.select import select, Select, SelectOption

from meta import LionBot, LionCog, conf
from meta.errors import UserInputError
from utils.lib import MessageArgs
from utils.ui import LeoUI, ModalRetryUI, FastModal, error_handler_for
from babel.translator import ctx_translator, LazyStr
from babel.utils import local_month
from gui.cards import WeeklyGoalCard, WeeklyStatsCard, MonthlyGoalCard, MonthlyStatsCard
from gui.base import CardMode
from core.lion_member import LionMember

from ..graphics.weekly import get_weekly_card
from ..graphics.monthly import get_monthly_card
from ..graphics.goals import get_goals_card
from ..data import StatsData
from .. import babel
from ..lib import (
    extract_monthid, extract_weekid, apply_month_offset, apply_week_offset, month_difference, week_difference
)

from .base import StatsUI

_p = babel._p

ANKI = False

GoalCard: TypeAlias = Union[WeeklyGoalCard, MonthlyGoalCard]
StatsCard: TypeAlias = Union[WeeklyStatsCard, MonthlyStatsCard]


class PeriodType(IntEnum):
    WEEKLY = 0
    MONTHLY = 1


class StatType(IntEnum):
    VOICE = 0
    TEXT = 1
    ANKI = 2


class StatPage(Enum):
    WEEKLY_VOICE = (0, PeriodType.WEEKLY, StatType.VOICE)
    WEEKLY_TEXT = (1, PeriodType.WEEKLY, StatType.TEXT)
    if ANKI:
        WEEKLY_ANKI = (2, PeriodType.WEEKLY, StatType.ANKI)
    MONTHLY_VOICE = (3, PeriodType.MONTHLY, StatType.VOICE)
    MONTHLY_TEXT = (4, PeriodType.MONTHLY, StatType.TEXT)
    if ANKI:
        MONTHLY_ANKI = (5, PeriodType.MONTHLY, StatType.ANKI)

    @classmethod
    def from_value(cls, value: int) -> 'StatPage':
        return next(item for item in cls if item.select_value == value)

    @property
    def period(self) -> PeriodType:
        return self.value[1]

    @property
    def stat(self) -> StatType:
        return self.value[2]

    @property
    def goal_key(self) -> tuple[str, str, str]:
        if self.period == PeriodType.WEEKLY:
            periodid = 'weekid'
        elif self.period == PeriodType.MONTHLY:
            periodid = 'monthlyid'
        return ('guildid', 'userid', periodid)

    @property
    def select_value(self) -> int:
        return self.value[0]

    @property
    def select_name(self) -> LazyStr:
        if self.period is PeriodType.WEEKLY:
            if self.stat is StatType.VOICE:
                name = _p(
                    'menu:stat_type|opt:weekly_voice|name',
                    "Weekly Voice Statistics"
                )
            elif self.stat is StatType.TEXT:
                name = _p(
                    'menu:stat_type|opt:weekly_text|name',
                    "Weekly Text Statistics"
                )
            elif self.stat is StatType.ANKI:
                name = _p(
                    'menu:stat_type|opt:weekly_anki|name',
                    "Weekly Anki Statistics"
                )
        elif self.period is PeriodType.MONTHLY:
            if self.stat is StatType.VOICE:
                name = _p(
                    'menu:stat_type|opt:monthly_voice|name',
                    "Monthly Voice Statistics"
                )
            elif self.stat is StatType.TEXT:
                name = _p(
                    'menu:stat_type|opt:monthly_text|name',
                    "Monthly Text Statistics"
                )
            elif self.stat is StatType.ANKI:
                name = _p(
                    'menu:stat_type|opt:monthly_anki|name',
                    "Monthly Anki Statistics"
                )
        return name


class GoalEditor(FastModal):
    limit = 10
    task_regex = re.compile(r"\s*(?:\[\s*(?P<check>[^\]]+)?\s*\])?\s*(?P<task>.+)")

    # First goal is usually tasks completed
    first_goal = TextInput(
        label='...',
        style=TextStyle.short,
        max_length=4,
        required=False
    )

    def setup_first_goal(self):
        t = ctx_translator.get().t
        field = self.first_goal
        field.label = t(_p(
            'modal:goal_editor|field:task_goal|label',
            "Task goal"
        ))
        field.placeholder = t(_p(
            'modal:goal_editor|field:task_goal|placeholder',
            "Enter the number of tasklist tasks you aim to do"
        ))

    async def parse_first_goal(self) -> Optional[int]:
        t = ctx_translator.get().t
        string = self.first_goal.value.strip()
        if not string:
            result = None
        elif not string.isdigit():
            raise UserInputError(t(_p(
                'modal:goal_editor|field:task_goal|error:NAN',
                "The provided task goal `{input}` is not a number! Please try again."
            )).format(input=string)
            )
        else:
            result = int(string)
        return result

    # Second goal is either message count, voice hours, or cards completed
    second_goal = TextInput(
        label='...',
        style=TextStyle.short,
        max_length=6,
        required=False
    )

    def setup_second_goal(self) -> Optional[int]:
        t = ctx_translator.get().t
        field = self.second_goal
        # TODO: Study vs Voice customisation
        if self.stat_page.stat is StatType.VOICE:
            field.label = t(_p(
                'modal:goal_editor|field:voice_goal|label',
                "Study time goal"
            ))
            field.placeholder = t(_p(
                'modal:goal_editor|field:voice_goal|placeholder',
                "Enter a number of hours of study to aim for."
            ))
        elif self.stat_page.stat is StatType.TEXT:
            field.label = t(_p(
                'modal:goal_editor|field:text_goal|label',
                "Message goal"
            ))
            field.placeholder = t(_p(
                'modal:goal_editor|field:text_goal|placeholder',
                "Enter a message count to aim for."
            ))
        elif self.stat_page.stat is StatType.ANKI:
            field.label = t(_p(
                'modal:goal_editor|field:anki_goal|label',
                "Card goal"
            ))
            field.placeholder = t(_p(
                'modal:goal_editor|field:anki_goal|label',
                "Enter a number of card revisions to aim for."
            ))

    async def parse_second_goal(self) -> Optional[int]:
        t = ctx_translator.get().t
        string = self.second_goal.value.strip()
        if not string:
            result = None
        elif not string.isdigit():
            if self.stat_page.stat is StatType.VOICE:
                raise UserInputError(
                    t(_p(
                        'modal:goal_editor|field:voice_goal|error:NAN',
                        "The provided study time goal `{input}` is not a number! Please try again."
                    )).format(input=string)
                )
            elif self.stat_page.stat is StatType.TEXT:
                raise UserInputError(
                    t(_p(
                        'modal:goal_editor|field:text_goal|error:NAN',
                        "The provided message goal `{input}` is not a number! Please try again."
                    )).format(input=string)
                )
            elif self.stat_page.stat is StatType.ANKI:
                raise UserInputError(
                    t(_p(
                        'modal:goal_editor|field:anki_goal|error:NAN',
                        "The provided card goal `{input}` is not a number! Please try again."
                    )).format(input=string)
                )
        else:
            result = int(string)
        return result

    # Both weekly and monthly have task goals, independent of mode
    task_editor = TextInput(
        label='',
        style=TextStyle.long,
        max_length=500,
        required=False
    )

    def setup_task_editor(self):
        t = ctx_translator.get().t
        field = self.task_editor

        if self.stat_page.period is PeriodType.WEEKLY:
            field.label = t(_p(
                'modal:goal_editor|field:weekly_task_editor|label',
                "Tasks to complete this week (one per line)"
            ))
            field.placeholder = t(_p(
                'modal:goal_editor|field:weekly_task_editor|placeholder',
                "[ ] Write my biology essay\n"
                "[x] Complete the second maths assignment\n"
            ))
        else:
            field.label = t(_p(
                'modal:goal_editor|field:monthly_task_editor|label',
                "Tasks to complete this month (one per line)"
            ))
            field.placeholder = t(_p(
                'modal:goal_editor|field:monthly_task_editor|placeholder',
                "[ ] Write my biology essay\n"
                "[x] Complete the second maths assignment\n"
            ))

    async def parse_task_editor(self) -> list[tuple[bool, str]]:
        t = ctx_translator.get().t

        task_lines = (line.strip() for line in self.task_editor.value.splitlines())
        task_lines = [line for line in task_lines if line]
        tasks: list[tuple[bool, str]] = []
        for line in task_lines:
            match = self.task_regex.match(line)
            if not match:
                # This should be essentially impossible
                # since the regex is a wildcard
                raise UserInputError(
                    t(_p(
                        'modal:goal_editor||field:task_editor|error:parse_general',
                        "Malformed task!\n`{input}`"
                    )).format(input=line)
                )
            # TODO Length validation
            check = bool(match['check'])
            task = match['task']
            if not task or not (task := task.strip()):
                continue
            tasks.append((check, task))

        return tasks

    def setup(self):
        t = ctx_translator.get().t
        if self.stat_page.period is PeriodType.WEEKLY:
            self.title = t(_p(
                'modal:goal_editor|title',
                "Weekly goal editor"
            ))
        else:
            self.title = t(_p(
                'modal:goal_editor|monthly|title',
                "Monthly goal editor"
            ))
        self.setup_first_goal()
        self.setup_second_goal()
        self.setup_task_editor()

    def __init__(self, stat_page: StatPage, *args, **kwargs):
        self.stat_page = stat_page
        self.setup()
        super().__init__(*args, **kwargs)

    async def parse(self) -> tuple[Optional[int], Optional[int], list[tuple[bool, str]]]:
        """
        Parse goal editor submission.

        Raises UserInputError with a human-readable message if the input cannot be parsed.
        """
        first = await self.parse_first_goal()
        second = await self.parse_second_goal()
        tasks = await self.parse_task_editor()

        return (first, second, tasks)

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction: discord.Interaction, error: UserInputError):
        await ModalRetryUI(self, error.msg).respond_to(interaction)


PageKey: TypeAlias = tuple[bool, int, StatPage]


class WeeklyMonthlyUI(StatsUI):
    def __init__(self, bot, user, guild, **kwargs):
        super().__init__(bot, user, guild, **kwargs)

        self.data: StatsData = bot.get_cog('StatsCog').data

        # State
        self.lion: Optional[LionMember] = None

        self._stat_page: StatPage = StatPage.WEEKLY_VOICE
        self._week_offset = 0
        self._month_offset = 0

        self._showing_selector = False
        self._selector_cache = {}  # (offset, StatPage) -> SelectMenu
        self._selector_offset = defaultdict(lambda: 0)  # StatPage -> top entry offset
        self._selector_offset_limit: dict[tuple[bool, StatType], int] = {}  # bottom entry offset

        # Card data
        self._card_cache: dict[PageKey, tuple[Future[GoalCard], Future[StatsCard]]] = {}

    @property
    def key(self) -> PageKey:
        return (self._showing_global, self._offset, self._stat_page)

    @property
    def tasks(self):
        """
        Return the render tasks for the current key.
        """
        return self._card_cache.get(self.key, (None, None))

    @property
    def weekly(self):
        """
        Whether the UI is in a weekly mode.
        """
        return self._stat_page.period == PeriodType.WEEKLY

    @property
    def _offset(self):
        """
        Return the current weekly or monthly offset, as appropriate.
        """
        return self._week_offset if self.weekly else self._month_offset

    @_offset.setter
    def _offset(self, value):
        if self.weekly:
            self._week_offset = value
        else:
            self._month_offset = value

    async def cleanup(self):
        await super().cleanup()

        # Card cache is potentially quite large, so explicitly garbage collect
        del self._card_cache
        gc.collect()

    @select(placeholder="...")
    async def type_menu(self, selection: discord.Interaction, menu: Select):
        value = StatPage.from_value(int(menu.values[0]))
        if self._stat_page is not value:
            await selection.response.defer(thinking=True, ephemeral=True)
            self._stat_page = value
            await self.refresh(thinking=selection)
        else:
            await selection.response.defer()

    async def type_menu_refresh(self):
        # TODO: Check enabled types
        t = self.bot.translator.t
        options = []
        for item in StatPage:
            option = SelectOption(label=t(item.select_name), value=str(item.select_value))
            option.default = item is self._stat_page
            options.append(option)
        self.type_menu.options = options

    @button(label="Edit Goals", style=ButtonStyle.blurple)
    async def edit_button(self, press: discord.Interaction, pressed: Button):
        """
        Press to open the goal editor for this stat type.
        """
        # Extract goal data
        # Open goal modal
        # Parse goal modal submit, validate input
        # If validation is successful, then update goal list by replacement
        t = self.bot.translator.t
        now = self.lion.now

        if self.weekly:
            goal_model = self.data.WeeklyGoals
            tasks_model = self.data.WeeklyTasks
            weekid = extract_weekid(apply_week_offset(now, self._week_offset))
            key = {'guildid': self.guildid or 0, 'userid': self.userid, 'weekid': weekid}
        else:
            goal_model = self.data.MonthlyGoals
            tasks_model = self.data.MonthlyTasks
            monthid = extract_monthid(apply_month_offset(now, self._month_offset))
            key = {'guildid': self.guildid or 0, 'userid': self.userid, 'monthid': monthid}

        if self._stat_page.stat is StatType.VOICE:
            goal_keys = ('task_goal', 'study_goal')
        elif self._stat_page.stat is StatType.TEXT:
            goal_keys = ('task_goal', 'message_goal')
        elif self._stat_page.stat is StatType.ANKI:
            goal_keys = ('task_goal', 'card_goal')

        goals = await goal_model.fetch_or_create(*key.values())
        tasks = await tasks_model.fetch_where(**key)

        modal = GoalEditor(self._stat_page)
        orig_first = goals[goal_keys[0]]
        orig_second = goals[goal_keys[1]]
        modal.first_goal.default = str(orig_first) if orig_first is not None else None
        modal.second_goal.default = str(orig_second) if orig_second is not None else None
        if tasks:
            tasklines = [f"[{'x' if task.completed else ' '}] {task.content}" for task in tasks]
            modal.task_editor.default = '\n'.join(tasklines)

        @modal.submit_callback()
        async def parse_goals(interaction: discord.Interaction):
            new_first, new_second, new_tasks = await modal.parse()
            # Successful parse, ack the interaction
            await interaction.response.defer(thinking=True)

            modified = False

            # Update the numerical goals, using the correct keys
            if new_first != orig_first or new_second != orig_second:
                modified = True
                update_args = dict(zip(goal_keys, (new_first, new_second)))
                await goals.update(**update_args)

            # Update the tasklist
            if len(new_tasks) != len(tasks) or not all(t == new_t for (t, new_t) in zip(tasks, new_tasks)):
                modified = True
                async with self.bot.db.connection() as conn:
                    async with conn.transaction():
                        await tasks_model.table.delete_where(**key).with_connection(conn)
                        if new_tasks:
                            await tasks_model.table.insert_many(
                                (*key.keys(), 'completed', 'content'),
                                *((*key.values(), *new_task) for new_task in new_tasks)
                            ).with_connection(conn)

            if modified:
                # Check whether the UI finished while we were interacting
                if not self._stopped.done():
                    # If either goal type was modified, clear the rendered cache and refresh
                    for page_key, (goalf, statf) in self._card_cache.items():
                        # If the stat period type is the same as the current period type
                        if page_key[2].period is self._stat_page.period:
                            self._card_cache[page_key] = (None, statf)
                    await self.refresh(thinking=interaction)
                else:
                    await interaction.delete_original_response()
        await press.response.send_modal(modal)

    async def edit_button_refresh(self):
        t = self.bot.translator.t
        self.edit_button.disabled = (self._offset != 0)
        self.edit_button.label = t(_p(
            'ui:weeklymonthly|button:edit_goals|label',
            "Edit Goals"
        ))

    def _selector_option_for(self, offset: int, page_type: StatPage) -> SelectOption:
        key = (offset, page_type)

        if (option := self._selector_cache.get(key, None)) is None:
            t = self.bot.translator.t
            now = self.lion.now.replace(hour=0, minute=0, second=0, microsecond=0)

            # Generate the option
            if page_type.period is PeriodType.MONTHLY:
                now = now.replace(day=1)  # Ensures a valid date after applying month offset
                target = apply_month_offset(now, offset)
                format = _p(
                    'ui:weeklymonthly|menu:period|monthly|label',
                    "{month} {year}"
                )
                option = SelectOption(
                    label=t(format).format(
                        month=local_month(target.month),
                        year=target.year
                    ),
                    value=str(offset)
                )
            else:
                start = apply_week_offset(now, offset)
                end = start + timedelta(weeks=1)

                label_format = _p(
                    'ui:weeklymonthly|menu:period|weekly|label',
                    "{year} W{week}"
                )
                desc_format = _p(
                    'ui:weeklymonthly|menu:period|weekly|desc',
                    "{start_day} {start_month} {start_year} to {end_day} {end_month} {end_year}"
                )

                start_day, end_day = start.day, end.day
                start_month, end_month = local_month(start.month, short=True), local_month(end.month, short=True)
                start_year, end_year = start.year, end.year

                option = SelectOption(
                    value=str(offset),
                    label=t(label_format).format(
                        year=start.year,
                        week=start.isocalendar().week
                    ),
                    description=t(desc_format).format(
                        start_day=start_day, start_month=start_month, start_year=start_year,
                        end_day=end_day, end_month=end_month, end_year=end_year
                    )
                )

            # Add to cache
            self._selector_cache[key] = option

        return option

    async def _fetch_bottom_offset(self, page_type: StatPage) -> int:
        """
        Calculate the bottom-most selection offset for the given StatPage.

        This is calculated based on the earliest study/text/card session for this user/member.
        The result is cached in `self._selector_offset_limit`.
        """
        cache_key = (self._showing_global, page_type)

        if (result := self._selector_offset_limit.get(cache_key, None)) is None:
            # Fetch first session for this page and global mode
            data_key = {'userid': self.userid}
            if not self._showing_global:
                data_key['guildid'] = self.guildid

            if page_type.stat is StatType.VOICE:
                model = self.data.VoiceSessionStats
            elif page_type.stat is StatType.TEXT:
                model = self.bot.get_cog('TextTrackerCog').data.TextSessions
            else:
                model = self.data.VoiceSessionStats

            first_result = await model.table.select_one_where(**data_key).order_by('start_time')
            if first_result is None:
                result = 0
            else:
                now = self.lion.now
                tz = self.lion.timezone
                start = first_result['start_time'].astimezone(tz)

                if page_type.period is PeriodType.WEEKLY:
                    result = week_difference(start, now)
                else:
                    result = month_difference(start, now)

            self._selector_offset_limit[cache_key] = result
        return result

    @button(label="Select Period", style=ButtonStyle.blurple)
    async def select_button(self, press: discord.Interaction, pressed: Button):
        """
        Press to open the period selector for this stat type.
        """
        await press.response.defer(thinking=True, ephemeral=True)
        self._showing_selector = not self._showing_selector
        await self.refresh(thinking=press)

    async def select_button_refresh(self):
        t = self.bot.translator.t
        button = self.select_button

        if self._showing_selector:
            button.label = t(_p(
                'ui:weeklymonthly|button:period|close|label',
                "Close Selector"
            ))
        elif self.weekly:
            button.label = t(_p(
                'ui:weeklymonthly|button:period|weekly|label',
                "Select Week"
            ))
        else:
            button.label = t(_p(
                'ui:weeklymonthly|button:period|monthly|label',
                "Select Month"
            ))

    @select(placeholder='...', max_values=1)
    async def period_menu(self, selection: discord.Interaction, menu: Select):
        if menu.values:
            await selection.response.defer(thinking=True)
            result = int(menu.values[0])
            if result == -1:
                # More recent
                # Change the selector offset for this selector key
                current_start = self._selector_offset[self._stat_page]
                new_start = current_start - 23 if current_start != 24 else 0
                self._selector_offset[self._stat_page] = new_start
            elif result == -2:
                # More older
                # Increase the selector offset for this selector key
                current_start = self._selector_offset[self._stat_page]
                new_start = current_start + 23 if current_start != 0 else 24
                self._selector_offset[self._stat_page] = new_start
            else:
                # Set the page offset for this period type and refresh
                self._offset = result

            await self.refresh(thinking=selection)
        else:
            await selection.response.defer()

    async def period_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.period_menu
        options = []

        starting = self._selector_offset[self._stat_page]  # Offset of first entry to display
        if starting > 0:
            # start with More ... (prev)
            more_first = SelectOption(
                value="-1",
                label="More (More recent)"
            )
            options.append(more_first)

        bottom = await self._fetch_bottom_offset(self._stat_page)
        if bottom - starting + 1 + len(options) <= 24:
            # Put all remaining entries into the options lise
            for offset in range(starting, bottom + 1):
                option = self._selector_option_for(offset, self._stat_page)
                option.default = (offset == self._offset)
                options.append(option)
        else:
            # Put the next 23 or 24 options there, and cap with a more option
            for offset in range(starting, starting + 24 - len(options)):
                option = self._selector_option_for(offset, self._stat_page)
                option.default = (offset == self._offset)
                options.append(option)
            more_last = SelectOption(
                value='-2',
                label="More (Older)"
            )
            options.append(more_last)

        menu.options = options
        if self.weekly:
            menu.placeholder = t(_p(
                'ui:weeklymonthly|menu:period|weekly|placeholder',
                "Select a week to display"
            ))
        else:
            menu.placeholder = t(_p(
                'ui:weeklymonthly|menu:period|monthly|placeholder',
                "Select a month to display"
            ))

    @button(label="Global Stats", style=ButtonStyle.blurple)
    async def global_button(self, press: discord.Interaction, pressed: Button):
        """
        Switch between local and global statistics modes.
        """
        await press.response.defer(thinking=True, ephemeral=True)
        self._showing_global = not self._showing_global
        # TODO: Asynchronously update user preferences
        self._showing_global_setting.data = self._showing_global
        await self._showing_global_setting.write()

        await self.refresh(thinking=press if not self._showing_global else None)

        if self._showing_global:
            t = self.bot.translator.t
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                description=t(_p(
                    'ui:WeeklyMonthly|button:global|resp:success',
                    "You will now see combined "
                    "statistics from all your servers (where applicable)! Press again to revert."
                ))
            )
            await press.edit_original_response(embed=embed)

    async def global_button_refresh(self):
        button = self.global_button
        t = self.bot.translator.t

        if self._showing_global:
            button.label = t(_p(
                'ui:WeeklyMonthly|button:global|mode:local',
                "Server Statistics"
            ))
        else:
            button.label = t(_p(
                'ui:WeeklyMonthly|button:global|mode:global',
                "Global Statistics"
            ))

    async def refresh_components(self):
        await asyncio.gather(
            self.edit_button_refresh(),
            self.select_button_refresh(),
            self.global_button_refresh(),
            self.close_button_refresh(),
            self.type_menu_refresh(),
            self.select_button_refresh(),
        )
        # TODO: Lazy refresh
        self._layout = [
            (self.type_menu,),
            (self.edit_button, self.select_button, self.global_button, self.close_button)
        ]

        voting = self.bot.get_cog('TopggCog')
        if voting and not await voting.check_voted_recently(self.userid):
            premiumcog = self.bot.get_cog('PremiumCog')
            if not (premiumcog and await premiumcog.is_premium_guild(self.guild.id)):
                self._layout.append((voting.vote_button(),))

        if self._showing_selector:
            await self.period_menu_refresh()
            self._layout.append((self.period_menu,))

    async def _tmp_fetch_goals(self):
        data = self.data
        now = self.lion.now

        if self.weekly:
            goal_model = data.WeeklyGoals
            tasks_model = data.WeeklyTasks
            weekid = extract_weekid(apply_week_offset(now, self._week_offset))
            key = {'guildid': self.guildid or 0, 'userid': self.userid, 'weekid': weekid}
        else:
            goal_model = data.MonthlyGoals
            tasks_model = data.MonthlyTasks
            now = now.replace(day=1)  # Ensures a valid date after applying month offset
            monthid = extract_monthid(apply_month_offset(now, self._month_offset))
            key = {'guildid': self.guildid or 0, 'userid': self.userid, 'monthid': monthid}

        if self._stat_page.stat is StatType.VOICE:
            goal_keys = ('task_goal', 'study_goal')
        elif self._stat_page.stat is StatType.TEXT:
            goal_keys = ('task_goal', 'message_goal')
        elif self._stat_page.stat is StatType.ANKI:
            goal_keys = ('task_goal', 'card_goal')

        goals = await goal_model.fetch_or_create(*key.values())
        tasks = await tasks_model.fetch_where(**key)

        numbers = (goals.task_goal, goals.study_goal)
        tasklist = [
            (i, task.content, task.completed)
            for i, task in enumerate(tasks)
        ]
        return numbers, tasklist

    async def _render_goals(self, show_global, offset, stat_page):
        if stat_page.stat is StatType.VOICE:
            mode = CardMode.VOICE
        elif stat_page.stat is StatType.TEXT:
            mode = CardMode.TEXT
        elif stat_page.stat is StatType.ANKI:
            mode = CardMode.ANKI

        card = await get_goals_card(
            self.bot,
            self.userid,
            self.guildid or 0,
            offset,
            (self._stat_page.period is PeriodType.WEEKLY),
            mode
        )
        await card.render()
        return card

    async def _render_stats(self, show_global, offset, stat_page):
        if stat_page.stat is StatType.VOICE:
            mode = CardMode.VOICE
        elif stat_page.stat is StatType.TEXT:
            mode = CardMode.TEXT
        elif stat_page.stats is StatType.ANKI:
            mode = CardMode.ANKI

        if stat_page.period == PeriodType.WEEKLY:
            card = await get_weekly_card(
                self.bot,
                self.userid,
                self.guildid,
                offset,
                mode
            )
        else:
            card = await get_monthly_card(
                self.bot,
                self.userid,
                self.guildid,
                offset,
                mode
            )
        await card.render()
        return card

    def _prepare(self, *key):
        """
        Launch render tasks for the given offset and stat_type.

        Avoids re-rendering if completed or already in progress.
        """
        goal_task, stats_task = self._card_cache.get(key, (None, None))
        if goal_task is None or goal_task.cancelled():
            goal_task = asyncio.create_task(self._render_goals(*key))
        if stats_task is None or stats_task.cancelled():
            stats_task = asyncio.create_task(self._render_stats(*key))

        tasks = (goal_task, stats_task)
        self._card_cache[key] = tasks
        return tasks

    async def fetch_cards(self, *key):
        """
        Render the cards for the current offset and stat type.

        Avoids re-rendering.
        Will raise asyncio.CancelledError if a rendering task is cancelled.
        """
        tasks = self._prepare(*key)
        await asyncio.gather(*tasks)
        return (tasks[0].result(), tasks[1].result())

    async def reload(self):
        """
        Reload the UI data, applying cache where possible.
        """
        self._showing_global = self._showing_global_setting.value if self.guild else True
        await self.fetch_cards(*self.key)

    async def make_message(self) -> MessageArgs:
        goal_card, stats_card = await self.fetch_cards(*self.key)
        files = [
            goal_card.as_file('goals.png'),
            stats_card.as_file('stats.png')
        ]
        return MessageArgs(files=files)

    async def run(self, interaction: discord.Interaction):
        """
        Execute the UI using the given interaction.
        """
        self._original = interaction
        self.lion = await self.bot.core.lions.fetch_member(self.guildid, self.userid)
        self._showing_global_setting = self.lion.luser.config.get('show_global_stats')

        await self.refresh()

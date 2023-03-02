from typing import Optional
from enum import Enum
import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, Select, SelectOption

from utils.lib import MessageArgs

from .. import babel
from .base import StatsUI

from gui.cards import WeeklyStatsCard, MonthlyStatsCard, WeeklyGoalCard, MonthlyGoalCard

_p = babel._p


class SessionType(Enum):
    Voice = 0
    Text = 1
    Anki = 2


class GoalBaseUI(StatsUI):
    """
    switcher row, local|global
    voice, text, anki
    Prev, Select, Next, Edit Goals
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__rendered = {}  # (offset, type) |-> (goal_card, stats_card)
        self._offset: int = 0
        self._stat_type: Optional[SessionType] = None

    @property
    def _key(self):
        return (self._offset, self._stat_type)

    @property
    def _rendered(self):
        return self.__rendered.get(self._key, None) is not None

    async def lazy_rerun_using(self, interaction: discord.Interaction):
        if self._rendered:
            await interaction.response.defer()
            waiting = None
        else:
            await interaction.response.defer(thinking=True)
            waiting = interaction
        await self.run(waiting_interaction=waiting)

    @button(label='VOICE_PLACEHOLDER')
    async def voice_pressed(self, press: discord.Interaction, pressed: Button):
        self._stat_type = SessionType.Voice
        await self.lazy_rerun_using(press)

    @button(label='TEXT_PLACEHOLDER')
    async def text_pressed(self, press: discord.Interaction, pressed: Button):
        self._stat_type = SessionType.Text
        await self.lazy_rerun_using(press)

    @button(label='ANKI_PLACEHOLDER')
    async def anki_pressed(self, press: discord.Interaction, pressed: Button):
        self._stat_type = SessionType.Anki
        await self.lazy_rerun_using(press)

    @button(label="PREV_PLACEHOLDER")
    async def prev_pressed(self, press: discord.Interaction, pressed: Button):
        self._offset -= 1
        await self.lazy_rerun_using(press)

    @button(label="NEXT_PLACEHOLDER")
    async def next_pressed(self, press: discord.Interaction, pressed: Button):
        self._offset += 1
        await self.lazy_rerun_using(press)

    @button(label="SELECT_PLACEHOLDER")
    async def next_pressed(self, press: discord.Interaction, pressed: Button):
        # TODO: Date selection
        ...

    @button(label="EDIT_PLACEHOLDER")
    async def edit_pressed(self, press: discord.Interaction, pressed: Button):
        # TODO: Goal editing
        ...


class MonthlyUI(StatsUI):
    _ui_name = _p('ui:MonthlyUI|name', 'Monthly')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._rendered = False
        self._stats_card: Optional[MonthlyStatsCard] = None
        self._goals_card: Optional[MonthlyGoalCard] = None

    async def redraw(self):
        self._layout = [
            (*self._switcher_buttons, self.toggle_pressed)
        ]
        await super().redraw()

    async def make_message(self) -> MessageArgs:
        if not self._rendered:
            await self._render()

        stats_file = self._stats_card.as_file('monthly_stats.png')
        goals_file = self._goals_card.as_file('monthly_goals.png')
        return MessageArgs(files=[goals_file, stats_file])

    async def _render(self):
        await asyncio.gather(self._render_goals(), self._render_stats())
        self._rendered = True

    async def _render_stats(self):
        args = await MonthlyStatsCard.sample_args(None)
        card = MonthlyStatsCard(**args)
        await card.render()
        self._stats_card = card
        return card

    async def _render_goals(self):
        args = await MonthlyGoalCard.sample_args(None)
        card = WeeklyGoalCard(**args)
        await card.render()
        self._goals_card = card
        return card


class WeeklyUI(StatsUI):
    _ui_name = _p('ui:WeeklyUI|name', 'Weekly')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._rendered = False
        self._stats_card: Optional[WeeklyStatsCard] = None
        self._goals_card: Optional[WeeklyGoalCard] = None

    async def redraw(self):
        self._layout = [
            [*self._switcher_buttons]
        ]
        if self.guild:
            self._layout[0].append(self.toggle_pressed)
        await super().redraw()

    async def _render(self):
        await asyncio.gather(self._render_goals(), self._render_stats())
        self._rendered = True

    async def make_message(self) -> MessageArgs:
        if not self._rendered:
            await self._render()

        stats_file = self._stats_card.as_file('weekly_stats.png')
        goals_file = self._goals_card.as_file('weekly_goals.png')
        return MessageArgs(files=[goals_file, stats_file])

    async def _render_stats(self):
        args = await WeeklyStatsCard.sample_args(None)
        card = WeeklyStatsCard(**args)
        await card.render()
        self._stats_card = card
        return card

    async def _render_goals(self):
        args = await WeeklyGoalCard.sample_args(None)
        card = WeeklyGoalCard(**args)
        await card.render()
        self._goals_card = card
        return card

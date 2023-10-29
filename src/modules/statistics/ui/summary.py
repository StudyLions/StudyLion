from typing import Optional
import asyncio

import discord

from utils.lib import MessageArgs

from .. import babel
from .base import StatsUI

from gui.cards import StatsCard, ProfileCard
from ..graphics.stats import get_stats_card

_p = babel._p


class SummaryUI(StatsUI):
    _ui_name = _p('ui:SummaryUI|name', 'Summary')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._rendered = False
        self._stats_card: Optional[StatsCard] = None
        self._profile_card: Optional[ProfileCard] = None

    async def redraw(self):
        if self.guild is not None:
            self._layout = [
                (*self._switcher_buttons, self.toggle_pressed)
            ]
        else:
            self._layout = [
                self._switcher_buttons
            ]
        await super().redraw()

    async def make_message(self) -> MessageArgs:
        if not self._rendered:
            await self._render()

        stats_file = self._stats_card.as_file('stats.png')
        profile_file = self._profile_card.as_file('profile.png')

        # TODO: Refresh peer timeouts on interaction usage
        # TODO: Write close and cleanup
        return MessageArgs(files=[profile_file, stats_file])

    async def _render(self):
        await asyncio.gather(self._render_stats(), self._render_profile())
        self._rendered = True

    async def _render_stats(self):
        card = await get_stats_card(self.bot, self.data, self.user.id, self.guild.id if self.guild else None)
        await card.render()
        self._stats_card = card
        return card

    async def _render_profile(self):
        args = await ProfileCard.sample_args(None)
        card = ProfileCard(**args)
        await card.render()
        self._profile_card = card
        return card

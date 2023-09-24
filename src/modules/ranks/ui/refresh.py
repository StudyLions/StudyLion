from typing import Optional
import asyncio

import discord
from discord.ui.select import select, Select, SelectOption, RoleSelect
from discord.ui.button import button, Button, ButtonStyle

from meta import conf, LionBot
from meta.logger import log_wrap
from core.data import RankType
from data import ORDER

from utils.ui import MessageUI
from utils.lib import MessageArgs, utc_now
from babel.translator import ctx_translator

from .. import babel, logger
from ..data import AnyRankData
from ..utils import rank_model_from_type, format_stat_range, stat_data_to_value
from .editor import RankEditor
from .preview import RankPreviewUI

_p = babel._p


class RankRefreshUI(MessageUI):
    # Cache of live rank UIs, mainly for introspection
    _running = set()

    def __init__(self, bot: LionBot, guild: discord.Guild, **kwargs):
        super().__init__(**kwargs)
        self.bot = bot
        self.guild = guild

        self.stage_ranks = None
        self.stage_members = None
        self.stage_roles = None
        self.stage_compute = None

        self.to_remove = 0
        self.to_add = 0
        self.removed = 0
        self.added = 0

        self.error: Optional[str] = None
        self.done = False

        self.errors: list[str] = []

        self._loop_task: Optional[asyncio.Task] = None
        self._wakeup = asyncio.Event()

    # ----- API -----
    async def set_error(self, error: str):
        """
        Set the given error, refresh, and stop.
        """
        self.error = error
        await self.refresh()
        await self.close()

    async def set_done(self):
        self.done = True
        await self.refresh()
        await self.close()

    def poke(self):
        self._wakeup.set()

    def start(self):
        self._loop_task = asyncio.create_task(self._refresh_loop(), name='Rank RefreshUI Monitor')
        self._running.add(self)

    async def run(self, *args, **kwargs):
        await super().run(*args, **kwargs)
        self.start()

    async def cleanup(self):
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self._running.discard(self)
        await super().cleanup()

    def progress_bar(self, value, minimum, maximum, width=10) -> str:
        """
        Build a text progress bar representing `value` between `minimum` and `maximum`.
        """
        emojis = self.bot.config.emojis

        proportion = (value - minimum) / (maximum - minimum)
        sections = min(max(int(proportion * width), 0), width)

        bar = []
        # Starting segment
        bar.append(str(emojis.progress_left_empty) if sections == 0 else str(emojis.progress_left_full))

        # Full segments up to transition or end
        if sections >= 2:
            bar.append(str(emojis.progress_middle_full) * (sections - 2))

        # Transition, if required
        if 1 < sections < width:
            bar.append(str(emojis.progress_middle_transition))

        # Empty sections up to end
        if sections < width:
            bar.append(str(emojis.progress_middle_empty) * (width - max(sections, 1) - 1))

        # End section
        bar.append(str(emojis.progress_right_empty) if sections < width else str(emojis.progress_right_full))

        # Join all the sections together and return
        return ''.join(bar)

    @log_wrap(action='refresh ui loop')
    async def _refresh_loop(self):
        while True:
            try:
                await asyncio.sleep(5)
                await self._wakeup.wait()
                self._wakeup.clear()
                await self.refresh()
            except asyncio.CancelledError:
                break

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        errored = bool(self.error)
        if errored:
            waiting_emoji = self.bot.config.emojis.cancel
            title = t(_p(
                'ui:refresh_ranks|embed|title:errored',
                "Could not refresh the server ranks!"
            ))
            colour = discord.Colour.brand_red()
        else:
            waiting_emoji = self.bot.config.emojis.loading
            if self.done:
                title = t(_p(
                    'ui:refresh_ranks|embed|title:done',
                    "Rank refresh complete!"
                ))
                colour = discord.Colour.brand_green()
            else:
                title = t(_p(
                    'ui:refresh_ranks|embed|title:working',
                    "Refreshing your server ranks, please wait."
                ))
                colour = discord.Colour.orange()

        embed = discord.Embed(
            colour=colour,
            title=title,
            timestamp=utc_now()
        )

        lines = []
        stop_here = False

        if not stop_here:
            stage = self.stage_ranks
            emoji = self.bot.config.emojis.tick if stage else waiting_emoji
            text = t(_p(
                'ui:refresh_ranks|embed|line:ranks',
                "**Loading server ranks:** {emoji}"
            )).format(emoji=emoji)
            lines.append(text)
            stop_here = not bool(stage)

        if not stop_here:
            stage = self.stage_members
            emoji = self.bot.config.emojis.tick if stage else waiting_emoji
            text = t(_p(
                'ui:refresh_ranks|embed|line:members',
                "**Loading server members:** {emoji}"
            )).format(emoji=emoji)
            lines.append(text)
            stop_here = not bool(stage)

        if not stop_here:
            stage = self.stage_roles
            emoji = self.bot.config.emojis.tick if stage else waiting_emoji
            text = t(_p(
                'ui:refresh_ranks|embed|line:roles',
                "**Loading rank roles:** {emoji}"
            )).format(emoji=emoji)
            lines.append(text)
            stop_here = not bool(stage)

        if not stop_here:
            stage = self.stage_compute
            emoji = self.bot.config.emojis.tick if stage else waiting_emoji
            text = t(_p(
                'ui:refresh_ranks|embed|line:compute',
                "**Computing correct ranks:** {emoji}"
            )).format(emoji=emoji)
            lines.append(text)
            stop_here = not bool(stage)

        if not stop_here:
            lines.append("")
            if self.to_remove > self.removed and not errored:
                # Still have members to remove, show loading bar
                name = t(_p(
                    'ui:refresh_ranks|embed|field:remove|name',
                    "Removing invalid rank roles from members"
                ))
                value = t(_p(
                    'ui:refresh_ranks|embed|field:remove|value',
                    "{progress} {done}/{total} removed"
                )).format(
                    progress=self.progress_bar(self.removed, 0, self.to_remove),
                    total=self.to_remove,
                    done=self.removed,
                )
                embed.add_field(name=name, value=value, inline=False)
            else:
                emoji = self.bot.config.emojis.tick
                text = t(_p(
                    'ui:refresh_ranks|embed|line:remove',
                     "**Removed invalid ranks:** {done}/{target}"
                 )).format(done=self.removed, target=self.to_remove)
                lines.append(text)

            if self.to_add > self.added and not errored:
                # Still have members to add, show loading bar
                name = t(_p(
                    'ui:refresh_ranks|embed|field:add|name',
                    "Giving members their rank roles"
                ))
                value = t(_p(
                    'ui:refresh_ranks|embed|field:add|value',
                    "{progress} {done}/{total} given"
                )).format(
                    progress=self.progress_bar(self.added, 0, self.to_add),
                    total=self.to_add,
                    done=self.added,
                )
                embed.add_field(name=name, value=value, inline=False)
            else:
                emoji = self.bot.config.emojis.tick
                text = t(_p(
                    'ui:refresh_ranks|embed|line:add',
                     "**Updated member ranks:** {done}/{target}"
                 )).format(done=self.added, target=self.to_add)
                lines.append(text)

        embed.description = '\n'.join(lines)
        if self.errors:
            name = (
                'ui:refresh_ranks|embed|field:errors|title',
                "Issues"
            )
            value = '\n'.join(self.errors)
            embed.add_field(name=name, value=value, inline=False)
        if self.error:
            name = (
                'ui:refresh_ranks|embed|field:critical|title',
                "Critical Error! Cannot complete refresh"
            )
            embed.add_field(name=name, value=self.error, inline=False)
            
        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        pass

    async def reload(self):
        pass

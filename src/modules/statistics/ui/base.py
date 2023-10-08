from typing import Optional
from enum import IntEnum
import asyncio
import gc

import discord
from discord.ui.button import ButtonStyle, button, Button
from discord.ui.text_input import TextInput, TextStyle
from discord.ui.select import select, Select, SelectOption

from meta import LionBot, LionCog, conf
from meta.errors import UserInputError
from utils.lib import MessageArgs
from utils.ui import LeoUI, ModalRetryUI, FastModal, error_handler_for
from babel.translator import ctx_translator
from gui.cards import ProfileCard, StatsCard

from ..graphics.stats import get_stats_card
from ..data import StatsData
from .. import babel

_p = babel._p


class StatsUI(LeoUI):
    def __init__(self, bot, user, guild, **kwargs):
        super().__init__(**kwargs)
        self.bot: LionBot = bot
        self.user: discord.User | discord.Member = user
        self.guild: Optional[discord.Guild] = guild

        # State
        self._showing_global = self.guild is None
        self._refresh_lock = asyncio.Lock()

        # Original interaction, response is used to display UI
        self._original: Optional[discord.Interaction] = None

    @property
    def guildid(self) -> Optional[int]:
        """
        ID of guild to render stats for, or None if global.
        """
        return self.guild.id if self.guild and not self._showing_global else None

    @property
    def userid(self) -> int:
        """
        ID of user to render stats for.
        """
        return self.user.id

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.user.id

    async def cleanup(self):
        if self._original and not self._original.is_expired():
            try:
                await self._original.edit_original_response(view=None)
            except discord.HTTPException:
                pass
            self._original = None

    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def close_button(self, press: discord.Interaction, pressed: Button):
        """
        Delete the output message and close the UI.
        """
        await press.response.defer()
        if self._original and not self._original.is_expired():
            await self._original.delete_original_response()
        self._original = None
        await self.close()

    async def close_button_refresh(self):
        pass

    async def refresh_components(self):
        raise NotImplementedError

    async def reload(self):
        raise NotImplementedError

    async def make_message(self) -> MessageArgs:
        raise NotImplementedError

    async def redraw(self, thinking: Optional[discord.Interaction] = None):
        """
        Redraw the UI.

        If a thinking interaction is provided,
        deletes the response while redrawing.
        """
        args = await self.make_message()
        if thinking is not None and not thinking.is_expired() and thinking.response.is_done():
            asyncio.create_task(thinking.delete_original_response())
        if self._original and not self._original.is_expired():
            await self._original.edit_original_response(**args.edit_args, view=self)
        else:
            await self.close()

    async def refresh(self, thinking: Optional[discord.Interaction] = None):
        """
        Refresh the UI.
        """
        async with self._refresh_lock:
            await self.reload()
            await self.refresh_components()
            await self.redraw(thinking=thinking)

    async def run(self, interaction: discord.Interaction):
        """
        Execute the UI using the given interaction.
        """
        raise NotImplementedError

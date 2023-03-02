from typing import Optional
from enum import IntEnum
import asyncio

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

from .base import StatsUI

_p = babel._p


class ProfileEditor(FastModal):
    limit = 5

    editor = TextInput(
        label='',
        style=TextStyle.long,
        max_length=100,
        required=False
    )

    def setup_editor(self):
        t = ctx_translator.get().t
        self.editor.label = t(_p(
            'modal:profile_editor|field:editor|label', "Profile Tags (One line per tag)"
        ))
        self.editor.placeholder = t(_p(
            'modal:profile_editor|field:editor|placeholder',
            "Mathematician\n"
            "Loves Cats"
        ))

    def setup(self):
        t = ctx_translator.get().t
        self.title = t(_p(
            'modal:profile_editor|title',
            "Profile Tag Editor"
        ))
        self.setup_editor()

    def __init__(self, **kwargs):
        self.setup()
        super().__init__(**kwargs)

    async def parse(self):
        new_tags = (tag.strip() for tag in self.editor.value.splitlines())
        new_tags = [tag for tag in new_tags if tag]

        # Validate tags
        if len(new_tags) > ProfileEditor.limit:
            t = ctx_translator.get().t
            raise UserInputError(
                t(_p(
                    'modal:profile_editor|error:too_many_tags',
                    "Too many tags! You can have at most `{limit}` profile tags."
                )).format(limit=ProfileEditor.limit)
            )
        # TODO: Per tag length validation
        return new_tags

    @error_handler_for(UserInputError)
    async def rerequest(self, interaction: discord.Interaction, error: UserInputError):
        await ModalRetryUI(self, error.msg).respond_to(interaction)


class StatType(IntEnum):
    VOICE = 0
    TEXT = 1
    ANKI = 2

    def select_name(self):
        if self is self.VOICE:
            # TODO: Handle study and general modes
            name = _p(
                'menu:stat_type|opt:voice|name',
                "Voice Statistics"
            )
        elif self is self.TEXT:
            name = _p(
                'menu:stat_type|opt:text|name',
                "Text Statistics"
            )
        elif self is self.ANKI:
            name = _p(
                'menu:stat_type|opt:anki|name',
                "Anki Statistics"
            )
        return name


class ProfileUI(StatsUI):
    def __init__(self, bot, user, guild, **kwargs):
        super().__init__(bot, user, guild, **kwargs)

        # State
        self._stat_type = StatType.VOICE
        self._showing_stats = False

        # Card data for rendering
        self._profile_card: Optional[ProfileCard] = None
        self._xp_card = None
        self._stats_card: Optional[StatsCard] = None
        self._stats_future: Optional[asyncio.Future] = None

    @select(placeholder="...")
    async def type_menu(self, selection: discord.Interaction, menu: Select):
        value = int(menu.values[0])
        if self._stat_type != value:
            await selection.response.defer(thinking=True, ephemeral=True)
            self._stat_type = StatType(value)

            # Clear card state for reload
            self._stats_card = None
            if self._stats_future is not None and not self._stats_future.done():
                self._stats_future.cancel()
                self._stats_future = None

            await self.refresh(thinking=selection)
        else:
            await selection.response.defer()

    async def type_menu_refresh(self):
        # TODO: Check enabled types
        t = self.bot.translator.t
        options = []
        for item in StatType:
            option = SelectOption(label=t(item.select_name()), value=str(item.value))
            option.default = item is self._stat_type
            options.append(option)
        self.type_menu.options = options

    @button(label="Edit Profile", style=ButtonStyle.blurple)
    async def edit_button(self, press: discord.Interaction, pressed: Button):
        """
        Press to open the profile tag editor.

        Opens a ProfileEditor modal with error-rerun handling.
        """
        t = self.bot.translator.t
        data: StatsData = self.bot.get_cog('StatsCog').data

        tags = await data.ProfileTag.fetch_tags(self.guildid, self.userid)

        modal = ProfileEditor()
        modal.editor.default = '\n'.join(tags)

        @modal.submit_callback()
        async def parse_tags(interaction: discord.Interaction):
            new_tags = await modal.parse()
            await interaction.response.defer(thinking=True, ephemeral=True)

            # Set the new tags and refresh
            await data.ProfileTag.set_tags(self.guildid, self.userid, new_tags)
            if self._original is not None:
                self._profile_card = None
                await self.refresh(thinking=interaction)
            else:
                # Corner case where the UI has expired or been closed
                embed = discord.Embed(
                    colour=discord.Colour.brand_green(),
                    description=t(_p(
                        'modal:profile_editor|resp:success',
                        "Your profile has been updated!"
                    ))
                )
                await interaction.edit_original_response(embed=embed)
        await press.response.send_modal(modal)

    async def edit_button_refresh(self):
        ...

    @button(label="Show Statistics", style=ButtonStyle.blurple)
    async def stats_button(self, press: discord.Interaction, pressed: Button):
        """
        Press to show or hide the statistics panel.
        """
        self._showing_stats = not self._showing_stats
        if self._stats_card or not self._showing_stats:
            await press.response.defer()
            await self.refresh()
        else:
            await press.response.defer(thinking=True, ephemeral=True)
            await self.refresh(thinking=press)

    async def stats_button_refresh(self):
        button = self.stats_button

        if self._showing_stats:
            button.label = "Hide Statistics"
        else:
            button.label = "Show Statistics"

    @button(label="Global Stats", style=ButtonStyle.blurple)
    async def global_button(self, press: discord.Interaction, pressed: Button):
        """
        Switch between local and global statistics modes.

        This is only displayed when statistics are shown.
        Also saves the value to user preferences.
        """
        await press.response.defer(thinking=True, ephemeral=True)
        self._showing_global = not self._showing_global
        # TODO: Asynchronously update user preferences

        # Clear card state for reload
        self._stats_card = None
        if self._stats_future is not None and not self._stats_future.done():
            self._stats_future.cancel()
            self._stats_future = None

        await self.refresh(thinking=press if not self._showing_global else None)

        if self._showing_global:
            t = self.bot.translator.t
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                description=t(_p(
                    'ui:Profile|button:global|resp:success',
                    "You will now see statistics from all you servers (where applicable)! Press again to revert."
                ))
            )
            await press.edit_original_response(embed=embed)

    async def global_button_refresh(self):
        button = self.global_button

        if self._showing_global:
            button.label = "Server Statistics"
        else:
            button.label = "Global Statistics"

    async def refresh_components(self):
        """
        Refresh each UI component, and the overall layout.
        """
        await asyncio.gather(
            self.edit_button_refresh(),
            self.global_button_refresh(),
            self.stats_button_refresh(),
            self.close_button_refresh(),
            self.type_menu_refresh()
        )
        if self._showing_stats:
            self._layout = [
                (self.type_menu,),
                (self.stats_button, self.global_button, self.edit_button, self.close_button)
            ]
        else:
            self._layout = [
                (self.stats_button, self.edit_button, self.close_button)
            ]

    async def _render_stats(self):
        """
        Create and render the profile card.
        """
        card = await get_stats_card(self.bot, self.userid, self.guildid)
        await card.render()
        self._stats_card = card
        return card

    async def _render_profile(self):
        """
        Create and render the XP and stats cards.
        """
        args = await ProfileCard.sample_args(None)
        data: StatsData = self.bot.get_cog('StatsCog').data
        args |= {'badges': await data.ProfileTag.fetch_tags(self.guildid, self.userid)}
        card = ProfileCard(**args)
        await card.render()
        self._profile_card = card
        return card

    async def reload(self):
        """
        Reload the UI data, applying cache where possible.
        """
        # Render the cards if required
        tasks = []
        if self._profile_card is None:
            profile_task = asyncio.create_task(self._render_profile())
            tasks.append(profile_task)
        if self._stats_card is None:
            if self._stats_future is None or self._stats_future.done() or self._stats_future.cancelled():
                self._stats_future = asyncio.create_task(self._render_stats())
            if self._showing_stats:
                tasks.append(self._stats_future)
        if tasks:
            await asyncio.gather(*tasks)

    async def make_message(self) -> MessageArgs:
        """
        Make the message arguments. Apply cache where possible.
        """
        # Build the final message arguments
        files = []
        files.append(self._profile_card.as_file('profile.png'))
        if self._showing_stats:
            files.append(self._stats_card.as_file('stats.png'))
        return MessageArgs(files=files)

    async def run(self, interaction: discord.Interaction):
        """
        Execute the UI using the given interaction.
        """
        self._original = interaction

        # TODO: Switch to using data cache in reload
        self._showing_global = False

        await self.refresh()

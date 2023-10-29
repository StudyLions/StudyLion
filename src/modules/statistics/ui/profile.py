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
from gui.base import CardMode

from ..graphics.stats import get_stats_card
from ..graphics.profile import get_profile_card
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

    @property
    def card_mode(self):
        # TODO: Need to support VOICE separately from STUDY
        if self is self.VOICE:
            return CardMode.VOICE
        elif self is self.TEXT:
            return CardMode.TEXT
        elif self is self.ANKI:
            return CardMode.ANKI


class ProfileUI(StatsUI):
    def __init__(self, bot, user, guild, **kwargs):
        super().__init__(bot, user, guild, **kwargs)

        # State
        self._stat_type = StatType.VOICE
        self._showing_stats = False
        self._stat_message = None

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

        tags = await data.ProfileTag.fetch_tags(self.guild.id, self.userid)

        modal = ProfileEditor()
        modal.editor.default = '\n'.join(tags)

        @modal.submit_callback()
        async def parse_tags(interaction: discord.Interaction):
            new_tags = await modal.parse()
            await interaction.response.defer(thinking=True, ephemeral=True)

            # Set the new tags and refresh
            await data.ProfileTag.set_tags(self.guild.id, self.userid, new_tags)
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
        t = self.bot.translator.t
        self.edit_button.label = t(_p(
            'ui:profile_card|button:edit|label',
            "Edit Profile Badges"
        ))

    @button(label="Show Statistics", style=ButtonStyle.blurple)
    async def stats_button(self, press: discord.Interaction, pressed: Button):
        """
        Press to show or hide the statistics panel.
        """
        self._showing_stats = not self._showing_stats
        await press.response.defer(thinking=True, ephemeral=True)
        await self.refresh(thinking=press)

    async def stats_button_refresh(self):
        button = self.stats_button
        t = self.bot.translator.t

        if self._showing_stats:
            button.label = t(_p(
                'ui:profile_card|button:statistics|label:hide',
                "Hide Statistics"
            ))
        else:
            button.label = t(_p(
                'ui:profile_card|button:statistics|label:show',
                "Show Statistics"
            ))

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

    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def close_button(self, press: discord.Interaction, pressed: Button):
        """
        Delete the output message and close the UI.
        """
        await press.response.defer()
        await self._original.delete_original_response()
        if self._stat_message is not None:
            await self._stat_message.delete()
            self._stat_message = None
        self._original = None
        await self.close()

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

        voting = self.bot.get_cog('TopggCog')
        if voting and not await voting.check_voted_recently(self.userid):
            premiumcog = self.bot.get_cog('PremiumCog')
            if not (premiumcog and await premiumcog.is_premium_guild(self.guild.id)):
                self._layout.append((voting.vote_button(),))

    async def _render_stats(self):
        """
        Create and render the profile card.
        """
        card = await get_stats_card(self.bot, self.userid, self.guildid, self._stat_type.card_mode)
        await card.render()
        self._stats_card = card
        return card

    async def _render_profile(self):
        """
        Create and render the XP and stats cards.
        """
        card = await get_profile_card(self.bot, self.userid, self.guild.id)
        if card:
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

    async def redraw(self, thinking: Optional[discord.Interaction] = None):
        """
        Redraw the UI.

        If a thinking interaction is provided,
        deletes the response while redrawing.
        """
        profile_args, stat_args = await self.make_message()
        if thinking is not None and not thinking.is_expired() and thinking.response.is_done():
            asyncio.create_task(thinking.delete_original_response())
        if stat_args is not None:
            send_task = asyncio.create_task(self._original.edit_original_response(**profile_args.edit_args, view=None))
            if self._stat_message is None:
                self._stat_message = await self._original.followup.send(**stat_args.send_args, view=self)
            else:
                await self._stat_message.edit(**stat_args.edit_args, view=self)
        else:
            send_task = asyncio.create_task(self._original.edit_original_response(**profile_args.edit_args, view=self))
            if self._stat_message is not None:
                await self._stat_message.delete()
                self._stat_message = None
        await send_task

    async def make_message(self) -> MessageArgs:
        """
        Make the message arguments. Apply cache where possible.
        """
        profile_args = MessageArgs(file=self._profile_card.as_file('profile.png'))
        if self._showing_stats:
            stats_args = MessageArgs(file=self._stats_card.as_file('stats.png'))
        else:
            stats_args = None
        return (profile_args, stats_args)

    async def run(self, interaction: discord.Interaction):
        """
        Execute the UI using the given interaction.
        """
        self._original = interaction

        # TODO: Switch to using data cache in reload
        self._showing_global = False

        await self.refresh()

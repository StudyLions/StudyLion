from typing import Optional, TYPE_CHECKING
import asyncio

import discord
from discord.ui.button import button, Button, ButtonStyle

from meta import conf, LionBot
from meta.errors import UserInputError
from utils.lib import utc_now
from utils.ui import LeoUI
from babel.translator import ctx_locale

from .. import babel, logger
from ..lib import slotid_to_utc, time_to_slotid

from .scheduleui import ScheduleUI

if TYPE_CHECKING:
    from ..cog import ScheduleCog

_p = babel._p


class SessionUI(LeoUI):
    # Maybe add a button to check channel permissions
    # And make the session update the channel if it is missing permissions

    def __init__(self, bot: LionBot, slotid: int, guildid: int, **kwargs):
        kwargs.setdefault('timeout', 3600)
        super().__init__(**kwargs)
        self.bot = bot
        self.cog: 'ScheduleCog' = bot.get_cog('ScheduleCog')
        self.slotid = slotid
        self.slot_start = slotid_to_utc(slotid)
        self.guildid = guildid
        self.locale = None

    @property
    def starting_soon(self):
        return (self.slot_start - utc_now()).total_seconds() < 60

    async def init_components(self):
        """
        Localise components.
        """
        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        locale = self.locale = lguild.locale
        t = self.bot.translator.t

        self.book_button.label = t(_p(
            'ui:sessionui|button:book|label',
            "Book"
        ), locale)
        self.cancel_button.label = t(_p(
            'ui:sessionui|button:cancel|label',
            "Cancel"
        ), locale)
        self.schedule_button.label = t(_p(
            'ui:sessionui|button:schedule|label',
            'Open Schedule'
        ), locale)

    # ----- API -----
    async def reload(self):
        await self.init_components()
        if self.starting_soon:
            # Slot is about to start or slot has already started
            self.set_layout((self.schedule_button,))
        else:
            self.set_layout(
                (self.book_button, self.cancel_button, self.schedule_button),
            )

    # ----- UI Components -----
    @button(label='BOOK_PLACEHOLDER', style=ButtonStyle.blurple)
    async def book_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t
        babel = self.bot.get_cog('BabelCog')
        locale = await babel.get_user_locale(press.user.id)
        ctx_locale.set(locale)

        error = None
        if self.starting_soon:
            error = t(_p(
                'ui:session|button:book|error:starting_soon',
                "Too late! This session has started or is starting shortly."
            ))
        else:
            schedule = await self.cog._fetch_schedule(press.user.id)
            if self.slotid in schedule:
                error = t(_p(
                    'ui:session|button:book|error:already_booked',
                    "You are already a member of this session!"
                ))
            else:
                try:
                    await self.cog.create_booking(self.guildid, press.user.id, self.slotid)
                    ack = t(_p(
                        'ui:session|button:book|success',
                        "Successfully booked this session."
                    ))
                    embed = discord.Embed(
                        colour=discord.Colour.brand_green(),
                        description=ack
                    )
                except UserInputError as e:
                    error = e.msg
        if error is not None:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=error,
                title=t(_p(
                    'ui:session|button:book|error|title',
                    "Could not book session"
                ))
            )

        await press.edit_original_response(embed=embed)

    @button(label='CANCEL_PLACHEHOLDER', style=ButtonStyle.blurple)
    async def cancel_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t
        babel = self.bot.get_cog('BabelCog')
        locale = await babel.get_user_locale(press.user.id)
        ctx_locale.set(locale)

        error = None
        if self.starting_soon:
            error = t(_p(
                'ui:session|button:cancel|error:starting_soon',
                "Too late! This session has started or is starting shortly."
            ))
        else:
            schedule = await self.cog._fetch_schedule(press.user.id)
            if self.slotid not in schedule:
                error = t(_p(
                    'ui:session|button:cancel|error:not_booked',
                    "You are not a member of this session!"
                ))
            else:
                try:
                    await self.cog.cancel_bookings(
                        (self.slotid, self.guildid, press.user.id),
                        refund=True
                    )
                    ack = t(_p(
                        'ui:session|button:cancel|success',
                        "Successfully cancelled this session."
                    ))
                    embed = discord.Embed(
                        colour=discord.Colour.brand_green(),
                        description=ack
                    )
                except UserInputError as e:
                    error = e.msg
        if error is not None:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description=error,
                title=t(_p(
                    'ui:session|button:cancel|error|title',
                    "Could not cancel session"
                ))
            )

        await press.edit_original_response(embed=embed)

    @button(label='SCHEDULE_PLACEHOLDER', style=ButtonStyle.blurple)
    async def schedule_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)

        babel = self.bot.get_cog('BabelCog')
        locale = await babel.get_user_locale(press.user.id)
        ctx_locale.set(locale)

        ui = ScheduleUI(self.bot, press.guild, press.user.id)
        await ui.run(press)
        await ui.wait()

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

_p, _np = babel._p, babel._np


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
        self.help_button.label = t(_p(
            'ui:sessionui|button:help|label',
            "How to Attend"
        ))

    # ----- API -----
    async def reload(self):
        await self.init_components()
        if self.starting_soon:
            # Slot is about to start or slot has already started
            self.set_layout((self.schedule_button, self.help_button))
        else:
            self.set_layout(
                (self.book_button, self.cancel_button,),
                (self.schedule_button, self.help_button,),
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

    @button(label='HELP_PLACEHOLDER', style=ButtonStyle.grey, emoji=conf.emojis.question)
    async def help_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t
        babel = self.bot.get_cog('BabelCog')
        locale = await babel.get_user_locale(press.user.id)
        ctx_locale.set(locale)

        schedule = await self.cog._fetch_schedule(press.user.id)
        if self.slotid not in schedule:
            # Tell them how to book
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                title=t(_p(
                    'ui:session|button:help|embed:unbooked|title',
                    'You have not booked this session!'
                )),
                description=t(_p(
                    'ui:session|button:help|embed:unbooked|description',
                    "You need to book this scheduled session before you can attend it! "
                    "Press the **{book_label}** button to book the session."
                )).format(book_label=self.book_button.label),
            )
        else:
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                title=t(_p(
                    'ui:session|button:help|embed:help|title',
                    "How to attend your scheduled session"
                ))
            )
            config = await self.cog.get_config(self.guildid)

            # Get required duration, and format it
            duration = config.min_attendance.value
            durstring = t(_np(
                'ui:session|button:help|embed:help|minimum_attendance',
                "at least one minute",
                "at least `{duration}` minutes",
                duration
            )).format(duration=duration)

            # Get session room
            room = config.session_room.value

            if room is None:
                room_line = ''
            elif room.type is discord.enums.ChannelType.category:
                room_line = t(_p(
                    'ui:session|button:help|embed:help|room_line:category',
                    "The exclusive scheduled session category **{category}** "
                    "will also be open to you during your scheduled session."
                )).format(category=room.name)
            else:
                room_line = t(_p(
                    'ui:session|button:help|embed:help|room_line:voice',
                    "The exclusive scheduled session room {room} "
                    "will also be open to you during your scheduled session."
                )).format(room=room.mention)

            # Get valid session channels, if set
            channels = (await self.cog.settings.SessionChannels.get(self.guildid)).value

            attend_args = dict(
                minimum=durstring,
                start=discord.utils.format_dt(slotid_to_utc(self.slotid), 't'),
                end=discord.utils.format_dt(slotid_to_utc(self.slotid + 3600), 't'),
            )

            if room is not None and len(channels) == 1 and channels[0].id == room.id:
                # Special case where session room is the only allowed channel/category
                room_line = ''
                if room.type is discord.enums.ChannelType.category:
                    attend_line = t(_p(
                        'ui:session|button:help|embed:help|attend_line:only_room_category',
                        "To attend your scheduled session, "
                        "join a voice channel in **{room}** for **{minimum}** "
                        "between {start} and {end}."
                    )).format(
                        **attend_args,
                        room=room.name
                    )
                else:
                    attend_line = t(_p(
                        'ui:session|button:help|embed:help|attend_line:only_room_channel',
                        "To attend your scheduled session, "
                        "join {room} for **{minimum}** "
                        "between {start} and {end}."
                    )).format(
                        **attend_args,
                        room=room.mention
                    )
            elif channels:
                attend_line = t(_p(
                    'ui:session|button:help|embed:help|attend_line:with_channels',
                    "To attend your scheduled session, join a valid session voice channel for **{minimum}** "
                    "between {start} and {end}."
                )).format(**attend_args)
                channel_string = ', '.join(
                    f"**{channel.name}**" if (channel.type == discord.enums.ChannelType.category) else channel.mention
                    for channel in channels
                )
                embed.add_field(
                    name=t(_p(
                        'ui:session|button:help|embed:help|field:channels|name',
                        "Valid session channels"
                    )),
                    value=channel_string[:1024],
                    inline=False
                )
            else:
                attend_line = t(_p(
                    'ui:session|button:help|embed:help|attend_line:all_channels',
                    "To attend your scheduled session, join any tracked voice channel "
                    "for **{minimum}** between {start} and {end}."
                )).format(**attend_args)

            embed.description = '\n'.join((attend_line, room_line))
            embed.add_field(
                name=t(_p(
                    'ui:session|button:help|embed:help|field:rewards|name',
                    "Rewards"
                )),
                value=t(_p(
                    'ui:session|button:help|embed:help|field:rewards|value',
                    "Everyone who attends the session will be rewarded with {coin}**{reward}**.\n"
                    "If *everyone* successfully attends, you will also be awarded a bonus of {coin}**{bonus}**.\n"
                    "Anyone who does *not* attend their booked session will have the rest of their schedule cancelled "
                    "**without refund**, so beware!"
                )).format(
                    coin=conf.emojis.coin,
                    reward=config.attendance_reward.value,
                    bonus=config.attendance_bonus.value,
                ),
                inline=False
            )
        await press.edit_original_response(embed=embed)

from typing import Optional, TYPE_CHECKING
import asyncio
import math

import discord
from discord.ui.select import select, Select, SelectOption
from discord.ui.button import button, Button, ButtonStyle

from meta import conf, LionBot
from meta.errors import UserInputError
from data import ORDER

from utils.ui import MessageUI, Confirm
from utils.lib import MessageArgs, utc_now, tabulate, error_embed
from babel.translator import ctx_translator

from .. import babel, logger
from ..data import ScheduleData
from ..lib import slotid_to_utc, time_to_slotid
from ..settings import ScheduleConfig, ScheduleSettings

_p, _np = babel._p, babel._np

if TYPE_CHECKING:
    from ..cog import ScheduleCog
    from core.lion_member import LionMember


guide = _p(
    'ui:schedule|about',
    "Guide tips here TBD"
)


class ScheduleUI(MessageUI):
    """
    Primary UI pathway for viewing and modifying a member's schedule.
    """

    def __init__(self, bot: LionBot, guild: discord.Guild, callerid: int, **kwargs):
        super().__init__(callerid=callerid, **kwargs)
        self.bot = bot
        self.cog: ScheduleCog = bot.get_cog('ScheduleCog')
        self.guild = guild

        self.guildid = guild.id
        self.userid = callerid
        self.lion: LionMember = None

        # Data state
        self.config: ScheduleConfig = None
        self.blacklisted = False
        self.schedule = {}  # ordered map slotid -> ScheduleSessionMember
        self.guilds = {}  # Cache of guildid -> ScheduleGuild

        # Statistics
        self.recent_stats = (0, 0)
        self.recent_avg = 0
        self.all_stats = (0, 0)
        self.all_avg = 0

        self.streak = 0

        # UI state
        self.show_info = False
        self.initial_load = False
        self.now = utc_now()
        self.nowid = time_to_slotid(self.now)

    # ----- API -----

    # ----- UI Components -----
    # IDEA: History button?

    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        """
        Quit the schedule
        """
        await press.response.defer()
        await self.quit()

    @button(emoji=conf.emojis.refresh, style=ButtonStyle.grey)
    async def refresh_button(self, press: discord.Interaction, pressed: Button):
        """
        Refresh the schedule
        """
        await press.response.defer(thinking=True, ephemeral=True)
        self.show_info = False
        self.initial_load = False
        await self.refresh(thinking=press)

    @button(label='CLEAR_PLACEHOLDER', style=ButtonStyle.red)
    async def clear_button(self, press: discord.Interaction, pressed: Button):
        """
        Clear future sessions for this user.
        """
        await press.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t

        # First update the schedule
        now = self.now = utc_now()
        nowid = self.nowid = time_to_slotid(now)
        nextid = nowid + 3600
        await self._load_schedule()
        slotids = set(self.schedule.keys())

        # Remove uncancellable slots
        slotids.discard(nowid)
        if (slotid_to_utc(nextid) - now).total_seconds() < 60:
            slotids.discard(nextid)
        if not slotids:
            # Nothing to cancel
            error = t(_p(
                'ui:schedule|button:clear|error:nothing',
                "No upcoming sessions to cancel! Your schedule is already clear."
            ))
            embed = error_embed(error)
        else:
            # Do cancel
            await self.cog.cancel_bookings(
                *(
                    (slotid, self.schedule[slotid].guildid, self.userid)
                    for slotid in slotids
                )
            )
            ack = t(_p(
                'ui:schedule|button:clear|success',
                "Successfully cancelled and refunded your upcoming scheduled sessions."
            ))
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=ack
            )
        await press.edit_original_response(embed=embed)
        self.show_info = False
        await self.refresh()

    async def clear_button_refresh(self):
        self.clear_button.label = self.bot.translator.t(_p(
            'ui:schedule|button:clear|label',
            "Clear Schedule"
        ))
        self.clear_button.disabled = (not self.schedule)

    @button(label='ABOUT_PLACEHOLDER', emoji=conf.emojis.question, style=ButtonStyle.grey)
    async def about_button(self, press: discord.Interaction, pressed: Button):
        """
        Replace message with the info page (temporarily).
        """
        await press.response.defer(thinking=True, ephemeral=True)
        self.show_info = not self.show_info
        await self.refresh(thinking=press)

    async def about_button_refresh(self):
        self.about_button.label = self.bot.translator.t(_p(
            'ui:schedule|button:about|label',
            "About Schedule"
        ))
        self.about_button.style = ButtonStyle.grey if self.show_info else ButtonStyle.blurple

    @select(cls=Select, placeholder='BOOK_MENU_PLACEHOLDER')
    async def booking_menu(self, selection: discord.Interaction, selected):
        if selected.values[0] == 'None':
            await selection.response.defer()
            return

        await selection.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t

        # Refresh the schedule
        now = self.now = utc_now()
        nowid = self.nowid = time_to_slotid(now)
        nextid = nowid + 3600
        next_soon = ((slotid_to_utc(nextid) - now).total_seconds() < 60)
        await self._load_schedule()

        # Check the requested slots
        slotids = set(map(int, selected.values))
        if nowid in slotids:
            # Error with cannot book now
            error = t(_p(
                'ui:schedule|menu:booking|error:current_slot',
                "You cannot schedule a currently running session!"
            ))
            embed = error_embed(error)
        elif (nextid in slotids) and next_soon:
            # Error with too late
            error = t(_p(
                'ui:schedule|menu:booking|error:next_slot',
                "Too late! You cannot schedule a session starting in the next minute."
            ))
            embed = error_embed(error)
        elif slotids.intersection(self.schedule.keys()):
            # Error with already booked
            error = t(_p(
                'ui:schedule|menu:booking|error:already_booked',
                "You have already booked one or more of the requested sessions!"
            ))
            embed = error_embed(error)
        else:
            # Okay, slotids are valid.
            # Check member balance is sufficient
            await self.lion.data.refresh()
            balance = self.lion.data.coins
            requested = len(slotids)
            required = requested * self.config.get(ScheduleSettings.ScheduleCost.setting_id).value
            if required > balance:
                error = t(_p(
                    'ui:schedule|menu:booking|error:insufficient_balance',
                    "Booking `{count}` scheduled sessions requires {coin}**{required}**, "
                    "but you only have {coin}**{balance}**!"
                )).format(
                    count=requested, coin=conf.emojis.coin, required=required, balance=balance
                )
                embed = error_embed(error)
            else:
                # Everything checks out, run the booking
                try:
                    await self.cog.create_booking(self.guildid, self.userid, *slotids)
                    timestrings = [
                        discord.utils.format_dt(slotid_to_utc(slotid), style='f')
                        for slotid in slotids
                    ]
                    ack = t(_np(
                        'ui:schedule|menu:booking|success',
                        "Successfully booked your scheduled session at {times}.",
                        "Successfully booked the following scheduled sessions.\n{times}",
                        len(slotids)
                    )).format(
                        times='\n'.join(timestrings)
                    )
                    embed = discord.Embed(
                        colour=discord.Colour.brand_green(),
                        description=ack
                    )
                except UserInputError as e:
                    embed = error_embed(e.msg)
        await selection.edit_original_response(embed=embed)
        self.show_info = False
        await self.refresh()

    async def booking_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.booking_menu

        if self.blacklisted:
            placeholder = t(_p(
                'ui:schedule|menu:booking|placeholder:blacklisted',
                "Book Sessions (Cannot book - Blacklisted)"
            ))
            disabled = True
            options = []
        else:
            disabled = False
            placeholder = t(_p(
                'ui:schedule|menu:booking|placeholder:regular',
                "Book Sessions ({amount} LC)"
            )).format(
                coin=conf.emojis.coin,
                amount=self.config.get(ScheduleSettings.ScheduleCost.setting_id).value
            )

            # Populate with choices
            nowid = self.nowid
            if ((slotid_to_utc(nowid + 3600) - utc_now()).total_seconds() < 60):
                # Start from next session instead
                nowid += 3600
            upcoming = [nowid + 3600 * i for i in range(1, 25)]
            upcoming = [slotid for slotid in upcoming if slotid not in self.schedule]
            options = self._format_slot_options(*upcoming)

        menu.placeholder = placeholder
        if options:
            menu.options = options
            menu.disabled = disabled
            menu.max_values = len(menu.options)
        else:
            menu.options = [
                SelectOption(label='None', value='None')
            ]
            menu.disabled = True
            menu.max_values = 1

    def _format_slot_options(self, *slotids: int) -> list[SelectOption]:
        """
        Format provided slotids into Select Options.

        ```
        Today 23:00 (in <1 hour)
        Tommorrow 01:00 (in 3 hours)
        Today/Tomorrow {start} (in 1 hour)
        ```
        """
        t = self.bot.translator.t
        options = []
        tz = self.lion.timezone
        nowid = self.nowid
        now = self.now.astimezone(tz)

        slot_format = t(_p(
            'ui:schedule|menu:slots|option|format',
            "{day} {time} ({until})"
        ))
        today_name = t(_p(
            'ui:schedule|menu:slots|option|day:today',
            "Today"
        ))
        tomorrow_name = t(_p(
            'ui:schedule|menu:slots|option|day:tomorrow',
            "Tomorrow"
        ))

        for slotid in slotids:
            slot_start = slotid_to_utc(slotid).astimezone(tz)
            distance = int((slotid - nowid) // 3600)
            until = self._format_until(distance)
            day = today_name if (slot_start.day == now.day) else tomorrow_name
            name = slot_format.format(
                day=day,
                time=slot_start.strftime('%H:%M'),
                until=until
            )

            options.append(SelectOption(label=name, value=str(slotid)))
        return options

    def _format_until(self, distance):
        t = self.bot.translator.t
        if distance:
            return t(_np(
                'ui:schedule|format_until|positive',
                "in <1 hour",
                "in {number} hours",
                distance
            )).format(number=distance)
        else:
            return t(_p(
                'ui:schedule|format_until|now',
                "right now!"
            ))

    @select(cls=Select, placeholder='CANCEL_MENU_PLACEHOLDER')
    async def cancel_menu(self, selection: discord.Interaction, selected):
        """
        Cancel the selected slotids.

        Refuses to cancel a slot if it is already running or within one minute of running.
        """
        await selection.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t

        # Collect slotids that were requested
        slotids = list(map(int, selected.values))

        # Check for 'forbidden' slotids (possible due to long running UI)
        now = utc_now()
        nowid = time_to_slotid(now)
        if nowid in slotids:
            error = t(_p(
                'ui:schedule|menu:cancel|error:current_slot',
                "You cannot cancel a currently running *scheduled* session! Please attend it if possible."
            ))
            embed = error_embed(error)
        elif (nextid := nowid + 3600) in slotids and (slotid_to_utc(nextid) - now).total_seconds() < 60:
            error = t(_p(
                'ui:schedule|menu:cancel|error:too_late',
                "Too late! You cannot cancel a scheduled session within a minute of it starting. "
                "Please attend it if possible."
            ))
            embed = error_embed(error)
        else:
            # Remaining slotids are now cancellable
            # Although there is no guarantee the bookings are still valid.
            # Request booking cancellation
            booking_records = await self.cog.cancel_bookings(
                *(
                    (slotid, self.schedule[slotid].guildid, self.userid)
                    for slotid in slotids
                )
            )
            if not booking_records:
                error = t(_p(
                    'ui:schedule|menu:cancel|error:already_cancelled',
                    "The selected bookings no longer exist! Nothing to cancel."
                ))
                embed = error_embed(error)
            else:
                timestrings = [
                    discord.utils.format_dt(slotid_to_utc(record['slotid']), style='f')
                    for record in booking_records
                ]
                ack = t(_np(
                    'ui:schedule|menu:cancel|success',
                    "Successfully cancelled and refunded your scheduled session booking for {times}.",
                    "Successfully cancelled and refunded your scheduled session bookings:\n{times}.",
                    len(booking_records)
                )).format(
                    times='\n'.join(timestrings)
                )
                embed = discord.Embed(
                    colour=discord.Colour.brand_green(),
                    description=ack
                )

        await selection.edit_original_response(embed=embed)
        self.show_info = False
        await self.refresh()

    async def cancel_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.cancel_menu

        menu.placeholder = t(_p(
            'ui:schedule|menu:cancel|placeholder',
            "Cancel booked sessions"
        ))
        minid = self.nowid
        if ((slotid_to_utc(self.nowid + 3600) - utc_now()).total_seconds() < 60):
            minid = self.nowid + 3600
        can_cancel = list(slotid for slotid in self.schedule.keys() if slotid > minid)

        menu.options = self._format_slot_options(*can_cancel)
        menu.max_values = len(menu.options)

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        # Show booking cost somewhere (in booking menu)
        # Show info automatically if member has never booked a session
        embed = discord.Embed(
            colour=discord.Colour.orange(),
        )
        member = self.lion.member
        embed.set_author(
            name=t(_p(
                'ui:schedule|embed|author',
                "Your Scheduled Sessions and Past Statistics"
            )).format(name=member.display_name if member else self.lion.luser.data.name),
            icon_url=self.lion.member.avatar
        )
        if self.show_info:
            # Info message
            embed.description = t(guide)
        else:
            # Statistics table
            stats_fields = {}
            recent_key = t(_p(
                'ui:schedule|embed|field:stats|field:recent',
                "Recent"
            ))
            recent_value = self._format_stats(*self.recent_stats, self.recent_avg)
            stats_fields[recent_key] = recent_value
            if self.recent_stats[1] == 100:
                alltime_key = t(_p(
                    'ui:schedule|embed|field:stats|field:alltime',
                    "All Time"
                ))
                alltime_value = self._format_stats(*self.all_stats, self.all_avg)
                stats_fields[alltime_key] = alltime_value
            streak_key = t(_p(
                'ui:schedule|embed|field:stats|field:streak',
                "Streak"
            ))
            if self.streak:
                streak_value = t(_np(
                    'ui:schedule|embed|field:stats|field:streak|value:zero',
                    "One session attended! Keep it up!",
                    "**{streak}** sessions attended in a row! Good job!",
                    self.streak,
                )).format(streak=self.streak)
            else:
                streak_value = t(_p(
                    'ui:schedule|embed|field:stats|field:streak|value:positive',
                    "No streak yet!"
                ))
            stats_fields[streak_key] = streak_value

            table = tabulate(*stats_fields.items())
            embed.add_field(
                name=t(_p(
                    'ui:schedule|embed|field:stats|name',
                    "Session Statistics"
                )),
                value='\n'.join(table),
                inline=False
            )

            # Upcoming sessions
            upcoming = list(self.schedule.values())
            guildids = set(row.guildid for row in upcoming)
            show_guild = (len(guildids) > 1) or (self.guildid not in guildids)

            # Split lists in about half if they are too long for one field.
            split = math.ceil(len(upcoming) / 2) if len(upcoming) >= 12 else 12
            block1 = upcoming[:split]
            block2 = upcoming[split:]

            embed.add_field(
                name=t(_p(
                    'ui:schedule|embed|field:upcoming|name',
                    "Upcoming Sessions"
                )),
                value=self._format_bookings(block1, show_guild) if block1 else t(_p(
                    'ui:schedule|embed|field:upcoming|value:empty',
                    "No sessions scheduled yet!"
                ))
            )
            if block2:
                embed.add_field(
                    name='-'*5,
                    value=self._format_bookings(block2, show_guild)
                )
        return MessageArgs(embed=embed)

    def _format_stats(self, attended, total, average):
        t = self.bot.translator.t
        return t(_p(
            'ui:schedule|embed|stats_format',
            "**{attended}** attended out of **{total}** booked.\r\n"
            "**{percent}%** attendance rate.\r\n"
            "**{average}** average attendance time."
        )).format(
            attended=attended,
            total=total,
            percent=math.ceil(attended/total * 100) if total else 0,
            average=f"{int(average // 60)}:{average % 60:02}"
        )

    def _format_bookings(self, bookings, show_guild=False):
        t = self.bot.translator.t
        short_format = t(_p(
            'ui:schedule|booking_format:short',
            "`{until}` | {start} - {end}"
        ))
        long_format = t(_p(
            'ui:schedule|booking_format:long',
            "> `{until}` | {start} - {end}"
        ))
        items = []
        format = long_format if show_guild else short_format
        last_guildid = None
        for booking in bookings:
            guildid = booking.guildid
            data = self.guilds[guildid]

            if last_guildid != guildid:
                channel = f"<#{data.lobby_channel}>"
                items.append(channel)
                last_guildid = guildid

            start = slotid_to_utc(booking.slotid)
            end = slotid_to_utc(booking.slotid + 3600)
            item = format.format(
                until=self._format_until(int((booking.slotid - self.nowid) // 3600)),
                start=discord.utils.format_dt(start, style='t'),
                end=discord.utils.format_dt(end, style='t'),
            )
            items.append(item)
        return '\n'.join(items)

    async def refresh_layout(self):
        # Don't show cancel menu or clear button if the schedule is empty
        await asyncio.gather(
            self.clear_button_refresh(),
            self.about_button_refresh(),
            self.booking_menu_refresh(),
            self.cancel_menu_refresh(),
        )
        if self.schedule and self.cancel_menu.options:
            self.set_layout(
                (self.about_button, self.refresh_button, self.clear_button, self.quit_button),
                (self.booking_menu,),
                (self.cancel_menu,),
            )
        else:
            self.set_layout(
                (self.about_button, self.refresh_button, self.quit_button),
                (self.booking_menu,)
            )

    async def reload(self):
        now = utc_now()
        nowid = time_to_slotid(now)
        self.initial_load = self.initial_load and (nowid == self.nowid)
        self.now = now
        self.nowid = nowid

        if not self.initial_load:
            await self._load_member()
            await self._load_statistics()
            self.show_info = not self.recent_stats[1]
            self.initial_load = True

        await self._load_schedule()

        member = self.guild.get_member(self.userid)
        blacklist_role = self.config.get(ScheduleSettings.BlacklistRole.setting_id).value
        self.blacklisted = member and blacklist_role and (blacklist_role in member.roles)

    async def _load_schedule(self):
        """
        Load current member schedule and update guild config cache.
        """
        nowid = self.nowid

        booking_model = self.cog.data.ScheduleSessionMember
        bookings = await booking_model.fetch_where(
            booking_model.slotid >= nowid,
            userid=self.userid,
        ).order_by('slotid', ORDER.ASC)
        guildids = list(set(booking.guildid for booking in bookings))
        guilds = await self.cog.data.ScheduleGuild.fetch_multiple(*guildids)
        self.guilds.update(guilds)
        self.schedule = {
            booking.slotid: booking for booking in bookings
        }

    async def _load_member(self):
        self.lion = await self.bot.core.lions.fetch_member(self.guildid, self.userid)
        await self.lion.data.refresh()

        guild_data = await self.cog.data.ScheduleGuild.fetch_or_create(self.guildid)
        self.guilds[self.guildid] = guild_data
        self.config = ScheduleConfig(self.guildid, guild_data)

    async def _load_statistics(self):
        now = utc_now()
        nowid = time_to_slotid(now)

        # Fetch (up to 100) most recent bookings
        booking_model = self.cog.data.ScheduleSessionMember
        recent = await booking_model.fetch_where(
            booking_model.slotid < nowid,
            userid=self.userid,
        ).order_by('slotid', ORDER.DESC).limit(100)

        # Calculate recent stats
        recent_total_clock = 0
        recent_att = 0
        recent_count = len(recent)
        streak = 0
        streak_broken = False
        for row in recent:
            recent_total_clock += row.clock
            if row.attended:
                recent_att += 1
                if not streak_broken:
                    streak += 1
            else:
                streak_broken = True

        self.recent_stats = (recent_att, recent_count)
        self.recent_avg = int(recent_total_clock // (60 * recent_count)) if recent_count else 0
        self.streak = streak

        # Calculate all-time stats
        if recent_count == 100:
            record = await booking_model.table.select_one_where(
                booking_model.slotid < nowid,
                userid=self.userid,
            ).select(
                _booked='COUNT(*)',
                _attended='COUNT(*) FILTER (WHERE attended)',
                _clocked='SUM(COALESCE(clock, 0))'
            ).with_no_adapter()
            self.all_stats = (record['_attended'], record['_booked'])
            self.all_avg = record['_clocked'] // (60 * record['_booked'])
        else:
            self.all_stats = self.recent_stats
            self.all_avg = self.recent_avg

from typing import Optional
from enum import IntEnum
import asyncio

import discord
from discord.ui.button import ButtonStyle, button, Button
from discord.ui.select import select, Select, SelectOption

from gui.base import CardMode

from meta import LionBot, conf, WEBSITE_URL
from utils.lib import MessageArgs
from utils.ui import input
from core.lion_guild import VoiceMode
from babel.translator import ctx_translator, LazyStr

from ..data import StatsData
from ..graphics.leaderboard import get_leaderboard_card
from .. import babel

from .base import StatsUI


_p = babel._p

ANKI_AVAILABLE = False


class LBPeriod(IntEnum):
    SEASON = 0
    DAY = 1
    WEEK = 2
    MONTH = 3
    ALLTIME = 4


class StatType(IntEnum):
    VOICE = 0
    TEXT = 1
    ANKI = 2


class LeaderboardUI(StatsUI):
    page_size = 10
    guildid: int

    def __init__(self, bot, user, guild, **kwargs):
        super().__init__(bot, user, guild, **kwargs)
        self.data: StatsData = bot.get_cog('StatsCog').data

        # ----- Constants initialised on run -----
        self.show_season = None
        self.period_starts = None

        # ----- UI state -----
        # Whether the leaderboard is focused on the calling member
        self.focused = True

        # Current visible page number
        self.pagen = 0

        # Current stat type
        self.stat_type = StatType.VOICE

        # Start of the current period
        self.current_period = LBPeriod.SEASON

        # Current rendered leaderboard card, if it exists
        self.card = None

        # ----- Cached and on-demand data -----
        # Cache of the full leaderboards for each type and period, populated on demand
        # (type, period) -> List[(userid, duration)]
        self.lb_data = {}

        # Cache of the cards already displayed
        # (type, period, filter_role_id) -> (pagen -> Optional[Future[Card]])
        self.cache = {}

        self.was_chunked: bool = guild.chunked

        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Web link button for richer leaderboard with podium, filters, periods
        self._web_button = discord.ui.Button(
            label="Full Leaderboard", emoji="🌐",
            url=f"{WEBSITE_URL}/dashboard/leaderboard",
            style=ButtonStyle.link,
        )
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: Role filter state for /leaderboard "Filter by Role" feature
        self.filter_role_id: Optional[int] = None
        self.available_filter_roles: list[int] = []
        self.role_filter_enabled: bool = False
        # --- END AI-MODIFIED ---

    async def run(self, interaction: discord.Interaction):
        self._original = interaction

        # Fetch guild data and populate period starts
        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        periods = {}
        self.show_season = bool(lguild.data.season_start)
        if self.show_season:
            periods[LBPeriod.SEASON] = lguild.data.season_start
            self.current_period = LBPeriod.SEASON
        else:
            self.current_period = LBPeriod.ALLTIME
        periods[LBPeriod.DAY] = lguild.today
        periods[LBPeriod.WEEK] = lguild.week_start
        periods[LBPeriod.MONTH] = lguild.month_start
        alltime = (lguild.data.first_joined_at or interaction.guild.created_at).astimezone(lguild.timezone)
        periods[LBPeriod.ALLTIME] = alltime
        self.period_starts = periods

        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Load role filter configuration for this guild (with cog safety check)
        self.role_filter_enabled = bool(lguild.data.leaderboard_role_filter_enabled)
        stats_cog = self.bot.get_cog('StatsCog')
        if self.role_filter_enabled and stats_cog is not None:
            filter_setting = await stats_cog.settings.LeaderboardFilterRoles.get(self.guildid)
            self.available_filter_roles = list(filter_setting.data) if filter_setting.data else []
        else:
            self.available_filter_roles = []
        self.filter_role_id = None
        # --- END AI-MODIFIED ---

        self.focused = True
        await self.refresh()

    async def focus_caller(self):
        """
        Focus the calling user, if possible.
        """
        self.focused = True
        data = await self.current_data()
        if data:
            caller_index = next((i for i, (uid, _) in enumerate(data) if uid == self.userid), None)
            if caller_index is not None:
                self.pagen = caller_index // self.page_size

    async def _fetch_lb_data(self, stat_type, period) -> list[tuple[int, int]]:
        """
        Worker for `fetch_lb_data`.
        """
        if stat_type is StatType.VOICE:
            if period is LBPeriod.ALLTIME:
                data = await self.data.VoiceSessionStats.leaderboard_all(self.guildid)
            elif (period_start := self.period_starts.get(period, None)) is None:
                raise ValueError("Uninitialised period requested!")
            else:
                data = await self.data.VoiceSessionStats.leaderboard_since(
                    self.guildid, period_start
                )
        elif stat_type is StatType.TEXT:
            if period is LBPeriod.ALLTIME:
                data = await self.data.MemberExp.leaderboard_all(self.guildid)
            elif (period_start := self.period_starts.get(period, None)) is None:
                raise ValueError("Uninitialised period requested!")
            else:
                data = await self.data.MemberExp.leaderboard_since(
                    self.guildid, period_start
                )
        else:
            # TODO: Anki data
            data = []

        # Filter out members which are not in the server and unranked roles and bots
        # Usually hits cache
        self.was_chunked = self.guild.chunked
        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Guard against StatsCog being None during shard reconnect/startup
        stats_cog = self.bot.get_cog('StatsCog')
        if stats_cog is not None:
            unranked_setting = await stats_cog.settings.UnrankedRoles.get(self.guild.id)
            unranked_roleids = set(unranked_setting.data)
        else:
            unranked_roleids = set()
        # --- END AI-MODIFIED ---
        true_leaderboard = []
        guild = self.guild
        for userid, stat_total in data:
            if member := guild.get_member(userid):
                if member.bot:
                    continue
                if any(role.id in unranked_roleids for role in member.roles):
                    continue
                true_leaderboard.append((userid, stat_total))
        return true_leaderboard

    async def fetch_lb_data(self, stat_type, period):
        """
        Fetch the leaderboard data for the given type and period.

        Uses cached futures so that requests are not repeated.
        """
        key = (stat_type, period)
        future = self.lb_data.get(key, None)
        if future is not None and not future.cancelled():
            result = await future
        else:
            future = asyncio.create_task(self._fetch_lb_data(*key))
            self.lb_data[key] = future
            result = await future

        return result

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: Apply role filter on top of cached leaderboard data
    async def current_data(self):
        """
        Helper method to retrieve the leaderboard data for the current mode,
        with role filter applied if active.
        """
        data = await self.fetch_lb_data(self.stat_type, self.current_period)
        if self.filter_role_id is not None:
            guild = self.guild
            filter_id = self.filter_role_id
            data = [
                (uid, total) for uid, total in data
                if (m := guild.get_member(uid)) and
                   any(r.id == filter_id for r in m.roles)
            ]
        return data
    # --- END AI-MODIFIED ---

    async def _render_card(self, stat_type, period, pagen, data):
        """
        Render worker for the given leaderboard page.
        """
        if data:
            # Calculate page data
            page_starts_at = pagen * self.page_size
            page_data = data[page_starts_at:page_starts_at + self.page_size]
            if not page_data:
                return None
            userids, times = zip(*page_data)
            positions = range(page_starts_at + 1, page_starts_at + self.page_size + 1)

            page_data = zip(userids, positions, times)
            if self.stat_type is StatType.VOICE:
                lguild = await self.bot.core.lions.fetch_guild(self.guildid)
                if lguild.guild_mode.voice is VoiceMode.VOICE:
                    mode = CardMode.VOICE
                else:
                    mode = CardMode.STUDY
            elif self.stat_type is StatType.TEXT:
                mode = CardMode.TEXT
            elif self.stat_type is StatType.ANKI:
                mode = CardMode.ANKI
            else:
                raise ValueError

            card = await get_leaderboard_card(
                self.bot, self.userid, self.guildid,
                mode,
                list(page_data)
            )
            await card.render()
            return card
        else:
            # Leaderboard is empty
            return None

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: Use filtered data and include filter_role_id in cache key
    # --- Original code (commented out for rollback) ---
    # async def fetch_page(self, stat_type, period, pagen):
    #     lb_data = await self.fetch_lb_data(stat_type, period)
    #     if lb_data:
    #         pagen %= (len(lb_data) // self.page_size) + (1 if len(lb_data) % self.page_size else 0)
    #     else:
    #         pagen = 0
    #     key = (stat_type, period, pagen)
    #     if (future := self.cache.get(key, None)) is not None and not future.cancelled():
    #         card = await future
    #     else:
    #         future = asyncio.create_task(self._render_card(
    #             stat_type, period, pagen, lb_data
    #         ))
    #         self.cache[key] = future
    #         card = await future
    #     return card
    # --- End original code ---
    async def fetch_page(self, stat_type, period, pagen):
        """
        Fetch the requested leaderboard page as a rendered LeaderboardCard.

        Applies cache where possible. Cache key includes filter_role_id
        so that different role filters produce separate cached cards.
        """
        lb_data = await self.current_data()
        if lb_data:
            pagen %= (len(lb_data) // self.page_size) + (1 if len(lb_data) % self.page_size else 0)
        else:
            pagen = 0
        key = (stat_type, period, self.filter_role_id, pagen)
        if (future := self.cache.get(key, None)) is not None and not future.cancelled():
            card = await future
        else:
            future = asyncio.create_task(self._render_card(
                stat_type,
                period,
                pagen,
                lb_data
            ))
            self.cache[key] = future
            card = await future
        return card
    # --- END AI-MODIFIED ---

    # UI interface
    @select(placeholder="Select Activity Type")
    async def stat_menu(self, selection: discord.Interaction, selected):
        if selected.values:
            await selection.response.defer(thinking=True)
            self.stat_type = StatType(int(selected.values[0]))
            self.focused = True
            await self.refresh(thinking=selection)

    async def stat_menu_refresh(self):
        # TODO: Customise based on configuration
        t = self.bot.translator.t
        menu = self.stat_menu
        menu.placeholder = t(_p(
            'ui:leaderboard|menu:stats|placeholder',
            "Select Activity Type"
        ))
        options = []
        lguild = await self.bot.core.lions.fetch_guild(self.guildid)
        if lguild.guild_mode.voice is VoiceMode.VOICE:
            options.append(
                SelectOption(
                    label=t(_p(
                        'ui:leaderboard|menu:stats|item:voice',
                        "Voice Activity"
                    )),
                    value=str(StatType.VOICE.value),
                    default=(self.stat_type == StatType.VOICE),
                )
            )
        else:
            options.append(
                SelectOption(
                    label=t(_p(
                        'ui:leaderboard|menu:stats|item:study',
                        "Productivity Statistics"
                    )),
                    value=str(StatType.VOICE.value),
                    default=(self.stat_type == StatType.VOICE),
                )
            )

        options.append(
            SelectOption(
                label=t(_p(
                    'ui:leaderboard|menu:stats|item:message',
                    "Message Activity"
                )),
                value=str(StatType.TEXT.value),
                default=(self.stat_type == StatType.TEXT),
            )
        )
        if ANKI_AVAILABLE:
            options.append(
                SelectOption(
                    label=t(_p(
                        'ui:leaderboard|menu;stats|item:anki',
                        "Anki Cards Reviewed"
                    )),
                    value=str(StatType.ANKI.value),
                    default=(self.stat_type == StatType.ANKI),
                )
            )
        menu.options = options

    # --- AI-MODIFIED (2026-03-23) ---
    # Purpose: Role filter dropdown for /leaderboard "Filter by Role" feature
    @select(placeholder="Filter by Role")
    async def role_filter_menu(self, selection: discord.Interaction, selected):
        if selected.values:
            await selection.response.defer(thinking=True)
            value = selected.values[0]
            if value == "none":
                self.filter_role_id = None
            else:
                self.filter_role_id = int(value)
            self.focused = True
            self.pagen = 0
            await self.refresh(thinking=selection)

    async def role_filter_menu_refresh(self):
        t = self.bot.translator.t
        menu = self.role_filter_menu
        menu.placeholder = t(_p(
            'ui:leaderboard|menu:role_filter|placeholder',
            "Filter by Role"
        ))
        options = [
            SelectOption(
                label=t(_p(
                    'ui:leaderboard|menu:role_filter|item:all',
                    "All Members"
                )),
                value="none",
                default=(self.filter_role_id is None),
            )
        ]
        guild = self.guild
        for role_id in self.available_filter_roles:
            role = guild.get_role(role_id)
            if role:
                options.append(
                    SelectOption(
                        label=role.name[:100],
                        value=str(role.id),
                        default=(self.filter_role_id == role.id),
                    )
                )
        menu.options = options
    # --- END AI-MODIFIED ---

    @button(label="This Season", style=ButtonStyle.grey)
    async def season_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.current_period = LBPeriod.SEASON
        self.focused = True
        await self.refresh(thinking=press)

    @button(label="Today", style=ButtonStyle.grey)
    async def day_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.current_period = LBPeriod.DAY
        self.focused = True
        await self.refresh(thinking=press)

    @button(label="This Week", style=ButtonStyle.grey)
    async def week_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.current_period = LBPeriod.WEEK
        self.focused = True
        await self.refresh(thinking=press)

    @button(label="This Month", style=ButtonStyle.grey)
    async def month_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.current_period = LBPeriod.MONTH
        self.focused = True
        await self.refresh(thinking=press)

    @button(label="All Time", style=ButtonStyle.grey)
    async def alltime_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.current_period = LBPeriod.ALLTIME
        self.focused = True
        await self.refresh(thinking=press)

    @button(emoji=conf.emojis.backward, style=ButtonStyle.grey)
    async def prev_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.pagen -= 1
        self.focused = False
        await self.refresh(thinking=press)

    async def _prepare(self):
        t = self.bot.translator.t
        self.season_button.label = t(_p(
            'ui:leaderboard|button:season|label',
            "This Season"
        ))
        self.day_button.label = t(_p(
            'ui:leaderboard|button:day|label',
            "Today"
        ))
        self.week_button.label = t(_p(
            'ui:leaderboard|button:week|label',
            "This Week"
        ))
        self.month_button.label = t(_p(
            'ui:leaderboard|button:month|label',
            "This Month"
        ))
        self.alltime_button.label = t(_p(
            'ui:leaderboard|button:alltime|label',
            "All Time"
        ))
        self.jump_button.label = t(_p(
            'ui:leaderboard|button:jump|label',
            "Jump"
        ))

    @button(label="Jump", style=ButtonStyle.blurple)
    async def jump_button(self, press: discord.Interaction, pressed: Button):
        """
        Jump-to-page button.
        Loads a page-switch dialogue.
        """
        t = self.bot.translator.t
        try:
            interaction, value = await input(
                press,
                title=t(_p(
                    'ui:leaderboard|button:jump|input:title',
                    "Jump to page"
                )),
                question=t(_p(
                    'ui:leaderboard|button:jump|input:question',
                    "Page number to jump to"
                ))
            )
            value = value.strip()
        except asyncio.TimeoutError:
            return

        if not value.lstrip('- ').isdigit():
            error_embed = discord.Embed(
                title=t(_p(
                    'ui:leaderboard|button:jump|error:invalid_page',
                    "Invalid page number, please try again!"
                )),
                colour=discord.Colour.brand_red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
        else:
            await interaction.response.defer(thinking=True)
            pagen = int(value.lstrip('- '))
            if value.startswith('-'):
                pagen = -1 * pagen
            elif pagen > 0:
                pagen = pagen - 1
            self.pagen = pagen
            self.focused = False
            await self.refresh(thinking=interaction)

    async def jump_button_refresh(self):
        component = self.jump_button

        data = await self.current_data()
        if not data:
            # Component should be hidden
            component.label = "-/-"
            component.disabled = True
        else:
            page_count = (len(data) // self.page_size) + 1
            pagen = self.pagen % page_count
            component.label = "{}/{}".format(pagen + 1, page_count)
            component.disabled = (page_count <= 1)

    @button(emoji=conf.emojis.forward, style=ButtonStyle.grey)
    async def next_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True)
        self.pagen += 1
        self.focused = False
        await self.refresh(thinking=press)

    async def make_message(self) -> MessageArgs:
        """
        Generate UI message arguments from stored data
        """
        t = self.bot.translator.t
        chunk_warning = t(_p(
            'ui:leaderboard|chunk_warning',
            "**Note:** Could not retrieve member list from Discord, so some members may be missing. "
            "Try again in a minute!"
        ))
        if self.card is not None:
            period_start = self.period_starts[self.current_period]
            header = t(_p(
                'ui:leaderboard|since',
                "Counting statistics since {timestamp}"
            )).format(timestamp=discord.utils.format_dt(period_start))
            # --- AI-MODIFIED (2026-03-23) ---
            # Purpose: Show active role filter in leaderboard header
            if self.filter_role_id is not None:
                role = self.guild.get_role(self.filter_role_id)
                role_name = role.name if role else str(self.filter_role_id)
                filter_line = t(_p(
                    'ui:leaderboard|filter_active',
                    "Filtered by role: **{role}**"
                )).format(role=role_name)
                header = '\n'.join((header, filter_line))
            # --- END AI-MODIFIED ---
            if not self.was_chunked:
                header = '\n'.join((header, chunk_warning))
            args = MessageArgs(
                embed=None,
                content=header,
                file=self.card.as_file('leaderboard.png')
            )
        else:
            if self.stat_type is StatType.VOICE:
                empty_description = t(_p(
                    'ui:leaderboard|mode:voice|message:empty|desc',
                    "There has been no voice activity since {timestamp}"
                ))
            elif self.stat_type is StatType.TEXT:
                empty_description = t(_p(
                    'ui:leaderboard|mode:text|message:empty|desc',
                    "There has been no message activity since {timestamp}"
                ))
            elif self.stat_type is StatType.ANKI:
                empty_description = t(_p(
                    'ui:leaderboard|mode:anki|message:empty|desc',
                    "There have been no Anki cards reviewed since {timestamp}"
                ))
            empty_description = empty_description.format(
                timestamp=discord.utils.format_dt(self.period_starts[self.current_period])
            )
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                title=t(_p(
                    'ui:leaderboard|message:empty|title',
                    "Leaderboard Empty!"
                )),
                description=empty_description
            )
            args = MessageArgs(
                content=chunk_warning if not self.was_chunked else None,
                embed=embed,
                files=[]
            )
        return args

    async def refresh_components(self):
        await self._prepare()
        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: Include role_filter_menu_refresh in gather when filter is available
        refresh_tasks = [
            self.jump_button_refresh(),
            self.close_button_refresh(),
            self.stat_menu_refresh(),
        ]
        show_role_filter = self.role_filter_enabled and len(self.available_filter_roles) > 0
        if show_role_filter:
            refresh_tasks.append(self.role_filter_menu_refresh())
        await asyncio.gather(*refresh_tasks)
        # --- END AI-MODIFIED ---

        # Compute period row
        period_buttons = {
            LBPeriod.DAY: self.day_button,
            LBPeriod.WEEK: self.week_button,
            LBPeriod.MONTH: self.month_button
        }
        if self.show_season:
            period_buttons[LBPeriod.SEASON] = self.season_button
        else:
            period_buttons[LBPeriod.ALLTIME] = self.alltime_button

        for period, component in period_buttons.items():
            if period is self.current_period:
                component.style = ButtonStyle.blurple
            else:
                component.style = ButtonStyle.grey

        period_row = tuple(period_buttons.values())

        # Compute page row
        data = await self.current_data()
        multipage = len(data) > self.page_size
        if multipage:
            page_row = (
                self.prev_button, self.jump_button, self.close_button, self.next_button
            )
        else:
            period_row = (*period_row, self.close_button)
            page_row = ()

        # --- AI-MODIFIED (2026-03-23) ---
        # Purpose: Conditionally include role filter select row; layout stays within 5 rows
        self._layout = [
            (self.stat_menu,),
        ]
        if show_role_filter:
            self._layout.append((self.role_filter_menu,))
        self._layout.append(period_row)
        if page_row:
            self._layout.append(page_row)
        self._layout.append((self._web_button,))
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-03-19) ---
        # Purpose: Vote button now injected globally via _maybe_append_vote_button in StatsUI.refresh()
        # --- Original code (commented out for rollback) ---
        # voting = self.bot.get_cog('TopggCog')
        # if voting and not await voting.check_voted_recently(self.userid):
        #     premiumcog = self.bot.get_cog('PremiumCog')
        #     if not (premiumcog and await premiumcog.is_premium_guild(self.guild.id)):
        #         self._layout.append((await voting.vote_button_for_user(self.userid),))
        # --- End original code ---
        # --- END AI-MODIFIED ---

    async def reload(self):
        """
        Reload UI data, applying cache where possible.
        """
        if self.focused:
            await self.focus_caller()
        self.card = await self.fetch_page(
            self.stat_type,
            self.current_period,
            self.pagen
        )

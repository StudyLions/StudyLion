from itertools import chain
from typing import Optional
from dataclasses import dataclass
import asyncio
import datetime as dt

import discord
from discord.ui.select import select, Select, SelectOption, UserSelect
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.text_input import TextInput, TextStyle

from meta import LionBot, conf
from meta.errors import ResponseTimedOut, SafeCancellation, UserInputError
from data import ORDER, Condition

from utils.ui import MessageUI, input
from utils.lib import MessageArgs, tabulate, utc_now

from . import babel, logger
from .ticket import Ticket
from .data import ModerationData, TicketType, TicketState

_p = babel._p

@dataclass
class TicketFilter:
    bot: LionBot

    after: Optional[dt.datetime] = None
    before: Optional[dt.datetime] = None
    targetids: Optional[list[int]] = None
    moderatorids: Optional[list[int]] = None
    types: Optional[list[TicketType]] = None
    states: Optional[list[TicketState]] = None

    def conditions(self) -> list[Condition]:
        conditions = []
        Ticket = ModerationData.Ticket

        if self.after is not None:
            conditions.append(Ticket.created_at >= self.after)
        if self.before is not None:
            conditions.append(Ticket.created_at < self.before)
        if self.targetids is not None:
            conditions.append(Ticket.targetid == self.targetids)
        if self.moderatorids is not None:
            conditions.append(Ticket.moderator_id == self.moderatorids)
        if self.types is not None:
            conditions.append(Ticket.ticket_type == self.types)
        if self.states is not None:
            conditions.append(Ticket.ticket_state == self.states)

        return conditions

    def formatted(self) -> str:
        t = self.bot.translator.t
        lines = []
        
        if self.after is not None:
            name = t(_p(
                'ticketfilter|field:after|name',
                "Created After"
            ))
            value = discord.utils.format_dt(self.after, 'd')
            lines.append((name, value))

        if self.before is not None:
            name = t(_p(
                'ticketfilter|field:before|name',
                "Created Before"
            ))
            value = discord.utils.format_dt(self.before, 'd')
            lines.append((name, value))

        if self.targetids is not None:
            name = t(_p(
                'ticketfilter|field:targetids|name',
                "Targets"
            ))
            value = ', '.join(f"<@{uid}>" for uid in self.targetids) or 'None'
            lines.append((name, value))

        if self.moderatorids is not None:
            name = t(_p(
                'ticketfilter|field:moderatorids|name',
                "Moderators"
            ))
            value = ', '.join(f"<@{uid}>" for uid in self.moderatorids) or 'None'
            lines.append((name, value))

        if self.types is not None:
            name = t(_p(
                'ticketfilter|field:types|name',
                "Ticket Types"
            ))
            value = ', '.join(typ.name for typ in self.types) or 'None'
            lines.append((name, value))

        if self.states is not None:
            name = t(_p(
                'ticketfilter|field:states|name',
                "Ticket States"
            ))
            value = ', '.join(state.name for state in self.states) or 'None'
            lines.append((name, value))

        if lines:
            table = tabulate(*lines)
            filterstr = '\n'.join(table)
        else:
            filterstr = ''

        return filterstr


class TicketListUI(MessageUI):
    block_len = 10

    def _init_children(self):
        # HACK to stop ViewWeights complaining that this UI has too many children
        # Children will be correctly initialised after parent init.
        return []

    def __init__(self, bot: LionBot, guild: discord.Guild, callerid: int, filters=None, **kwargs):
        super().__init__(callerid=callerid, **kwargs)
        self._children = super()._init_children()

        self.bot = bot
        self.data: ModerationData = bot.db.registries[ModerationData.__name__]
        self.guild = guild
        self.filters = filters or TicketFilter(bot)

        # Paging state
        self._pagen = 0
        self.blocks = [[]]

        # UI State
        self.show_filters = False
        self.show_tickets = False

        self.child_ticket: Optional[TicketUI] = None

    @property
    def page_count(self):
        return len(self.blocks)

    @property
    def pagen(self):
        self._pagen = self._pagen % self.page_count
        return self._pagen

    @pagen.setter
    def pagen(self, value):
        self._pagen = value % self.page_count

    @property
    def current_page(self):
        return self.blocks[self.pagen]

    # ----- API -----

    # ----- UI Components -----
    # Edit Filters
    @button(
        label="EDIT_FILTER_BUTTON_PLACEHOLDER",
        style=ButtonStyle.blurple
    )
    async def edit_filter_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.show_filters = True
        self.show_tickets = False
        await self.refresh(thinking=press)
    
    async def edit_filter_button_refresh(self):
        button = self.edit_filter_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:tickets|button:edit_filter|label',
            "Edit Filters"
        ))
        button.style = ButtonStyle.grey if not self.show_filters else ButtonStyle.blurple

    # Select Ticket
    @button(
        label="SELECT_TICKET_BUTTON_PLACEHOLDER",
        style=ButtonStyle.blurple
    )
    async def select_ticket_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.show_tickets = True
        self.show_filters = False
        await self.refresh(thinking=press)
    
    async def select_ticket_button_refresh(self):
        button = self.select_ticket_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:tickets|button:select_ticket|label',
            "Select Ticket"
        ))
        button.style = ButtonStyle.grey if not self.show_tickets else ButtonStyle.blurple

    # Pardon All
    @button(
        label="PARDON_BUTTON_PLACEHOLDER",
        style=ButtonStyle.red
    )
    async def pardon_button(self, press: discord.Interaction, pressed: Button):
        t = self.bot.translator.t

        tickets = list(chain(*self.blocks))
        if not tickets:
            raise UserInputError(t(_p(
                'ui:tickets|button:pardon|error:no_tickets',
                "Not tickets matching the given criterial! Nothing to pardon."
            )))

        # Request reason via modal
        modal_title = t(_p(
            'ui:tickets|button:pardon|modal:reason|title',
            "Pardon Tickets"
        ))
        input_field = TextInput(
            label=t(_p(
                'ui:tickets|button:pardon|modal:reason|field|label',
                "Why are you pardoning these tickets?"
            )),
            style=TextStyle.long,
            min_length=0,
            max_length=1024,
        )
        try:
            interaction, reason = await input(
                press, modal_title, field=input_field, timeout=300,
            )
        except asyncio.TimeoutError:
            raise ResponseTimedOut

        await interaction.response.defer(thinking=True, ephemeral=True)

        # Run pardon
        for ticket in tickets:
            await ticket.pardon(modid=press.user.id, reason=reason)

        await self.refresh(thinking=interaction)
    
    async def pardon_button_refresh(self):
        button = self.pardon_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:tickets|button:pardon|label',
            "Pardon All"
        ))
        button.disabled = not bool(self.current_page)

    # Filter Ticket Type
    @select(
        cls=Select,
        placeholder="FILTER_TYPE_MENU_PLACEHOLDER",
        min_values=1, max_values=3,
    )
    async def filter_type_menu(self, selection: discord.Interaction, selected: Select):
        await selection.response.defer(thinking=True, ephemeral=True)
        self.filters.types = [TicketType[value] for value in selected.values] or None
        self.pagen = 0
        await self.refresh(thinking=selection)
    
    async def filter_type_menu_refresh(self):
        menu = self.filter_type_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:tickets|menu:filter_type|placeholder',
            "Select Ticket Types"
        ))

        options = []
        descmap = {
            TicketType.NOTE: ('Notes',),
            TicketType.WARNING: ('Warnings',),
            TicketType.STUDY_BAN: ('Video Blacklists',),
        }
        filtered = self.filters.types
        for typ, (name,) in descmap.items():
            option = SelectOption(
                label=name,
                value=typ.name,
                default=(filtered is None or typ in filtered)
            )
            options.append(option)
        menu.options = options

    # Filter Ticket State
    @select(
        cls=Select,
        placeholder="FILTER_STATE_MENU_PLACEHOLDER",
        min_values=1, max_values=4
    )
    async def filter_state_menu(self, selection: discord.Interaction, selected: Select):
        await selection.response.defer(thinking=True, ephemeral=True)
        self.filters.states = [TicketState[value] for value in selected.values] or None
        self.pagen = 0
        await self.refresh(thinking=selection)
    
    async def filter_state_menu_refresh(self):
        menu = self.filter_state_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:tickets|menu:filter_state|placeholder',
            "Select Ticket States"
        ))

        options = []
        descmap = {
            TicketState.OPEN: ('OPEN', ),
            TicketState.EXPIRING: ('EXPIRING', ),
            TicketState.EXPIRED: ('EXPIRED', ),
            TicketState.PARDONED: ('PARDONED', ),
        }
        filtered = self.filters.states
        for state, (name,) in descmap.items():
            option = SelectOption(
                label=name,
                value=state.name,
                default=(filtered is None or state in filtered)
            )
            options.append(option)
        menu.options = options

    # Filter Ticket Target
    @select(
        cls=UserSelect,
        placeholder="FILTER_TARGET_MENU_PLACEHOLDER",
        min_values=0, max_values=10
    )
    async def filter_target_menu(self, selection: discord.Interaction, selected: UserSelect):
        await selection.response.defer(thinking=True, ephemeral=True)
        self.filters.targetids = [user.id for user in selected.values] or None
        self.pagen = 0
        await self.refresh(thinking=selection)
    
    async def filter_target_menu_refresh(self):
        menu = self.filter_target_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:tickets|menu:filter_target|placeholder',
            "Select Ticket Targets"
        ))

    # Select Ticket
    @select(
        cls=Select,
        placeholder="TICKETS_MENU_PLACEHOLDER",
        min_values=1, max_values=1
    )
    async def tickets_menu(self, selection: discord.Interaction, selected: Select):
        await selection.response.defer(thinking=True, ephemeral=True)
        if selected.values:
            ticketid = int(selected.values[0])
            ticket = await Ticket.fetch_ticket(self.bot, ticketid)
            ticketui = TicketUI(self.bot, ticket, self._callerid)
            if self.child_ticket:
                await self.child_ticket.quit()
            self.child_ticket = ticketui
            await ticketui.run(selection)
    
    async def tickets_menu_refresh(self):
        menu = self.tickets_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:tickets|menu:tickets|placeholder',
            "Select Ticket"
        ))
        options = []
        for ticket in self.current_page:
            option = SelectOption(
                label=f"Ticket #{ticket.data.guild_ticketid}",
                value=str(ticket.data.ticketid)
            )
            options.append(option)
        menu.options = options

    # Backwards
    @button(emoji=conf.emojis.backward, style=ButtonStyle.grey)
    async def prev_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.pagen -= 1
        await self.refresh(thinking=press)

    # Jump to page
    @button(label="JUMP_PLACEHOLDER", style=ButtonStyle.blurple)
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
                    'ui:tickets|button:jump|input:title',
                    "Jump to page"
                )),
                question=t(_p(
                    'ui:tickets|button:jump|input:question',
                    "Page number to jump to"
                ))
            )
            value = value.strip()
        except asyncio.TimeoutError:
            return

        if not value.lstrip('- ').isdigit():
            error_embed = discord.Embed(
                title=t(_p(
                    'ui:tickets|button:jump|error:invalid_page',
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
            await self.refresh(thinking=interaction)

    async def jump_button_refresh(self):
        component = self.jump_button
        component.label = f"{self.pagen + 1}/{self.page_count}"
        component.disabled = (self.page_count <= 1)

    # Forward
    @button(emoji=conf.emojis.forward, style=ButtonStyle.grey)
    async def next_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True)
        self.pagen += 1
        await self.refresh(thinking=press)

    # Quit
    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        """
        Quit the UI.
        """
        await press.response.defer()
        if self.child_ticket:
            await self.child_ticket.quit()
        await self.quit()

    # ----- UI Flow -----
    def _format_ticket(self, ticket) -> str:
        """
        Format a ticket into a single embed line.
        """
        components = (
            "[#{ticketid}]({link})",
            "{created}",
            "`{type}[{state}]`",
            "<@{targetid}>",
            "{content}",
        )

        formatstr = ' | '.join(components)

        data = ticket.data
        if not data.content:
            content = 'No Content'
        elif len(data.content) > 100:
            content = data.content[:97] + '...'
        else:
            content = data.content

        ticketstr = formatstr.format(
            ticketid=data.guild_ticketid,
            link=ticket.jump_url or 'https://lionbot.org',
            created=discord.utils.format_dt(data.created_at, 'd'),
            type=data.ticket_type.name,
            state=data.ticket_state.name,
            targetid=data.targetid,
            content=content,
        )
        if data.ticket_state is TicketState.PARDONED:
            ticketstr = f"~~{ticketstr}~~"
        return ticketstr

    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t
        embed = discord.Embed(
            title=t(_p(
                'ui:tickets|embed|title',
                "Moderation Tickets in {guild}"
            )).format(guild=self.guild.name),
            timestamp=utc_now()
        )
        tickets = self.current_page
        if tickets:
            desc = '\n'.join(self._format_ticket(ticket) for ticket in tickets)
        else:
            desc = t(_p(
                'ui:tickets|embed|desc:no_tickets',
                "No tickets matching the given criteria!"
            ))
        embed.description = desc

        filterstr = self.filters.formatted()
        if filterstr:
            embed.add_field(
                name=t(_p(
                    'ui:tickets|embed|field:filters|name',
                    "Filters"
                )),
                value=filterstr,
                inline=False
            )

        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        to_refresh = (
            self.edit_filter_button_refresh(),
            self.select_ticket_button_refresh(),
            self.pardon_button_refresh(),
            self.tickets_menu_refresh(),
            self.filter_type_menu_refresh(),
            self.filter_state_menu_refresh(),
            self.filter_target_menu_refresh(),
            self.jump_button_refresh(),
        )
        await asyncio.gather(*to_refresh)

        action_line = (
            self.edit_filter_button,
            self.select_ticket_button,
            self.pardon_button,
        )

        if self.page_count > 1:
            page_line = (
                self.prev_button,
                self.jump_button,
                self.quit_button,
                self.next_button,
            )
        else:
            page_line = ()
            action_line = (*action_line, self.quit_button)

        if self.show_filters:
            menus = (
                (self.filter_type_menu,),
                (self.filter_state_menu,),
                (self.filter_target_menu,),
            )
        elif self.show_tickets and self.current_page:
            menus = ((self.tickets_menu,),)
        else:
            menus = ()

        self.set_layout(
            action_line,
            *menus,
            page_line,
        )

    async def reload(self):
        tickets = await Ticket.fetch_tickets(
            self.bot,
            *self.filters.conditions(),
            guildid=self.guild.id,
        )
        blocks = [
            tickets[i:i+self.block_len]
            for i in range(0, len(tickets), self.block_len)
        ]
        self.blocks = blocks or [[]]


class TicketUI(MessageUI):
    def __init__(self, bot: LionBot, ticket: Ticket, callerid: int, **kwargs):
        super().__init__(callerid=callerid, **kwargs)

        self.bot = bot
        self.ticket = ticket

    # ----- API -----

    # ----- UI Components -----
    # Pardon Ticket
    @button(
        label="PARDON_BUTTON_PLACEHOLDER",
        style=ButtonStyle.red
    )
    async def pardon_button(self, press: discord.Interaction, pressed: Button):
        t = self.bot.translator.t

        modal_title = t(_p(
            'ui:ticket|button:pardon|modal:reason|title',
            "Pardon Moderation Ticket"
        ))
        input_field = TextInput(
            label=t(_p(
                'ui:ticket|button:pardon|modal:reason|field|label',
                "Why are you pardoning this ticket?"
            )),
            style=TextStyle.long,
            min_length=0,
            max_length=1024,
        )
        try:
            interaction, reason = await input(
            press, modal_title, field=input_field, timeout=300,
        )
        except asyncio.TimeoutError:
            raise ResponseTimedOut

        await interaction.response.defer(thinking=True, ephemeral=True)

        await self.ticket.pardon(modid=press.user.id, reason=reason)
        await self.refresh(thinking=interaction)


    async def pardon_button_refresh(self):
        button = self.pardon_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:ticket|button:pardon|label',
            "Pardon"
        ))
        button.disabled = (self.ticket.data.ticket_state is TicketState.PARDONED)

    # Quit
    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        """
        Quit the UI.
        """
        await press.response.defer()
        await self.quit()

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        return await self.ticket.make_message()

    async def refresh_layout(self):
        await self.pardon_button_refresh()
        self.set_layout(
            (self.pardon_button, self.quit_button,)
        )

    async def reload(self):
        await self.ticket.data.refresh()

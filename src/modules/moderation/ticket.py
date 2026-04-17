import asyncio
import pytz
import datetime as dt
from typing import Optional

import discord
from core.lion_guild import LionGuild
from data.queries import ORDER
from meta import LionBot
from utils.lib import MessageArgs, jumpto, strfdelta, utc_now
from utils.monitor import TaskMonitor

from . import babel, logger
from .data import ModerationData, TicketState, TicketType
from .settings import ModerationSettings

_p = babel._p


# Factory map, TicketType -> Ticket subclass
_ticket_types = {}


def ticket_factory(ticket_type: TicketType):
    """
    Register a Ticket subclass as the factory for the given ticket_type.
    """
    def decorator(cls):
        _ticket_types[ticket_type] = cls
        return cls
    return decorator


class Ticket:
    """
    ABC representing a single recorded moderation action.

    All subclasses must be constructable from the same args.
    """
    __slots__ = ('lguild', 'bot', 'data')

    # Task manager keeping track of expiring ticket tasks
    # Tickets are keyed by ticketid
    expiring = TaskMonitor()

    def __init__(self, lguild: LionGuild, ticket_data: ModerationData.Ticket, **kwargs):
        self.lguild = lguild
        self.bot: LionBot = lguild.bot
        self.data = ticket_data

    @classmethod
    async def create(cls, *args, **kwargs):
        """
        Create a new ticket of this type.

        Must be extended by concrete ticket types.
        `kwargs` should generally be passed directly to the data constructor.
        This method may perform discord actions such as adding or removing a role.
        If the actions fail, the method may passthrough the resulting HTTPException.
        """
        raise NotImplementedError

    @classmethod
    async def fetch_ticket(cls, bot: LionBot, ticketid: int) -> 'Ticket':
        """
        Fetch a single requested ticketid.

        Factory method which uses the internal `_ticket_types` map
        to instantiate the correct Ticket subclass.
        """
        registry: ModerationData = bot.db.registries['ModerationData']
        data = await registry.Ticket.fetch(ticketid)
        if data:
            lguild = await bot.core.lions.fetch_guild(data.guildid)
            cls = _ticket_types.get(data.ticket_type, cls)
            ticket = cls(lguild, data)
        else:
            ticket = None
        return ticket

    @classmethod
    async def fetch_tickets(cls, bot: LionBot, *args, **kwargs) -> list['Ticket']:
        """
        Fetch tickets matching the given criteria.

        Factory method which uses the internal `_ticket_types` to
        instantiate the correct classes.
        """
        registry: ModerationData = bot.db.registries['ModerationData']
        rows = await registry.Ticket.fetch_where(*args, **kwargs).order_by(
            'created_at', ORDER.DESC,
        )
        tickets = []
        if rows:
            guildids = set(row.guildid for row in rows)
            lguilds = await bot.core.lions.fetch_guilds(*guildids)
            for row in rows:
                lguild = lguilds[row.guildid]
                cls = _ticket_types.get(row.ticket_type, cls)
                ticket = cls(lguild, row)
                tickets.append(ticket)
        return tickets

    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.data.guildid)

    @property
    def target(self) -> Optional[discord.Member]:
        guild = self.guild
        if guild:
            return guild.get_member(self.data.targetid)
        else:
            return None

    @property
    def type(self) -> TicketType:
        return self.data.ticket_type

    @property
    def jump_url(self) -> Optional[str]:
        """
        A link to jump to the ticket message in the ticket log,
        if it has been posted.

        May not be valid if the ticket was not posted or the ticket log has changed.
        """
        ticket_log_id = self.lguild.config.get(ModerationSettings.TicketLog.setting_id).data
        if ticket_log_id and self.data.log_msg_id:
            return jumpto(self.data.guildid, ticket_log_id, self.data.log_msg_id)
        else:
            return None

    # --- AI-MODIFIED (2026-04-17) ---
    # Purpose: Helpers used to surface the "offense N of M" context for
    #   STUDY_BAN/SCREEN_BAN blacklist tickets in the mod log embed,
    #   /tickets list, blacklist DM alerts, and dashboard.
    #   Mirrors the auto-duration count logic in
    #   VideoTicket.autocreate / ScreenTicket.autocreate (non-pardoned tickets only).
    _BLACKLIST_DURATION_TABLES = {
        TicketType.STUDY_BAN: 'studyban_durations',
        TicketType.SCREEN_BAN: 'screenban_durations',
    }

    async def get_offense_number(self) -> Optional[int]:
        """
        Return the chronological non-pardoned offense number of this ticket
        among the same target's same-type blacklist tickets in this guild.

        Returns None for non-blacklist ticket types and for pardoned tickets.
        For a non-pardoned blacklist ticket the value is at least 1.
        """
        if self.data.ticket_type not in self._BLACKLIST_DURATION_TABLES:
            return None
        if self.data.ticket_state is TicketState.PARDONED:
            return None

        TicketModel = self.data.__class__
        row = await TicketModel.table.select_one_where(
            (TicketModel.ticket_state != TicketState.PARDONED),
            (TicketModel.ticketid <= self.data.ticketid),
            guildid=self.data.guildid,
            targetid=self.data.targetid,
            ticket_type=self.data.ticket_type,
        ).with_no_adapter().select(offense_number="COUNT(*)")
        if not row:
            return None
        return int(row[0]['offense_number'] or 0) or None

    async def get_total_tiers(self) -> Optional[int]:
        """
        Return the configured number of escalation tiers (durations) for this
        guild for this blacklist type.

        Returns None for non-blacklist ticket types or if no durations configured.
        """
        table_name = self._BLACKLIST_DURATION_TABLES.get(self.data.ticket_type)
        if not table_name:
            return None
        try:
            async with self.bot.db.connection() as conn:
                async with conn.cursor() as cur:
                    # --- AI-MODIFIED (2026-04-17) ---
                    # The shared connection pool uses psycopg dict_row factory
                    # (see data/connector.py), so cur.fetchone() returns a
                    # mapping keyed by column name, not a tuple. Indexing with
                    # [0] raises KeyError. Alias the COUNT explicitly so the
                    # code is robust to dict_row.
                    await cur.execute(
                        f"SELECT COUNT(*) AS tier_count FROM {table_name} WHERE guildid = %s",
                        (self.data.guildid,),
                    )
                    row = await cur.fetchone()
                    count = int(row['tier_count']) if row and row.get('tier_count') is not None else 0
                    # --- END AI-MODIFIED ---
        except Exception:
            logger.exception(
                f"Failed to fetch total tiers for ticket {self.data.ticketid}"
            )
            return None
        return count or None
    # --- END AI-MODIFIED ---

    async def make_message(self) -> MessageArgs:
        """
        Base form of the ticket message posted to the moderation ticket log.

        Subclasses are expected to extend or override this,
        but this forms the default and standard structure for a ticket.
        """
        t = self.bot.translator.t
        # TODO: Better solution for guild ticket ids
        await self.data.refresh()
        data = self.data
        member = self.target
        name = str(member) if member else str(data.targetid)

        if data.auto:
            title_fmt = t(_p(
                'ticket|title:auto',
                "Ticket #{ticketid} | {state} | {type}[Auto] | {name}"
            ))
        else:
            title_fmt = t(_p(
                'ticket|title:manual',
                "Ticket #{ticketid} | {state} | {type} | {name}"
            ))
        title = title_fmt.format(
            ticketid=data.guild_ticketid,
            state=data.ticket_state.name,
            type=data.ticket_type.name,
            name=name
        )

        embed = discord.Embed(
            title=title,
            description=data.content,
            timestamp=data.created_at.replace(tzinfo=pytz.utc),
            colour=discord.Colour.orange()
        )
        embed.add_field(
            name=t(_p('ticket|field:target|name', "Target")),
            value=f"<@{data.targetid}>"
        )
        if not data.auto:
            embed.add_field(
                name=t(_p('ticket|field:moderator|name', "Moderator")),
                value=f"<@{data.moderator_id}>"
            )
        # --- AI-MODIFIED (2026-04-17) ---
        # Purpose: Surface "Offense #N (Tier N of M)" for STUDY_BAN/SCREEN_BAN
        #   so mods see the escalation context directly in the ticket log embed.
        offense_number = await self.get_offense_number()
        if offense_number is not None:
            total_tiers = await self.get_total_tiers()
            if total_tiers:
                offense_value = t(_p(
                    'ticket|field:offense|value:with_tiers',
                    "#{number} (Tier {tier} of {total})"
                )).format(
                    number=offense_number,
                    tier=min(offense_number, total_tiers),
                    total=total_tiers,
                )
            else:
                offense_value = t(_p(
                    'ticket|field:offense|value:plain',
                    "#{number}"
                )).format(number=offense_number)
            embed.add_field(
                name=t(_p('ticket|field:offense|name', "Offense")),
                value=offense_value,
            )
        # --- END AI-MODIFIED ---
        if data.expiry:
            timestamp = discord.utils.format_dt(data.expiry)
            if data.ticket_state is TicketState.EXPIRING:
                embed.add_field(
                    name=t(_p('ticket|field:expiry|mode:expiring|name', "Expires At")),
                    value=t(_p(
                        'ticket|field:expiry|mode:expiring|value',
                        "{timestamp}\nDuration: `{duration}`"
                    )).format(
                        timestamp=timestamp,
                        duration=strfdelta(dt.timedelta(seconds=data.duration))
                    ),
                )
            elif data.ticket_state is TicketState.EXPIRED:
                embed.add_field(
                    name=t(_p('ticket|field:expiry|mode:expired|name', "Expired")),
                    value=t(_p(
                        'ticket|field:expiry|mode:expired|value',
                        "{timestamp}"
                    )).format(
                        timestamp=timestamp,
                    ),
                )
            else:
                embed.add_field(
                    name=t(_p('ticket|field:expiry|mode:open|name', "Expiry")),
                    value=t(_p(
                        'ticket|field:expiry|mode:open|value',
                        "{timestamp}"
                    )).format(
                        timestamp=timestamp,
                    ),
                )

        if data.context:
            embed.add_field(
                name=t(_p('ticket|field:context|name', "Context")),
                value=data.context,
                inline=False
            )

        if data.addendum:
            embed.add_field(
                name=t(_p('ticket|field:notes|name', "Notes")),
                value=data.addendum,
                inline=False
            )

        if data.ticket_state is TicketState.PARDONED:
            embed.add_field(
                name=t(_p('ticket|field:pardoned|name', "Pardoned")),
                value=t(_p(
                    'ticket|field:pardoned|value',
                    "Pardoned by <@{moderator}> at {timestamp}.\n{reason}"
                )).format(
                    moderator=data.pardoned_by,
                    timestamp=discord.utils.format_dt(data.pardoned_at) if data.pardoned_at else 'Unknown',
                    reason=data.pardoned_reason or ''
                ),
                inline=False
            )

        embed.set_footer(
            text=f"ID: {data.targetid}"
        )

        return MessageArgs(embed=embed)

    async def update(self, **kwargs):
        """
        Update the ticket data.

        `kwargs` are passed directly to the data update method.
        Also handles updating the ticket message and rescheduling the
        expiry, if applicable.
        No error is raised if the ticket message cannot be updated.

        This should generally be called using the correct Ticket
        subclass, so that the ticket message args are correct.
        """
        await self.data.update(**kwargs)
        # TODO: Ticket post update and expiry update
        await self.post()

    async def post(self):
        """
        Post or update the ticket in the ticket log.
        """
        ticket_log = self.lguild.config.get(ModerationSettings.TicketLog.setting_id).value
        ticket_log: discord.TextChannel
        args = await self.make_message()
        if ticket_log:
            resend = True
            if self.data.log_msg_id:
                msg = ticket_log.get_partial_message(self.data.log_msg_id)
                try:
                    await msg.edit(**args.edit_args)
                    resend = False
                except discord.NotFound:
                    resend = True
                except discord.HTTPException:
                    resend = True
            if resend:
                try:
                    msg = await ticket_log.send(**args.send_args)
                except discord.HTTPException:
                    msg = None
                await self.data.update(log_msg_id=msg.id if msg else None)

        return None

    async def cancel_expiry(self):
        """
        Convenience method to cancel expiry of this ticket.

        Typically used when another ticket overrides the current ticket.
        Sets the ticket state to OPEN, so that it no longer expires.
        """
        if self.data.ticket_state is TicketState.EXPIRING:
            await self.data.update(ticket_state=TicketState.OPEN)
            self.expiring.cancel_tasks(self.data.ticketid)
            await self.post()

    async def _expire(self):
        """
        Actual expiry method.
        """
        if self.data.ticket_state == TicketState.EXPIRING:
            logger.debug(
                f"Expiring ticket '{self.data.ticketid}'."
            )
        try:
            await self._revert(reason="Automatic Expiry.")
        except Exception:
            logger.warning(
                "Revert failed during automatic ticket expiry. "
                "This should not happen, revert should silently fail and log. "
                f"Ticket data: {self.data}"
            )

        await self.data.update(ticket_state=TicketState.EXPIRED)
        await self.post()
        # TODO: Post an extra note to the modlog about the expiry.

    async def revert(self, reason: Optional[str] = None, **kwargs):
        """
        Revert this ticket.

        By default this is a no-op.
        Ticket types should override to implement any required revert logic.

        The optional `reason` paramter is intended for any auditable actions.
        """
        return

    async def expire(self):
        """
        Expire this ticket.

        This is a publicly exposed API,
        and the caller is responsible for checking that the ticket needs expiry.
        """
        await self._expire()

    async def pardon(self, modid: int, reason: str):
        """
        Pardon a ticket.

        Specifically, set the state of the ticket to `PARDONED`,
        with the given moderator and reason,
        and revert the ticket if applicable.

        If the ticket is already pardoned, this is a no-op.
        """
        if self.data.ticket_state != TicketState.PARDONED:
            # Cancel expiry if it was scheduled
            self.expiring.cancel_tasks(self.data.ticketid)

            # Revert the ticket if it is currently active
            if self.data.ticket_state in (TicketState.OPEN, TicketState.EXPIRING):
                await self.revert(reason=f"Pardoned by {modid}")

            # Set pardoned state
            await self.data.update(
                ticket_state=TicketState.PARDONED,
                pardoned_at=utc_now(),
                pardoned_by=modid,
                pardoned_reason=reason
            )

            # Update ticket log message
            await self.post()

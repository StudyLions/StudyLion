import asyncio
import datetime as dt
from typing import Optional

import discord
from core.lion_guild import LionGuild
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
        rows = await registry.Ticket.fetch_where(*args, **kwargs)
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
    def guild(self):
        return self.bot.get_guild(self.data.guildid)

    @property
    def target(self):
        guild = self.guild
        if guild:
            return guild.get_member(self.data.targetid)
        else:
            return None

    @property
    def type(self):
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
            timestamp=data.created_at,
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
                    "Pardoned by <&{moderator}> at {timestamp}.\n{reason}"
                )).format(
                    moderator=data.pardoned_by,
                    timestamp=discord.utils.format_dt(timestamp),
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

    async def _revert(self):
        raise NotImplementedError

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

    async def revert(self):
        """
        Revert this ticket.
        """
        raise NotImplementedError

    async def expire(self):
        """
        Expire this ticket.

        This is a publicly exposed API,
        and the caller is responsible for checking that the ticket needs expiry.
        """
        await self._expire()

    async def pardon(self):
        raise NotImplementedError

import asyncio
import logging
import traceback
import datetime

import discord

from meta import client
from data.conditions import THIS_SHARD
from settings import GuildSettings
from utils.lib import FieldEnum, strfdelta, utc_now

from .. import data
from ..module import module


class TicketType(FieldEnum):
    """
    The possible ticket types.
    """
    NOTE = 'NOTE', 'Note'
    WARNING = 'WARNING', 'Warning'
    STUDY_BAN = 'STUDY_BAN', 'Study Ban'
    MESAGE_CENSOR = 'MESSAGE_CENSOR', 'Message Censor'
    INVITE_CENSOR = 'INVITE_CENSOR', 'Invite Censor'


class TicketState(FieldEnum):
    """
    The possible ticket states.
    """
    OPEN = 'OPEN', "Active"
    EXPIRING = 'EXPIRING', "Active"
    EXPIRED = 'EXPIRED', "Expired"
    PARDONED = 'PARDONED', "Pardoned"
    REVERTED = 'REVERTED', "Reverted"


class Ticket:
    """
    Abstract base class representing a Ticketed moderation action.
    """
    # Type of event the class represents
    _ticket_type = None  # type: TicketType

    _ticket_types = {}  # Map: TicketType -> Ticket subclass

    _expiry_tasks = {}  # Map: ticketid -> expiry Task

    def __init__(self, ticketid, *args, **kwargs):
        self.ticketid = ticketid

    @classmethod
    async def create(cls, *args, **kwargs):
        """
        Method used to create a new ticket of the current type.
        Should add a row to the ticket table, post the ticket, and return the Ticket.
        """
        raise NotImplementedError

    @property
    def data(self):
        """
        Ticket row.
        This will usually be a row of `ticket_info`.
        """
        return data.ticket_info.fetch(self.ticketid)

    @property
    def guild(self):
        return client.get_guild(self.data.guildid)

    @property
    def target(self):
        guild = self.guild
        return guild.get_member(self.data.targetid) if guild else None

    @property
    def msg_args(self):
        """
        Ticket message posted in the moderation log.
        """
        args = {}

        # Build embed
        info = self.data
        member = self.target
        name = str(member) if member else str(info.targetid)

        if info.auto:
            title_fmt = "Ticket #{} | {} | {}[Auto] | {}"
        else:
            title_fmt = "Ticket #{} | {} | {} | {}"
        title = title_fmt.format(
            info.guild_ticketid,
            TicketState(info.ticket_state).desc,
            TicketType(info.ticket_type).desc,
            name
        )

        embed = discord.Embed(
            title=title,
            description=info.content,
            timestamp=info.created_at
        )
        embed.add_field(
            name="Target",
            value="<@{}>".format(info.targetid)
        )

        if not info.auto:
            embed.add_field(
                name="Moderator",
                value="<@{}>".format(info.moderator_id)
            )

        # if info.duration:
        #     value = "`{}` {}".format(
        #         strfdelta(datetime.timedelta(seconds=info.duration)),
        #         "(Expiry <t:{:.0f}>)".format(info.expiry.timestamp()) if info.expiry else ""
        #     )
        #     embed.add_field(
        #         name="Duration",
        #         value=value
        #     )
        if info.expiry:
            if info.ticket_state == TicketState.EXPIRING:
                embed.add_field(
                    name="Expires at",
                    value="<t:{:.0f}>\n(Duration: `{}`)".format(
                        info.expiry.timestamp(),
                        strfdelta(datetime.timedelta(seconds=info.duration))
                    )
                )
            elif info.ticket_state == TicketState.EXPIRED:
                embed.add_field(
                    name="Expired",
                    value="<t:{:.0f}>".format(
                        info.expiry.timestamp(),
                    )
                )
            else:
                embed.add_field(
                    name="Expiry",
                    value="<t:{:.0f}>".format(
                        info.expiry.timestamp()
                    )
                )

        if info.context:
            embed.add_field(
                name="Context",
                value=info.context,
                inline=False
            )

        if info.addendum:
            embed.add_field(
                name="Notes",
                value=info.addendum,
                inline=False
            )

        if self.state == TicketState.PARDONED:
            embed.add_field(
                name="Pardoned",
                value=(
                    "Pardoned by <@{}> at <t:{:.0f}>.\n{}"
                ).format(
                    info.pardoned_by,
                    info.pardoned_at.timestamp(),
                    info.pardoned_reason or ""
                ),
                inline=False
            )

        embed.set_footer(text="ID: {}".format(info.targetid))

        args['embed'] = embed

        # Add file
        if info.file_name:
            args['file'] = discord.File(info.file_data, info.file_name)

        return args

    @property
    def link(self):
        """
        The link to the ticket in the moderation log.
        """
        info = self.data
        modlog = GuildSettings(info.guildid).mod_log.data

        return 'https://discord.com/channels/{}/{}/{}'.format(
            info.guildid,
            modlog,
            info.log_msg_id
        )

    @property
    def state(self):
        return TicketState(self.data.ticket_state)

    @property
    def type(self):
        return TicketType(self.data.ticket_type)

    async def update(self, **kwargs):
        """
        Update ticket fields.
        """
        fields = (
            'targetid', 'moderator_id', 'auto', 'log_msg_id',
            'content', 'expiry', 'ticket_state',
            'context', 'addendum', 'duration', 'file_name', 'file_data',
            'pardoned_by', 'pardoned_at', 'pardoned_reason',
        )
        params = {field: kwargs[field] for field in fields if field in kwargs}
        if params:
            data.ticket_info.update_where(params, ticketid=self.ticketid)

        await self.update_expiry()
        await self.post()

    async def post(self):
        """
        Post or update the ticket in the moderation log.
        Also updates the saved message id.
        """
        info = self.data
        modlog = GuildSettings(info.guildid).mod_log.value
        if not modlog:
            return

        resend = True
        try:
            if info.log_msg_id:
                # Try to fetch the message
                message = await modlog.fetch_message(info.log_msg_id)
                if message:
                    if message.author.id == client.user.id:
                        # TODO: Handle file edit
                        await message.edit(embed=self.msg_args['embed'])
                        resend = False
                    else:
                        try:
                            await message.delete()
                        except discord.HTTPException:
                            pass

            if resend:
                message = await modlog.send(**self.msg_args)
                self.data.log_msg_id = message.id
        except discord.HTTPException:
            client.log(
                "Cannot post ticket (tid: {}) due to discord exception or issue.".format(self.ticketid)
            )
        except Exception:
            # This should never happen in normal operation
            client.log(
                "Error while posting ticket (tid:{})! "
                "Exception traceback follows.\n{}".format(
                    self.ticketid,
                    traceback.format_exc()
                ),
                context="TICKETS",
                level=logging.ERROR
            )

    @classmethod
    def load_expiring(cls):
        """
        Load and schedule all expiring tickets.
        """
        # TODO: Consider changing this to a flat timestamp system, to avoid storing lots of coroutines.
        # TODO: Consider only scheduling the expiries in the next day, and updating this once per day.
        # TODO: Only fetch tickets from guilds we are in.

        # Cancel existing expiry tasks
        for task in cls._expiry_tasks.values():
            if not task.done():
                task.cancel()

        # Get all expiring tickets
        expiring_rows = data.tickets.select_where(
            ticket_state=TicketState.EXPIRING,
            guildid=THIS_SHARD
        )

        # Create new expiry tasks
        now = utc_now()
        cls._expiry_tasks = {
            row['ticketid']: asyncio.create_task(
                cls._schedule_expiry_for(
                    row['ticketid'],
                    (row['expiry'] - now).total_seconds()
                )
            ) for row in expiring_rows
        }

        # Log
        client.log(
            "Loaded {} expiring tickets.".format(len(cls._expiry_tasks)),
            context="TICKET_LOADER",
        )

    @classmethod
    async def _schedule_expiry_for(cls, ticketid, delay):
        """
        Schedule expiry for a given ticketid
        """
        try:
            await asyncio.sleep(delay)
            ticket = Ticket.fetch(ticketid)
            if ticket:
                await asyncio.shield(ticket._expire())
        except asyncio.CancelledError:
            return

    def update_expiry(self):
        # Cancel any existing expiry task
        task = self._expiry_tasks.pop(self.ticketid, None)
        if task and not task.done():
            task.cancel()

        # Schedule a new expiry task, if applicable
        if self.data.ticket_state == TicketState.EXPIRING:
            self._expiry_tasks[self.ticketid] = asyncio.create_task(
                self._schedule_expiry_for(
                    self.ticketid,
                    (self.data.expiry - utc_now()).total_seconds()
                )
            )

    async def cancel_expiry(self):
        """
        Cancel ticket expiry.

        In particular, may be used if another ticket overrides `self`.
        Sets the ticket state to `OPEN`, so that it no longer expires.
        """
        if self.state == TicketState.EXPIRING:
            # Update the ticket state
            self.data.ticket_state = TicketState.OPEN

            # Remove from expiry tsks
            self.update_expiry()

            # Repost
            await self.post()

    async def _revert(self, reason=None):
        """
        Method used to revert the ticket action, e.g. unban or remove mute role.
        Generally called by `pardon` and `_expire`.

        May be overriden by the Ticket type, if they implement any revert logic.
        Is a no-op by default.
        """
        return

    async def _expire(self):
        """
        Method to automatically expire a ticket.

        May be overriden by the Ticket type for more complex expiry logic.
        Must set `data.ticket_state` to `EXPIRED` if applicable.
        """
        if self.state == TicketState.EXPIRING:
            client.log(
                "Automatically expiring ticket (tid:{}).".format(self.ticketid),
                context="TICKETS"
            )
            try:
                await self._revert(reason="Automatic Expiry")
            except Exception:
                # This should never happen in normal operation
                client.log(
                    "Error while expiring ticket (tid:{})! "
                    "Exception traceback follows.\n{}".format(
                        self.ticketid,
                        traceback.format_exc()
                    ),
                    context="TICKETS",
                    level=logging.ERROR
                )

            # Update state
            self.data.ticket_state = TicketState.EXPIRED

            # Update log message
            await self.post()

            # Post a note to the modlog
            modlog = GuildSettings(self.data.guildid).mod_log.value
            if modlog:
                try:
                    await modlog.send(
                        embed=discord.Embed(
                            colour=discord.Colour.orange(),
                            description="[Ticket #{}]({}) expired!".format(self.data.guild_ticketid, self.link)
                        )
                    )
                except discord.HTTPException:
                    pass

    async def pardon(self, moderator, reason, timestamp=None):
        """
        Pardon process for the ticket.

        May be overidden by the Ticket type for more complex pardon logic.
        Must set `data.ticket_state` to `PARDONED` if applicable.
        """
        if self.state != TicketState.PARDONED:
            if self.state in (TicketState.OPEN, TicketState.EXPIRING):
                try:
                    await self._revert(reason="Pardoned by {}".format(moderator.id))
                except Exception:
                    # This should never happen in normal operation
                    client.log(
                        "Error while pardoning ticket (tid:{})! "
                        "Exception traceback follows.\n{}".format(
                            self.ticketid,
                            traceback.format_exc()
                        ),
                        context="TICKETS",
                        level=logging.ERROR
                    )

            # Update state
            with self.data.batch_update():
                self.data.ticket_state = TicketState.PARDONED
                self.data.pardoned_at = utc_now()
                self.data.pardoned_by = moderator.id
                self.data.pardoned_reason = reason

            # Update (i.e. remove) expiry
            self.update_expiry()

            # Update log message
            await self.post()

    @classmethod
    def fetch_tickets(cls, *ticketids, **kwargs):
        """
        Fetch tickets matching the given criteria (passed transparently to `select_where`).
        Positional arguments are treated as `ticketids`, which are not supported in keyword arguments.
        """
        if ticketids:
            kwargs['ticketid'] = ticketids

        # Set the ticket type to the class type if not specified
        if cls._ticket_type and 'ticket_type' not in kwargs:
            kwargs['ticket_type'] = cls._ticket_type

        # This is actually mainly for caching, since we don't pass the data to the initialiser
        rows = data.ticket_info.fetch_rows_where(
            **kwargs
        )

        return [
            cls._ticket_types[TicketType(row.ticket_type)](row.ticketid)
            for row in rows
        ]

    @classmethod
    def fetch(cls, ticketid):
        """
        Return the Ticket with the given id, if found, or `None` otherwise.
        """
        tickets = cls.fetch_tickets(ticketid)
        return tickets[0] if tickets else None

    @classmethod
    def register_ticket_type(cls, ticket_cls):
        """
        Decorator to register a new Ticket subclass as a ticket type.
        """
        cls._ticket_types[ticket_cls._ticket_type] = ticket_cls
        return ticket_cls


@module.launch_task
async def load_expiring_tickets(client):
    Ticket.load_expiring()

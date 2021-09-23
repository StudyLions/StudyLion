import datetime

import discord

from meta import client
from settings import GuildSettings
from utils.lib import FieldEnum

from . import data


class TicketType(FieldEnum):
    """
    The possible ticket types.
    """
    NOTE = 'NOTE', 'Note'
    WARNING = 'WARNING', 'Warning'
    STUDY_BAN = 'STUDY_BAN', 'Study Ban'
    MESAGE_CENSOR = 'MESSAGE_CENSOR', 'Message Censor'
    INVITE_CENSOR = 'INVITE_CENSOR', 'Invite Censor'


class Ticket:
    """
    Abstract base class representing a Ticketed moderation action.
    """
    # Type of event the class represents
    _ticket_type = None  # type: TicketType

    _ticket_types = {}  # Map: TicketType -> Ticket subclass

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
    def member(self):
        guild = self.guild
        return guild.get_member(self.data.targetid) if guild else None

    @property
    def msg_args(self):
        """
        Ticket message posted in the moderation log.
        """
        info = self.data
        member = self.member
        name = str(member) if member else str(info.targetid)

        if info.auto:
            title_fmt = "Ticket #{} | {}[Auto] | {}"
        else:
            title_fmt = "Ticket #{} | {} | {}"
        title = title_fmt.format(
            info.guild_ticketid,
            TicketType[info.ticket_type].desc,
            name
        )

        embed = discord.Embed(
            title=title,
            description=info.content,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(
            name="Target",
            value="<@{}>".format(info.targetid)
        )
        embed.add_field(
            name="Moderator",
            value="<@{}>".format(info.moderator_id)
        )
        embed.set_footer(text="ID: {}".format(info.targetid))
        return {'embed': embed}

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
            info.list_msg_id
        )

    async def update(self, **kwargs):
        """
        Update ticket fields.
        """
        fields = (
            'targetid', 'moderator_id', 'auto', 'log_msg_id', 'content', 'expiry',
            'pardoned', 'pardoned_by', 'pardoned_at', 'pardoned_reason'
        )
        params = {field: kwargs[field] for field in fields if field in kwargs}
        if params:
            data.tickets.update_where(params, ticketid=self.ticketid)

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
        if info.log_msg_id:
            # Try to fetch the message
            message = await modlog.fetch_message(info.log_msg_id)
            if message:
                if message.author.id == client.user.id:
                    await message.edit(**self.msg_args)
                    resend = False
                else:
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass

        if resend:
            message = await modlog.send(**self.msg_args)
            self.update(log_msg_id=message.id)

    async def _expire(self):
        """
        Method to automatically expire a ticket.
        """
        raise NotImplementedError

    async def pardon(self, moderator, reason, timestamp=None):
        """
        Pardon process for the ticket.
        """
        raise NotImplementedError

    @classmethod
    def fetch_where(**kwargs):
        """
        Fetchs all tickets matching the given criteria.
        """
        ...

    @classmethod
    def fetch_by_id(*args):
        """
        Fetch the tickets with the given id(s).
        """
        ...

    @classmethod
    def register_ticket_type(cls, ticket_cls):
        """
        Decorator to register a new Ticket subclass as a ticket type.
        """
        cls._ticket_types[ticket_cls._ticket_type] = ticket_cls
        return ticket_cls


@Ticket.register_ticket_type
class StudyBanTicket(Ticket):
    _ticket_type = TicketType.STUDY_BAN

    @classmethod
    async def create(cls, guildid, targetid, moderatorid, reason, duration=None, expiry=None):
        """
        Create a new study ban ticket.
        """
        # First create the ticket itself
        ticket_row = data.tickets.insert(
            guildid=guildid,
            targetid=targetid,
            ticket_type=cls._ticket_type,
            moderator_id=moderatorid,
            auto=(moderatorid == client.user.id),
            content=reason,
            expiry=expiry
        )

        # Then create the study ban
        data.study_bans.insert(
            ticketid=ticket_row['ticketid'],
            study_ban_duration=duration,
        )

        # Create the Ticket
        ticket = cls(ticket_row['ticketid'])

        # Post the ticket
        await ticket.post()

        return ticket


# TODO Auto-expiry system for expiring tickets.

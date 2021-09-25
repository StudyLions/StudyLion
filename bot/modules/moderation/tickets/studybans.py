import datetime
import discord

from meta import client
from utils.lib import utc_now
from settings import GuildSettings
from data import NOT

from .. import data
from .Ticket import Ticket, TicketType, TicketState


@Ticket.register_ticket_type
class StudyBanTicket(Ticket):
    _ticket_type = TicketType.STUDY_BAN

    @classmethod
    async def create(cls, guildid, targetid, moderatorid, reason, expiry=None, **kwargs):
        """
        Create a new study ban ticket.
        """
        # First create the ticket itself
        ticket_row = data.tickets.insert(
            guildid=guildid,
            targetid=targetid,
            ticket_type=cls._ticket_type,
            ticket_state=TicketState.EXPIRING if expiry else TicketState.OPEN,
            moderator_id=moderatorid,
            auto=(moderatorid == client.user.id),
            content=reason,
            expiry=expiry,
            **kwargs
        )

        # Create the Ticket
        ticket = cls(ticket_row['ticketid'])

        # Schedule ticket expiry, if applicable
        if expiry:
            ticket.update_expiry()

        # Cancel any existing studyban expiry for this member
        tickets = cls.fetch_tickets(
            guildid=guildid,
            ticketid=NOT(ticket_row['ticketid']),
            targetid=targetid,
            ticket_state=TicketState.EXPIRING
        )
        for ticket in tickets:
            await ticket.cancel_expiry()

        # Post the ticket
        await ticket.post()

        # Return the ticket
        return ticket

    async def _revert(self, reason=None):
        """
        Revert the studyban by removing the role.
        """
        guild_settings = GuildSettings(self.data.guildid)
        role = guild_settings.studyban_role.value
        target = self.target

        if target and role:
            try:
                await target.remove_roles(
                    role,
                    reason="Reverting StudyBan: {}".format(reason)
                )
            except discord.HTTPException:
                # TODO: Error log?
                ...

    @classmethod
    async def autoban(cls, guild, target, reason, **kwargs):
        """
        Convenience method to automatically studyban a member, for the configured duration.
        If the role is set, this will create and return a `StudyBanTicket` regardless of whether the
        studyban was successful.
        If the role is not set, or the ticket cannot be created, this will return `None`.
        """
        # Get the studyban role, fail if there isn't one set, or the role doesn't exist
        guild_settings = GuildSettings(guild.id)
        role = guild_settings.studyban_role.value
        if not role:
            return None

        # Attempt to add the role, record failure
        try:
            await target.add_roles(role, reason="Applying StudyBan: {}".format(reason[:400]))
        except discord.HTTPException:
            role_failed = True
        else:
            role_failed = False

        # Calculate the applicable automatic duration and expiry
        # First count the existing non-pardoned studybans for this target
        studyban_count = data.tickets.select_one_where(
            guildid=guild.id,
            targetid=target.id,
            ticket_type=cls._ticket_type,
            ticket_state=NOT(TicketState.PARDONED),
            select_columns=('COUNT(*)',)
        )[0]
        studyban_count = int(studyban_count)

        # Then read the guild setting to find the applicable duration
        studyban_durations = guild_settings.studyban_durations.value
        if studyban_count < len(studyban_durations):
            duration = studyban_durations[studyban_count]
            expiry = utc_now() + datetime.timedelta(seconds=duration)
        else:
            duration = None
            expiry = None

        # Create the ticket and return
        if role_failed:
            kwargs['addendum'] = '\n'.join((
                kwargs.get('addendum', ''),
                "Could not add the studyban role! Please add the role manually and check my permissions."
            ))
        return await cls.create(
            guild.id, target.id, client.user.id, reason, duration=duration, expiry=expiry, **kwargs
        )

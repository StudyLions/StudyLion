from typing import TYPE_CHECKING
import datetime as dt

import discord
from meta import LionBot
from utils.lib import utc_now

from ..ticket import Ticket, ticket_factory
from ..data import TicketType, TicketState, ModerationData
from .. import logger, babel

if TYPE_CHECKING:
    from ..cog import ModerationCog

_p = babel._p


@ticket_factory(TicketType.NOTE)
class NoteTicket(Ticket):
    __slots__ = ()

    @classmethod
    async def create(
        cls, bot: LionBot, guildid: int, userid: int,
        moderatorid: int, content: str, expiry=None,
        **kwargs
    ):
        modcog: 'ModerationCog' = bot.get_cog('ModerationCog')
        ticket_data = await modcog.data.Ticket.create(
            guildid=guildid,
            targetid=userid,
            ticket_type=TicketType.NOTE,
            ticket_state=TicketState.OPEN,
            moderator_id=moderatorid,
            content=content,
            expiry=expiry,
            created_at=utc_now().replace(tzinfo=None),
            **kwargs
        )

        lguild = await bot.core.lions.fetch_guild(guildid)
        new_ticket = cls(lguild, ticket_data)
        await new_ticket.post()

        if expiry:
            cls.expiring.schedule_task(ticket_data.ticketid, expiry.timestamp())

        return new_ticket

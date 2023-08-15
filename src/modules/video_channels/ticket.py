import datetime as dt

import discord
from meta import LionBot
from utils.lib import utc_now

from modules.moderation.cog import ModerationCog
from modules.moderation.data import TicketType, TicketState, ModerationData
from modules.moderation.ticket import Ticket, ticket_factory

from . import babel, logger
from .settings import VideoSettings


@ticket_factory(TicketType.STUDY_BAN)
class VideoTicket(Ticket):
    __slots__ = ()

    @classmethod
    async def create(
        cls, bot: LionBot, member: discord.Member,
        moderatorid: int, reason: str, expiry=None, 
        **kwargs
    ):
        modcog: ModerationCog = bot.get_cog('ModerationCog')
        ticket_data = await modcog.data.Ticket.create(
            guildid=member.guild.id,
            targetid=member.id,
            ticket_type=TicketType.STUDY_BAN,
            ticket_state=TicketState.EXPIRING if expiry else TicketState.OPEN,
            moderator_id=moderatorid,
            auto=(moderatorid == bot.user.id),
            content=reason,
            expiry=expiry,
            **kwargs
        )

        lguild = await bot.core.lions.fetch_guild(member.guild.id, guild=member.guild)
        new_ticket = cls(lguild, ticket_data)

        # Schedule expiry if required
        if expiry:
            cls.expiring.schedule_task(ticket_data.ticketid, expiry.timestamp())

        await new_ticket.post()

        # Cancel any existent expiring video blacklists
        tickets = await cls.fetch_tickets(
            bot,
            (modcog.data.Ticket.ticketid != new_ticket.data.ticketid),
            guildid=member.guild.id,
            targetid=member.id,
            ticket_state=TicketState.EXPIRING
        )
        for ticket in tickets:
            await ticket.cancel_expiry()

        return new_ticket

    @classmethod
    async def autocreate(cls, bot: LionBot, target: discord.Member, reason: str, **kwargs):
        modcog: ModerationCog = bot.get_cog('ModerationCog')
        lguild = await bot.core.lions.fetch_guild(target.guild.id, guild=target.guild)

        blacklist = lguild.config.get(VideoSettings.VideoBlacklist.setting_id).value
        if not blacklist:
            return

        # This will propagate HTTPException if needed
        await target.add_roles(blacklist, reason=reason)

        Ticket = modcog.data.Ticket
        row = await Ticket.table.select_one_where(
            (Ticket.ticket_state != TicketState.PARDONED),
            guildid=target.guild.id,
            targetid=target.id,
            ticket_type=TicketType.STUDY_BAN,
        ).with_no_adapter().select(ticket_count="COUNT(*)")
        count = row[0]['ticket_count'] if row else 0

        durations = (await VideoSettings.VideoBlacklistDurations.get(target.guild.id)).value
        if count < len(durations):
            durations.sort()
            duration = durations[count]
            expiry = utc_now() + dt.timedelta(seconds=duration)
        else:
            duration = None
            expiry = None

        return await cls.create(
            bot, target,
            bot.user.id, reason,
            duration=duration, expiry=expiry,
            **kwargs
        )

    async def _revert(self, reason=None):
        target = self.target
        blacklist = self.lguild.config.get(VideoSettings.VideoBlacklist.setting_id).value

        # TODO: User lion.remove_role instead

        if target and blacklist in target.roles:
            try:
                await target.remove_roles(
                    blacklist,
                    reason=reason
                )
            except discord.HTTPException as e:
                logger.debug(f"Revert failed for ticket {self.data.ticketid}: {e.text}")

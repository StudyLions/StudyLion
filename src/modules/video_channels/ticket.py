import datetime as dt

import discord
from meta import LionBot
from utils.lib import utc_now

from modules.moderation.cog import ModerationCog
from modules.moderation.data import TicketType, TicketState, ModerationData
from modules.moderation.ticket import Ticket, ticket_factory

from . import babel, logger
from .settings import VideoSettings

_p = babel._p


# --- AI-MODIFIED (2026-04-17) ---
# Purpose: Add 'total_tiers' to __slots__ so autocreate() can store it
# alongside violation_number. Without this slot, the new
# `new_ticket.total_tiers = len(durations)` line in autocreate() raises
# AttributeError, propagating up through _joined_video_channel and breaking
# the auto-blacklist post-roll DM/log flow (the role gets added but
# downstream actions crash). This MUST stay in lockstep with the matching
# slot on ScreenTicket.
@ticket_factory(TicketType.STUDY_BAN)
class VideoTicket(Ticket):
    __slots__ = ('violation_number', 'total_tiers')
# --- END AI-MODIFIED ---

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

        await ticket_data.update(created_at=utc_now().replace(tzinfo=None))

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

        # --- AI-MODIFIED (2026-04-03, updated 2026-04-17) ---
        # Purpose: Store violation number AND total escalation tiers on the
        #   ticket so the blacklist DM alert can render "offense #N of M".
        new_ticket = await cls.create(
            bot, target,
            bot.user.id, reason,
            duration=duration, expiry=expiry,
            **kwargs
        )
        if new_ticket is not None:
            new_ticket.violation_number = count + 1
            new_ticket.total_tiers = len(durations)
        return new_ticket
        # --- END AI-MODIFIED --- 

    # --- AI-REPLACED (2026-04-03) ---
    # Reason: Add "blacklist lifted" DM notification when blacklist expires/pardoned,
    #   and fix bug where pardon() didn't call _revert (role wasn't removed on pardon)
    # What the new code does better: Sends a DM notification via send_alert when the
    #   blacklist is lifted, and overrides revert() so pardoning also removes the role
    # --- Original code (commented out for rollback) ---
    # async def _revert(self, reason=None):
    #     target = self.target
    #     blacklist = self.lguild.config.get(VideoSettings.VideoBlacklist.setting_id).value
    #
    #     # TODO: User lion.remove_role instead
    #
    #     if target and blacklist in target.roles:
    #         try:
    #             await target.remove_roles(
    #                 blacklist,
    #                 reason=reason
    #             )
    #         except discord.HTTPException as e:
    #             logger.debug(f"Revert failed for ticket {self.data.ticketid}: {e.text}")
    # --- End original code ---
    async def _revert(self, reason=None):
        target = self.target
        blacklist = self.lguild.config.get(VideoSettings.VideoBlacklist.setting_id).value

        reverted = False
        if target and blacklist in target.roles:
            try:
                await target.remove_roles(blacklist, reason=reason)
                reverted = True
            except discord.HTTPException as e:
                logger.debug(f"Revert failed for ticket {self.data.ticketid}: {e.text}")

        if reverted and target:
            t = self.bot.translator.t
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'video_ticket|revert|notification|title',
                    "Your blacklist has been lifted!"
                )),
                description=t(_p(
                    'video_ticket|revert|notification|desc',
                    "Your video channel blacklist in **{server}** has been lifted.\n"
                    "You may now rejoin video channels."
                )).format(server=target.guild.name),
                timestamp=utc_now()
            )
            modcog: ModerationCog = self.bot.get_cog('ModerationCog')
            if modcog:
                try:
                    await modcog.send_alert(target, embed=embed)
                except Exception:
                    logger.debug(
                        f"Could not send blacklist-lifted notification for ticket {self.data.ticketid}"
                    )

    async def revert(self, reason=None, **kwargs):
        await self._revert(reason=reason)
    # --- END AI-REPLACED ---

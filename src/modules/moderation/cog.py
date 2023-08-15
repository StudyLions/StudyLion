from typing import Optional
from collections import defaultdict
import asyncio

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from meta.sharding import THIS_SHARD
from core.data import CoreData
from utils.lib import utc_now

from wards import low_management_ward, high_management_ward, equippable_role

from . import babel, logger
from .data import ModerationData, TicketType, TicketState
from .settings import ModerationSettings
from .settingui import ModerationSettingUI
from .ticket import Ticket

_p = babel._p


class ModerationCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(ModerationData())
        self.settings = ModerationSettings()

        # TODO: Needs refactor
        self.expiring_tickets = Ticket.expiring
        self.expiring_tickets.executor = self._expiring_callback

    async def cog_load(self):
        await self.data.init()

        model_settings = (
            self.settings.TicketLog,
            self.settings.ModRole,
            self.settings.AlertChannel,
        )
        for model_setting in model_settings:
            self.bot.core.guild_config.register_model_setting(model_setting)

        configcog = self.bot.get_cog('ConfigCog')
        if configcog is None:
            logger.warning(
                "Could not load ConfigCog. "
                "Moderation configuration will not crossload."
            )
        else:
            self.crossload_group(self.configure_group, configcog.configure_group)

        if self.bot.is_ready():
            await self.initialise()

    async def cog_unload(self):
        if self.expiring_tickets._monitor_task:
            self.expiring_tickets._monitor_task.cancel()

    @LionCog.listener('on_ready')
    @log_wrap(action="Load Expiring Tickets")
    async def initialise(self):
        # Load expiring
        expiring = await Ticket.fetch_tickets(
            self.bot,
            THIS_SHARD,
            ticket_state=TicketState.EXPIRING,
        )
        tasks = [
            (ticket.data.ticketid, ticket.data.expiry.timestamp())
            for ticket in expiring if ticket.data.expiry
        ]
        logger.info(
            f"Scheduled {len(tasks)} expiring tickets."
        )
        self.expiring_tickets.schedule_tasks(*tasks)
        self.expiring_tickets.start()

    async def _expiring_callback(self, ticketid: int):
        ticket = await Ticket.fetch_ticket(self.bot, ticketid)
        if ticket.data.ticket_state is not TicketState.EXPIRING:
            return
        now = utc_now()
        if ticket.data.expiry > now:
            logger.info(
                f"Rescheduling expiry for ticket '{ticketid}' "
                f"which expires later {ticket.data.expiry}"
            )
            self.expiring_tickets.schedule_task(ticketid, ticket.data.expiry.timestamp())
        else:
            logger.info(
                f"Running expiry task for ticket '{ticketid}'"
            )
            await ticket.expire()

    # ----- API -----
    async def send_alert(self, member: discord.Member, **kwargs) -> Optional[discord.Message]:
        """
        Send a moderation alert to the specified member.

        Sends the alert directly to the member if possible,
        otherwise to the configured `alert_channel`.

        Takes into account the member notification preferences (TODO)
        """
        try:
            return await member.send(**kwargs)
        except discord.HTTPException:
            alert_channel = await self.settings.AlertChannel.get(member.guild.id)
            if alert_channel:
                try:
                    return await alert_channel.send(content=member.mention, **kwargs)
                except discord.HTTPException:
                    pass

    async def get_ticket_webhook(self, guild: discord.Guild):
        """
        Get the ticket log webhook data, if it exists.

        If it does not exist, but the ticket channel is set, tries to create it.
        """
        ...

    # ----- Commands -----

    # ----- Configuration -----
    @LionCog.placeholder_group
    @cmds.hybrid_group('configure', with_app_command=False)
    async def configure_group(self, ctx: LionContext):
        ...

    @configure_group.command(
        name=_p('cmd:configure_moderation', "moderation"),
        description=_p(
            'cmd:configure_moderation|desc',
            "Configure general moderation settings."
        )
    )
    @appcmds.rename(
        modrole=ModerationSettings.ModRole._display_name,
        ticket_log=ModerationSettings.TicketLog._display_name,
        alert_channel=ModerationSettings.AlertChannel._display_name,
    )
    @appcmds.describe(
        modrole=ModerationSettings.ModRole._desc,
        ticket_log=ModerationSettings.TicketLog._desc,
        alert_channel=ModerationSettings.AlertChannel._desc,
    )
    @high_management_ward
    async def configure_moderation(self, ctx: LionContext,
                                   modrole: Optional[discord.Role] = None,
                                   ticket_log: Optional[discord.TextChannel] = None,
                                   alert_channel: Optional[discord.TextChannel] = None,
                                   ):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        await ctx.interaction.response.defer(thinking=True)

        modified = []

        if modrole is not None:
            setting = self.settings.ModRole
            await setting._check_value(ctx.guild.id, modrole)
            instance = setting(ctx.guild.id, modrole.id)
            modified.append(instance)

        if ticket_log is not None:
            setting = self.settings.TicketLog
            await setting._check_value(ctx.guild.id, ticket_log)
            instance = setting(ctx.guild.id, ticket_log.id)
            modified.append(instance)

        if alert_channel is not None:
            setting = self.settings.AlertChannel
            await setting._check_value(ctx.guild.id, alert_channel)
            instance = setting(ctx.guild.id, alert_channel.id)
            modified.append(instance)

        if modified:
            ack_lines = []
            update_args = {}

            # All settings are guild model settings so we can simultaneously write
            for instance in modified:
                update_args[instance._column] = instance.data
                ack_lines.append(instance.update_message)

            # Do the ack
            tick = self.bot.config.emojis.tick
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description='\n'.join(f"{tick} {line}" for line in ack_lines)
            )
            await ctx.reply(embed=embed)

            # Dispatch updates to any listeners
            for instance in modified:
                instance.dispatch_update()

        if ctx.channel.id not in ModerationSettingUI._listening or not modified:
            ui = ModerationSettingUI(self.bot, ctx.guild.id, ctx.channel.id)
            await ui.run(ctx.interaction)
            await ui.wait()

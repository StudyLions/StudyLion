from typing import Optional
from collections import defaultdict
import asyncio

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.ui.text_input import TextInput, TextStyle

from meta import LionCog, LionBot, LionContext
from meta.errors import SafeCancellation, UserInputError
from meta.logger import log_wrap
from meta.sharding import THIS_SHARD
from core.data import CoreData
from utils.lib import utc_now, parse_ranges, parse_time_static
from utils.ui import input

from wards import low_management_ward, high_management_ward, equippable_role, moderator_ward

from . import babel, logger
from .data import ModerationData, TicketType, TicketState
from .settings import ModerationSettings
from .settingui import ModerationSettingUI
from .ticket import Ticket
from .tickets import NoteTicket, WarnTicket
from .ticketui import TicketListUI, TicketFilter

_p, _np = babel._p, babel._np


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
            self.crossload_group(self.configure_group, configcog.admin_config_group)

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
            alert_channel = (await self.settings.AlertChannel.get(member.guild.id)).value
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
    # modnote command
    @cmds.hybrid_command(
        name=_p('cmd:modnote', "modnote"),
        description=_p(
            'cmd:modnote|desc',
            "Add a note to the target member's moderation record."
        )
    )
    @appcmds.rename(
        target=_p('cmd:modnote|param:target', "target"),
        note=_p('cmd:modnote|param:note', "note"),
    )
    @appcmds.describe(
        target=_p(
            'cmd:modnote|param:target|desc',
            "Target member or user to add a note to."
        ),
        note=_p(
            'cmd:modnote|param:note|desc',
            "Contents of the note."
        ),
    )
    @appcmds.default_permissions(manage_guild=True)
    @appcmds.guild_only
    @moderator_ward
    async def cmd_modnote(self, ctx: LionContext,
                          target: discord.Member | discord.User,
                          note: Optional[appcmds.Range[str, 1, 1024]] = None,
                          ):
        """
        Create a NoteTicket on the given target.

        If `note` is not given, prompts for the note content via modal.
        """
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        if note is None:
            # Prompt for note via modal
            modal_title = t(_p(
                'cmd:modnote|modal:enter_note|title',
                "Moderation Note"
            ))
            input_field = TextInput(
                label=t(_p(
                    'cmd:modnote|modal:enter_note|field|label',
                    "Note Content",
                )),
                style=TextStyle.long,
                min_length=1,
                max_length=1024,
            )
            try:
                interaction, note = await input(
                    ctx.interaction, modal_title,
                    field=input_field,
                    timeout=300
                )
            except asyncio.TimeoutError:
                # Moderator did not fill in the modal in time
                # Just leave quietly
                raise SafeCancellation
        else:
            interaction = ctx.interaction

        await interaction.response.defer(thinking=True, ephemeral=True)

        # Create NoteTicket
        ticket = await NoteTicket.create(
            bot=self.bot,
            guildid=ctx.guild.id, userid=target.id,
            moderatorid=ctx.author.id, content=note, expiry=None
        )

        # Write confirmation with ticket number and link to ticket if relevant
        embed = discord.Embed(
            colour=discord.Colour.orange(),
            description=t(_p(
                'cmd:modnote|embed:success|desc',
                "Moderation note created as [Ticket #{ticket}]({jump_link})"
            )).format(
                ticket=ticket.data.guild_ticketid,
                jump_link=ticket.jump_url or ctx.message.jump_url
            )
        )
        await interaction.edit_original_response(embed=embed)

    # Warning Ticket Command
    @cmds.hybrid_command(
        name=_p('cmd:warning', "warning"),
        description=_p(
            'cmd:warning|desc',
            "Warn a member for a misdemeanour, and add it to their moderation record."
        )
    )
    @appcmds.rename(
        target=_p('cmd:warning|param:target', "target"),
        reason=_p('cmd:warning|param:reason', "reason"),
    )
    @appcmds.describe(
        target=_p(
            'cmd:warning|param:target|desc',
            "Target member to warn."
        ),
        reason=_p(
            'cmd:warning|param:reason|desc',
            "The reason why you are warning this member."
        ),
    )
    @appcmds.default_permissions(manage_guild=True)
    @appcmds.guild_only
    @moderator_ward
    async def cmd_warning(self, ctx: LionContext,
                          target: discord.Member,
                          reason: Optional[appcmds.Range[str, 0, 1024]] = None,
                          ):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        # Prompt for warning reason if not given
        if reason is None:
            modal_title = t(_p(
                'cmd:warning|modal:reason|title',
                "Moderation Warning"
            ))
            input_field = TextInput(
                label=t(_p(
                    'cmd:warning|modal:reason|field|label',
                    "Reason for the warning (visible to user)."
                )),
                style=TextStyle.long,
                min_length=0,
                max_length=1024,
            )
            try:
                interaction, note = await input(
                    ctx.interaction, modal_title,
                    field=input_field,
                    timeout=300,
                )
            except asyncio.TimeoutError:
                raise SafeCancellation
        else:
            interaction = ctx.interaction

        await interaction.response.defer(thinking=True, ephemeral=False)

        # Create WarnTicket
        ticket = await WarnTicket.create(
            bot=self.bot,
            guildid=ctx.guild.id, userid=target.id,
            moderatorid=ctx.author.id, content=reason
        )

        # Post to user or moderation notify channel
        alert_embed = discord.Embed(
            colour=discord.Colour.dark_red(),
            title=t(_p(
                'cmd:warning|embed:user_alert|title',
                "You have received a warning!"
            )),
            description=reason,
        )
        alert_embed.add_field(
            name=t(_p(
                'cmd:warning|embed:user_alert|field:note|name',
                "Note"
            )),
            value=t(_p(
                'cmd:warning|embed:user_alert|field:note|value',
                "*Warnings appear in your moderation history."
                " Continuing failure to comply with server rules and moderator"
                " directions may result in more severe action."
            ))
        )
        alert_embed.set_footer(
            icon_url=ctx.guild.icon,
            text=ctx.guild.name,
        )
        alert = await self.send_alert(target, embed=alert_embed)

        # Ack the ticket creation, including alert status and warning count

        warning_count = await ticket.count_warnings_for(
            self.bot, ctx.guild.id, target.id
        )
        count_line = t(_np(
            'cmd:warning|embed:success|line:count',
            "This their first warning.",
            "They have recieved **`{count}`** warnings.",
            warning_count
        )).format(count=warning_count)

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            description=t(_p(
                'cmd:warning|embed:success|desc',
                "[Ticket #{ticket}]({jump_link}) {user} has been warned."
            )).format(
                ticket=ticket.data.guild_ticketid,
                jump_link=ticket.jump_url or ctx.message.jump_url,
                user=target.mention,
            ) + '\n' + count_line
        )
        if alert is None:
            embed.add_field(
                name=t(_p(
                    'cmd:warning|embed:success|field:no_alert|name',
                    "Note"
                )),
                value=t(_p(
                    'cmd:warning|embed:success|field:no_alert|value',
                    "*Could not deliver warning to the target.*"
                ))
            )
        await interaction.edit_original_response(embed=embed)

    # Pardon user command
    @cmds.hybrid_command(
        name=_p('cmd:pardon', "pardon"),
        description=_p(
            'cmd:pardon|desc',
            "Pardon moderation tickets to mark them as no longer in effect."
        )
    )
    @appcmds.rename(
        ticketids=_p(
            'cmd:pardon|param:ticketids',
            "tickets"
        ),
        reason=_p(
            'cmd:pardon|param:reason',
            "reason"
        )
    )
    @appcmds.describe(
        ticketids=_p(
            'cmd:pardon|param:ticketids|desc',
            "Comma separated list of ticket numbers to pardon."
        ),
        reason=_p(
            'cmd:pardon|param:reason',
            "Why these tickets are being pardoned."
        )
    )
    @appcmds.default_permissions(manage_guild=True)
    @appcmds.guild_only
    @moderator_ward
    async def cmd_pardon(self, ctx: LionContext,
                         ticketids: str,
                         reason: Optional[appcmds.Range[str, 0, 1024]] = None,
                         ):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        # Prompt for pardon reason if not given
        # Note we can't parse first since we need to do first response with the modal
        if reason is None:
            modal_title = t(_p(
                'cmd:pardon|modal:reason|title',
                "Pardon Tickets"
            ))
            input_field = TextInput(
                label=t(_p(
                    'cmd:pardon|modal:reason|field|label',
                    "Why are you pardoning these tickets?"
                )),
                style=TextStyle.long,
                min_length=0,
                max_length=1024,
            )
            try:
                interaction, reason = await input(
                    ctx.interaction, modal_title, field=input_field, timeout=300,
                )
            except asyncio.TimeoutError:
                raise SafeCancellation
        else:
            interaction = ctx.interaction

        await interaction.response.defer(thinking=True)

        # Parse provided ticketids
        try:
            parsed_ids = parse_ranges(ticketids)
            errored = False
        except ValueError:
            errored = True
            parsed_ids = []

        if errored or not parsed_ids:
            raise UserInputError(t(_p(
                'cmd:pardon|error:parse_ticketids',
                "Could not parse provided tickets as a list of ticket ids!"
                " Please enter tickets as a comma separated list of ticket numbers,"
                " for example `1, 2, 3`."
            )))

        # Now find these tickets
        tickets = await Ticket.fetch_tickets(
            bot=self.bot,
            guildid=ctx.guild.id,
            guild_ticketid=parsed_ids,
        )
        if not tickets:
            raise UserInputError(t(_p(
                'cmd:pardon|error:no_matching',
                "No matching moderation tickets found to pardon!"
            )))

        # Pardon each ticket
        for ticket in tickets:
            await ticket.pardon(
                modid=ctx.author.id,
                reason=reason
            )

        # Now ack the pardon
        count = len(tickets)
        ticketstr = ', '.join(
            f"[#{ticket.data.guild_ticketid}]({ticket.jump_url})" for ticket in tickets
        )

        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            description=t(_np(
                'cmd:pardon|embed:success|title',
                "Ticket {ticketstr} has been pardoned.",
                "The following tickets have been pardoned:\n{ticketstr}",
                count
            )).format(ticketstr=ticketstr)
        )
        await interaction.edit_original_response(embed=embed)

    # View tickets 
    @cmds.hybrid_command(
        name=_p('cmd:tickets', "tickets"),
        description=_p(
            'cmd:tickets|desc',
            "View moderation tickets in this server."
        )
    )
    @appcmds.rename(
        target_user=_p('cmd:tickets|param:target', "target"),
        ticket_type=_p('cmd:tickets|param:type', "type"),
        ticket_state=_p('cmd:tickets|param:state', "ticket_state"),
        include_pardoned=_p('cmd:tickets|param:pardoned', "include_pardoned"),
        acting_moderator=_p('cmd:tickets|param:moderator', "acting_moderator"),
        after=_p('cmd:tickets|param:after', "after"),
        before=_p('cmd:tickets|param:before', "before"),
    )
    @appcmds.describe(
        target_user=_p(
            'cmd:tickets|param:target|desc',
            "Filter by tickets acting on a given user."
        ),
        ticket_type=_p(
            'cmd:tickets|param:type|desc',
            "Filter by ticket type."
        ),
        ticket_state=_p(
            'cmd:tickets|param:state|desc',
            "Filter by ticket state."
        ),
        include_pardoned=_p(
            'cmd:tickets|param:pardoned|desc',
            "Whether to only show active tickets, or also include pardoned."
        ),
        acting_moderator=_p(
            'cmd:tickets|param:moderator|desc',
            "Filter by moderator responsible for the ticket."
        ),
        after=_p(
            'cmd:tickets|param:after|desc',
            "Only show tickets after this date (YYY-MM-DD HH:MM)"
        ),
        before=_p(
            'cmd:tickets|param:before|desc',
            "Only show tickets before this date (YYY-MM-DD HH:MM)"
        ),
    )
    @appcmds.choices(
        ticket_type=[
            appcmds.Choice(name=typ.name, value=typ.name)
            for typ in (TicketType.NOTE, TicketType.WARNING, TicketType.STUDY_BAN)
        ],
        ticket_state=[
            appcmds.Choice(name=state.name, value=state.name)
            for state in (
                TicketState.OPEN, TicketState.EXPIRING, TicketState.EXPIRED, TicketState.PARDONED,
            )
        ]
    )
    @appcmds.default_permissions(manage_guild=True)
    @appcmds.guild_only
    @moderator_ward
    async def tickets_cmd(self, ctx: LionContext,
                          target_user: Optional[discord.User] = None,
                          ticket_type: Optional[appcmds.Choice[str]] = None,
                          ticket_state: Optional[appcmds.Choice[str]] = None,
                          include_pardoned: Optional[bool] = None,
                          acting_moderator: Optional[discord.User] = None,
                          after: Optional[str] = None,
                          before: Optional[str] = None,
                          ):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        filters = TicketFilter(self.bot)
        if target_user is not None:
            filters.targetids = [target_user.id]
        if ticket_type is not None:
            filters.types = [TicketType[ticket_type.value]]
        if ticket_state is not None:
            filters.states = [TicketState[ticket_state.value]]
        elif include_pardoned:
            filters.states = None
        else:
            filters.states = [TicketState.OPEN, TicketState.EXPIRING]
        if acting_moderator is not None:
            filters.moderatorids = [acting_moderator.id]
        if after is not None:
            filters.after = await parse_time_static(after, ctx.lguild.timezone)
        if before is not None:
            filters.before = await parse_time_static(before, ctx.lguild.timezone)
        

        ticketsui = TicketListUI(self.bot, ctx.guild, ctx.author.id, filters=filters)
        await ticketsui.run(ctx.interaction)
        await ticketsui.wait()

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
        adminrole=ModerationSettings.AdminRole._display_name,
        modrole=ModerationSettings.ModRole._display_name,
        ticket_log=ModerationSettings.TicketLog._display_name,
        alert_channel=ModerationSettings.AlertChannel._display_name,
    )
    @appcmds.describe(
        adminrole=ModerationSettings.AdminRole._desc,
        ticket_log=ModerationSettings.TicketLog._desc,
        alert_channel=ModerationSettings.AlertChannel._desc,
    )
    @high_management_ward
    async def configure_moderation(self, ctx: LionContext,
                                   modrole: Optional[discord.Role] = None,
                                   ticket_log: Optional[discord.TextChannel] = None,
                                   alert_channel: Optional[discord.TextChannel] = None,
                                   adminrole: Optional[discord.Role] = None,
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

        if adminrole is not None:
            setting = self.settings.AdminRole
            await setting._check_value(ctx.guild.id, adminrole)
            instance = setting(ctx.guild.id, adminrole.id)
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

            await ctx.lguild.data.update(**update_args)

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

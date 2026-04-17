from typing import Optional
from collections import defaultdict
import asyncio
import datetime as dt

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.ui.text_input import TextInput, TextStyle

from meta import LionCog, LionBot, LionContext
from meta.errors import SafeCancellation, UserInputError
from meta.logger import log_wrap
from meta.sharding import THIS_SHARD
from core.data import CoreData
from utils.lib import utc_now, parse_ranges, parse_time_static, strfdelta
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
        # --- AI-MODIFIED (2026-04-02) ---
        # Purpose: Reject bot targets to prevent AttributeError on ClientUser.create_dm
        if target.bot:
            await ctx.reply(
                "You cannot warn a bot!",
                ephemeral=True
            )
            return
        # --- END AI-MODIFIED ---
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
            for typ in (TicketType.NOTE, TicketType.WARNING, TicketType.STUDY_BAN, TicketType.SCREEN_BAN)
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

    # ============================================================
    # AI-GENERATED COMMAND BLOCK (2026-04-17)
    # Purpose: New /strikes <user> command — single-screen disciplinary
    #   summary for a target showing per-type ticket counts, the configured
    #   blacklist escalation ladders (with current tier marked), the
    #   currently-active blacklist (if any), and the most recent offences.
    #   Designed so mods don't have to manually scroll /tickets to figure out
    #   "is this a 1st-time offender or a repeat one?".
    # ============================================================
    _STRIKES_BLACKLIST_TIER_TABLES = {
        TicketType.STUDY_BAN: ('studyban_durations', 'Video Blacklist'),
        TicketType.SCREEN_BAN: ('screenban_durations', 'Screen Blacklist'),
    }
    _STRIKES_TYPE_DISPLAY = {
        TicketType.NOTE: 'Notes',
        TicketType.WARNING: 'Warnings',
        TicketType.STUDY_BAN: 'Video Blacklists',
        TicketType.SCREEN_BAN: 'Screen Blacklists',
        TicketType.MESSAGE_CENSOR: 'Message Censors',
        TicketType.INVITE_CENSOR: 'Invite Censors',
    }

    @staticmethod
    def _strikes_format_duration(seconds: int) -> str:
        if seconds is None:
            return 'Permanent'
        if seconds <= 0:
            return '0s'
        return strfdelta(dt.timedelta(seconds=seconds), short=True).strip()

    async def _strikes_fetch_tier_durations(self, guildid: int, table_name: str) -> list[int]:
        # --- AI-MODIFIED (2026-04-17) ---
        # Reason: psycopg3's default cursor uses dict_row, so r[0] raises
        #         KeyError(0). Use the column name instead.
        try:
            async with self.bot.db.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"SELECT duration FROM {table_name} "
                        f"WHERE guildid = %s ORDER BY rowid",
                        (guildid,),
                    )
                    rows = await cur.fetchall()
        except Exception:
            logger.exception(
                f"Failed to fetch tier ladder for guild {guildid} from {table_name}"
            )
            return []
        result: list[int] = []
        for r in rows:
            dur = r['duration'] if isinstance(r, dict) else r[0]
            if dur is None:
                continue
            try:
                result.append(int(dur))
            except (TypeError, ValueError):
                continue
        return result
        # --- END AI-MODIFIED ---

    @cmds.hybrid_command(
        name=_p('cmd:strikes', "strikes"),
        description=_p(
            'cmd:strikes|desc',
            "View a member's full strike record: counts, tier ladder, recent offences."
        )
    )
    @appcmds.rename(
        target=_p('cmd:strikes|param:target', "target"),
    )
    @appcmds.describe(
        target=_p(
            'cmd:strikes|param:target|desc',
            "Member or user to look up the strike record for."
        ),
    )
    @appcmds.default_permissions(manage_guild=True)
    @appcmds.guild_only
    @moderator_ward
    async def cmd_strikes(self, ctx: LionContext,
                          target: discord.Member | discord.User):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        await ctx.interaction.response.defer(thinking=True, ephemeral=False)

        all_tickets = await Ticket.fetch_tickets(
            self.bot,
            guildid=ctx.guild.id,
            targetid=target.id,
        )

        if not all_tickets:
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'cmd:strikes|embed:clean|title',
                    "{user} has a clean record."
                )).format(user=str(target)),
                description=t(_p(
                    'cmd:strikes|embed:clean|desc',
                    "No moderation tickets have ever been recorded for this member in **{guild}**."
                )).format(guild=ctx.guild.name),
            )
            embed.set_footer(text=f"ID: {target.id}")
            try:
                avatar = target.display_avatar.url
                embed.set_thumbnail(url=avatar)
            except Exception:
                pass
            await ctx.interaction.edit_original_response(embed=embed)
            return

        counts = defaultdict(lambda: {'total': 0, 'active': 0, 'pardoned': 0})
        active_expiries: dict[TicketType, Optional[dt.datetime]] = {}
        active_count_by_type: dict[TicketType, int] = defaultdict(int)
        for ticket in all_tickets:
            d = ticket.data
            counts[d.ticket_type]['total'] += 1
            if d.ticket_state is TicketState.PARDONED:
                counts[d.ticket_type]['pardoned'] += 1
            else:
                counts[d.ticket_type]['active'] += 1

            if d.ticket_state in (TicketState.OPEN, TicketState.EXPIRING):
                if d.ticket_type in self._STRIKES_BLACKLIST_TIER_TABLES:
                    current = active_expiries.get(d.ticket_type)
                    candidate_expiry = d.expiry
                    if current is None or (
                        candidate_expiry is None
                    ) or (
                        current is not None and candidate_expiry is not None
                        and candidate_expiry > current
                    ):
                        active_expiries[d.ticket_type] = candidate_expiry
                    active_count_by_type[d.ticket_type] += 1

        ladders: dict[TicketType, list[int]] = {}
        for typ, (table, _label) in self._STRIKES_BLACKLIST_TIER_TABLES.items():
            durations = await self._strikes_fetch_tier_durations(ctx.guild.id, table)
            if durations:
                durations.sort()
            ladders[typ] = durations

        currently_blacklisted = bool(active_expiries)
        if currently_blacklisted:
            colour = discord.Colour.dark_red()
            heading_emoji = '🚫'
        elif counts.get(TicketType.WARNING, {}).get('active', 0) > 0:
            colour = discord.Colour.orange()
            heading_emoji = '⚠️'
        else:
            colour = discord.Colour.blurple()
            heading_emoji = '📋'

        embed = discord.Embed(
            colour=colour,
            title=t(_p(
                'cmd:strikes|embed|title',
                "{emoji} Strike Record — {user}"
            )).format(emoji=heading_emoji, user=str(target)),
            timestamp=utc_now(),
        )
        try:
            embed.set_thumbnail(url=target.display_avatar.url)
        except Exception:
            pass
        embed.set_footer(text=f"ID: {target.id}  ·  {len(all_tickets)} total tickets")

        summary_order = (
            TicketType.STUDY_BAN,
            TicketType.SCREEN_BAN,
            TicketType.WARNING,
            TicketType.NOTE,
        )
        summary_lines = []
        for typ in summary_order:
            label = self._STRIKES_TYPE_DISPLAY.get(typ, typ.name)
            c = counts.get(typ, {'total': 0, 'active': 0, 'pardoned': 0})
            if c['total'] == 0:
                summary_lines.append(f"`{label:<18}`  —  none")
            else:
                summary_lines.append(
                    f"`{label:<18}`  —  **{c['active']}** active · {c['pardoned']} pardoned · {c['total']} total"
                )
        embed.add_field(
            name=t(_p('cmd:strikes|field:summary|name', "Summary")),
            value='\n'.join(summary_lines),
            inline=False,
        )

        for typ in (TicketType.STUDY_BAN, TicketType.SCREEN_BAN):
            label = self._STRIKES_BLACKLIST_TIER_TABLES[typ][1]
            type_total_active = counts.get(typ, {}).get('active', 0)
            durations = ladders.get(typ, [])
            if not durations and type_total_active == 0:
                continue

            ladder_parts = []
            for idx, dur in enumerate(durations):
                fmt = self._strikes_format_duration(dur)
                if idx == type_total_active and type_total_active < len(durations):
                    ladder_parts.append(f"**▶ {fmt}**")
                else:
                    ladder_parts.append(fmt)
            ladder_parts.append('Permanent' if type_total_active < len(durations) else '**▶ Permanent**')

            ladder_str = ' → '.join(ladder_parts) if durations else (
                t(_p('cmd:strikes|field:ladder|value:permanent_only',
                     "No tier ladder configured — every offence is a permanent blacklist."))
            )

            if type_total_active >= len(durations) and durations:
                next_descr = t(_p(
                    'cmd:strikes|field:ladder|next:permanent',
                    "Next offence: **Permanent** (escalation ladder exhausted)."
                ))
            elif durations:
                next_dur = durations[type_total_active]
                next_descr = t(_p(
                    'cmd:strikes|field:ladder|next:duration',
                    "Next offence: **{duration}** (tier {tier} of {total})"
                )).format(
                    duration=self._strikes_format_duration(next_dur),
                    tier=type_total_active + 1,
                    total=len(durations),
                )
            else:
                next_descr = ''

            current_expiry = active_expiries.get(typ)
            if typ in active_expiries:
                if current_expiry is not None:
                    active_line = t(_p(
                        'cmd:strikes|field:ladder|active:expiring',
                        "Currently blacklisted — expires {when}."
                    )).format(when=discord.utils.format_dt(current_expiry, 'R'))
                else:
                    active_line = t(_p(
                        'cmd:strikes|field:ladder|active:permanent',
                        "Currently blacklisted — **permanent**."
                    ))
            else:
                active_line = ''

            value_lines = []
            if active_line:
                value_lines.append(active_line)
            if ladder_str:
                value_lines.append(ladder_str)
            if next_descr:
                value_lines.append(next_descr)

            embed.add_field(
                name=t(_p('cmd:strikes|field:ladder|name', "{label} Ladder")).format(label=label),
                value='\n'.join(value_lines) or 'No data.',
                inline=False,
            )

        recent = all_tickets[:5]
        recent_lines = []
        for ticket in recent:
            d = ticket.data
            content = (d.content or '').strip().replace('\n', ' ')
            if len(content) > 80:
                content = content[:77] + '...'
            elif not content:
                content = '*no content*'
            jump = ticket.jump_url
            ticket_link = f"[#{d.guild_ticketid}]({jump})" if jump else f"#{d.guild_ticketid}"
            line = (
                f"• {ticket_link} · {discord.utils.format_dt(d.created_at, 'd')} "
                f"· `{d.ticket_type.name}[{d.ticket_state.name}]` · {content}"
            )
            if d.ticket_state is TicketState.PARDONED:
                line = f"~~{line}~~"
            recent_lines.append(line)

        embed.add_field(
            name=t(_p('cmd:strikes|field:recent|name', "Recent (last {n})")).format(n=len(recent)),
            value='\n'.join(recent_lines) or t(_p(
                'cmd:strikes|field:recent|value:empty',
                "No recent tickets."
            )),
            inline=False,
        )

        await ctx.interaction.edit_original_response(embed=embed)
    # ============================================================
    # END AI-GENERATED COMMAND BLOCK
    # ============================================================

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

from typing import Optional
import gc
import sys
import asyncio
import logging

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from data.queries import ORDER
from utils.lib import tabulate

from wards import low_management
from meta import LionBot, LionCog, LionContext, WEBSITE_URL
from data import Table
from utils.ui import AButton, AsComponents
from utils.lib import utc_now

from . import babel
from .helpui import HelpUI

_p = babel._p

logger = logging.getLogger(__name__)


created = utc_now()
guide_link = "https://discord.studylions.com/tutorial"

# --- AI-REPLACED (2026-03-22) ---
# Reason: Old Discord CDN GIF URL returned 404 (dead attachment)
# What the new code does better: Removed broken image entirely; the rich
# embed (6 feature fields + 4 link buttons + author + footer) is informative
# enough without a hero image.
# --- Original code (commented out for rollback) ---
# animation_link = (
#     "https://media.discordapp.net/attachments/879412267731542047/926837189814419486/ezgif.com-resize.gif"
# )
# ONBOARDING_HERO_GIF = (
#     "https://media.discordapp.net/attachments/879412267731542047/926837189814419486/ezgif.com-resize.gif"
# )
# FEATURE_GIF_STUDY = ONBOARDING_HERO_GIF
# FEATURE_GIF_RANKS = ONBOARDING_HERO_GIF
# FEATURE_GIF_ECONOMY = ONBOARDING_HERO_GIF
# FEATURE_GIF_PET = ONBOARDING_HERO_GIF
# FEATURE_GIF_POMODORO = ONBOARDING_HERO_GIF
# --- End original code ---
# --- END AI-REPLACED ---


class MetaCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot

    @cmds.hybrid_command(
        name=_p('cmd:help', "help"),
        description=_p(
            'cmd:help|desc',
            "See a brief summary of my commands and features."
        )
    )
    async def help_cmd(self, ctx: LionContext):
        if not ctx.interaction:
            return
        await ctx.interaction.response.defer(thinking=True, ephemeral=True)
        ui = HelpUI(
            ctx.bot,
            ctx.author,
            ctx.guild,
            show_admin=await low_management(ctx.bot, ctx.author, ctx.guild),
        )
        await ui.run(ctx.interaction)

    # --- AI-REPLACED (2026-03-20) ---
    # Reason: Old join message was a plain text embed with no buttons, no DM, no channel fallback
    # What the new code does better: Rich feature showcase embed with link buttons,
    #     DM to server owner with setup guide, and smart channel fallback logic
    # --- Original code (commented out for rollback) ---
    # @LionCog.listener('on_guild_join')
    # async def post_join_message(self, guild: discord.Guild):
    #     logger.debug(f"Sending join message to <gid: {guild.id}>")
    #     t = self.bot.translator.t
    #     message = t(_p(
    #         'new_guild_join_message|desc',
    #         "Thank you for inviting me to your community!\n"
    #         "Get started by typing {help_cmd} to see my commands,"
    #         " and {dash_cmd} to view and set up my configuration options!\n\n"
    #         "If you need any help configuring me,"
    #         " or would like to suggest a feature,"
    #         " report a bug, and stay updated,"
    #         " make sure to join our main support server by [clicking here]({support})."
    #     )).format(
    #         dash_cmd=self.bot.core.mention_cmd('dashboard'),
    #         help_cmd=self.bot.core.mention_cmd('help'),
    #         support=self.bot.config.bot.support_guild,
    #     )
    #     try:
    #         await guild.me.edit(nick="Leo")
    #     except discord.HTTPException:
    #         pass
    #     if (channel := guild.system_channel) and channel.permissions_for(guild.me).embed_links:
    #         embed = discord.Embed(
    #             description=message,
    #             colour=discord.Colour.orange(),
    #         )
    #         embed.set_author(
    #             name=t(_p(
    #                 'new_guild_join_message|name',
    #                 "Hello everyone! My name is Leo, the LionBot!"
    #             )),
    #             icon_url="https://cdn.discordapp.com/emojis/933610591459872868.webp"
    #         )
    #         embed.set_image(url=animation_link)
    #         try:
    #             await channel.send(embed=embed)
    #         except discord.HTTPException:
    #             logger.warning(
    #                 f"Could not send join message to <gid: {guild.id}>",
    #                 exc_info=True,
    #             )
    # --- End original code ---

    @staticmethod
    def _can_send_embeds(channel: discord.TextChannel) -> bool:
        perms = channel.permissions_for(channel.guild.me)
        return perms.send_messages and perms.embed_links

    def _find_welcome_channel(self, guild: discord.Guild):
        for ch in [guild.system_channel, guild.rules_channel]:
            if ch and self._can_send_embeds(ch):
                return ch
        for ch in guild.text_channels:
            if self._can_send_embeds(ch):
                return ch
        return None

    # --- AI-REPLACED (2026-03-26) ---
    # Reason: Updated button labels -- "Explore Features" -> "Admin Tutorial", "Support Server" -> "Report a Bug / Ask for Help"
    # --- Original code (commented out for rollback) ---
    # def _build_welcome_view(self, guild: discord.Guild) -> discord.ui.View:
    #     setup_url = f"{WEBSITE_URL}/dashboard/servers/{guild.id}/setup"
    #     features_url = f"{WEBSITE_URL}/features"
    #     support_url = str(self.bot.config.bot.support_guild)
    #     donate_url = f"{WEBSITE_URL}/donate"
    #     view = discord.ui.View()
    #     view.add_item(discord.ui.Button(label="Quick Setup", emoji="\U0001FA84", url=setup_url, style=discord.ButtonStyle.link))
    #     view.add_item(discord.ui.Button(label="Explore Features", emoji="\u2728", url=features_url, style=discord.ButtonStyle.link))
    #     view.add_item(discord.ui.Button(label="Support Server", emoji="\U0001F91D", url=support_url, style=discord.ButtonStyle.link))
    #     view.add_item(discord.ui.Button(label="Support Leo", emoji="\u2764\uFE0F", url=donate_url, style=discord.ButtonStyle.link))
    #     return view
    # --- End original code ---
    def _build_welcome_view(self, guild: discord.Guild) -> discord.ui.View:
        # --- AI-REPLACED (2026-04-29) ---
        # Reason: Setup Wizard was rebranded as "Setup Checklist" and the
        #         primary onboarding UI moved from the standalone /setup page
        #         to a checklist widget on the server overview. Deep-linking
        #         with ?setup=open auto-opens the checklist for the admin.
        # What the new code does better: Drops admins straight into the new
        #         mobile-first checklist UI (progress, jargon tooltips, per-task
        #         drawers, "configured / skipped / done" pills). Old /setup is
        #         still reachable as deprecated guided tour but no longer the
        #         default entry point from the welcome DM/channel message.
        # --- Original code (commented out for rollback) ---
        # setup_url = f"{WEBSITE_URL}/dashboard/servers/{guild.id}/setup"
        # --- End original code ---
        setup_url = f"{WEBSITE_URL}/dashboard/servers/{guild.id}?setup=open"
        # --- END AI-REPLACED ---
        tutorials_url = f"{WEBSITE_URL}/tutorials"
        support_url = str(self.bot.config.bot.support_guild)
        donate_url = f"{WEBSITE_URL}/donate"

        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            # --- AI-REPLACED (2026-04-29) ---
            # Reason: Match the new "Setup Checklist" branding shown in the
            #         dashboard sidebar + widget heading. Switched the magic-wand
            #         emoji (\U0001FA84) to a check-mark (\u2705) so the button's
            #         visual cue matches what the user sees on landing.
            # --- Original code (commented out for rollback) ---
            # label="Quick Setup", emoji="\U0001FA84",
            # --- End original code ---
            label="Setup Checklist", emoji="\u2705",
            # --- END AI-REPLACED ---
            url=setup_url, style=discord.ButtonStyle.link,
        ))
        view.add_item(discord.ui.Button(
            label="Admin Tutorial", emoji="\U0001F4D6",
            url=tutorials_url, style=discord.ButtonStyle.link,
        ))
        view.add_item(discord.ui.Button(
            label="Report a Bug / Ask for Help", emoji="\U0001F41B",
            url=support_url, style=discord.ButtonStyle.link,
        ))
        view.add_item(discord.ui.Button(
            label="Support Leo", emoji="\u2764\uFE0F",
            url=donate_url, style=discord.ButtonStyle.link,
        ))
        return view
    # --- END AI-REPLACED ---

    @LionCog.listener('on_guild_join')
    async def post_join_message(self, guild: discord.Guild):
        logger.debug(f"Sending join message to <gid: {guild.id}>")

        try:
            await guild.me.edit(nick="Leo")
        except discord.HTTPException:
            pass

        t = self.bot.translator.t

        # --- AI-REPLACED (2026-03-26) ---
        # Reason: Shorter, warmer join message focused on family-business identity and asking users not to remove Leo
        # What the new code does better: Less text clutter, emotional tone, encourages opening a ticket instead of removing
        # --- Original code (commented out for rollback) ---
        # embed = discord.Embed(
        #     description=t(_p(
        #         'new_guild_join_message|desc',
        #         "Thank you for adding me to **{server_name}**! "
        #         "I'm a powerful productivity and engagement bot that helps "
        #         "gamify your server with activity tracking, rewards, and more.\n\n"
        #         "Use {help_cmd} to explore commands, or click **Quick Setup** below "
        #         "to configure me on the web in under 2 minutes!"
        #     )).format(server_name=guild.name, help_cmd=self.bot.core.mention_cmd('help')),
        #     colour=discord.Colour.orange(),
        # )
        # embed.set_author(name=t(_p('new_guild_join_message|name', "Hello everyone! I'm Leo, the LionBot!")),
        #     icon_url="https://cdn.discordapp.com/emojis/933610591459872868.webp")
        # embed.add_field(name="\U0001F4CA Study Tracking", value="Track voice & text activity, earn hourly coin rewards, and camera bonuses", inline=True)
        # embed.add_field(name="\U0001F3C6 Ranks & Leaderboards", value="Competitive rank progression, profile cards, and server-wide leaderboards", inline=True)
        # embed.add_field(name="\U0001F4B0 Economy & Shop", value="Virtual currency, colour role shop, room rentals, and coin transfers", inline=True)
        # embed.add_field(name="\U0001F345 Pomodoro Timers", value="Focus sessions with streaks, milestones, and voice channel integration", inline=True)
        # embed.add_field(name="\U0001F981 LionGotchi", value="Virtual pet companion with farming, crafting, equipment, and marketplace", inline=True)
        # embed.add_field(name="\u2699\uFE0F And Much More", value="Moderation, role menus, video channels, schedules, tasks, and reminders", inline=True)
        # embed.set_footer(text=f"Set up in under 2 minutes \u2022 {WEBSITE_URL}")
        # --- End original code ---
        embed = discord.Embed(
            description=t(_p(
                'new_guild_join_message|desc',
                "Thanks for adding Leo to **{server_name}**! "
                "Leo is built with love by a small family team \u2014 "
                "this project means the world to us.\n\n"
                "Leo is in active development with new features landing regularly. "
                "If you run into a bug or need help setting up, "
                "please don't remove Leo \u2014 join our server and open a ticket. "
                "We're here to help personally!\n\n"
                # --- AI-MODIFIED (2026-04-29) ---
                # Purpose: Match new button label (was "Quick Setup") + soften
                # the "in under 2 minutes" claim. The new checklist has 8 tasks
                # (6 required + 2 optional) and most admins take 4-8 minutes if
                # they read each task carefully. "A few minutes" is honest
                # without scaring anyone off.
                "Use {help_cmd} to explore commands, or click **Setup Checklist** "
                "below to get started in just a few minutes."
                # --- END AI-MODIFIED ---
            )).format(
                server_name=guild.name,
                help_cmd=self.bot.core.mention_cmd('help'),
            ),
            colour=discord.Colour.orange(),
        )
        embed.set_author(
            name=t(_p(
                'new_guild_join_message|name',
                "Hello everyone! I'm Leo, the LionBot!"
            )),
            icon_url="https://cdn.discordapp.com/emojis/933610591459872868.webp",
        )
        # --- AI-MODIFIED (2026-04-29) ---
        # Purpose: Match the body copy (which dropped the "2 minutes" claim).
        embed.set_footer(text=f"Set up in just a few minutes \u2022 {WEBSITE_URL}")
        # --- END AI-MODIFIED ---
        # --- END AI-REPLACED ---

        view = self._build_welcome_view(guild)

        channel = self._find_welcome_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed, view=view)
            except discord.HTTPException:
                logger.warning(
                    f"Could not send join message to <gid: {guild.id}>",
                    exc_info=True,
                )

        owner = guild.owner
        if not owner:
            try:
                owner = await self.bot.fetch_user(guild.owner_id)
            except discord.HTTPException:
                owner = None

        # --- AI-REPLACED (2026-03-26) ---
        # Reason: Shorter, warmer DM to server owner with family-business tone
        # --- Original code (commented out for rollback) ---
        # if owner:
        #     dm_embed = discord.Embed(
        #         description=t(_p('new_guild_join_dm|desc',
        #             "Thanks for adding Leo to **{server_name}**! "
        #             "Here's how to get started:\n\n"
        #             "**1.** Click **Quick Setup** below to configure your server on the web dashboard in under 2 minutes\n\n"
        #             "**2.** Or use {dash_cmd} in Discord to manage settings at a glance\n\n"
        #             "**3.** Need help? Join our support server \u2014 our team is happy to assist!\n\n"
        #             "Once set up, your members can start earning rewards, climbing ranks, and more right away!"
        #         )).format(server_name=guild.name, dash_cmd=self.bot.core.mention_cmd('dashboard')),
        #         colour=discord.Colour.orange(),
        #     )
        #     dm_embed.set_author(name=t(_p('new_guild_join_dm|name', "Welcome to LionBot!")),
        #         icon_url="https://cdn.discordapp.com/emojis/933610591459872868.webp")
        #     dm_embed.set_footer(text=f"Set up {guild.name} \u2022 {WEBSITE_URL}")
        #     dm_view = self._build_welcome_view(guild)
        #     try:
        #         await owner.send(embed=dm_embed, view=dm_view)
        #     except discord.HTTPException:
        #         logger.debug(f"Could not DM owner of <gid: {guild.id}>")
        # --- End original code ---
        if owner:
            dm_embed = discord.Embed(
                description=t(_p(
                    'new_guild_join_dm|desc',
                    "Thanks for adding Leo to **{server_name}**! "
                    "We're a small family team and we genuinely care about "
                    "every server that uses Leo.\n\n"
                    # --- AI-MODIFIED (2026-04-29) ---
                    # Purpose: Match new button label (was "Quick Setup") +
                    # soften the time-to-setup claim. See body-copy comment
                    # for the channel embed above for rationale.
                    "Click **Setup Checklist** below to configure your server "
                    "in just a few minutes. If you run into any issues, "
                    # --- END AI-MODIFIED ---
                    "please don't hesitate to reach out \u2014 "
                    "we're always happy to help!"
                )).format(
                    server_name=guild.name,
                ),
                colour=discord.Colour.orange(),
            )
            dm_embed.set_author(
                name=t(_p(
                    'new_guild_join_dm|name',
                    "Welcome to LionBot!"
                )),
                icon_url="https://cdn.discordapp.com/emojis/933610591459872868.webp",
            )
            dm_embed.set_footer(text=f"Set up {guild.name} \u2022 {WEBSITE_URL}")

            dm_view = self._build_welcome_view(guild)

            try:
                await owner.send(embed=dm_embed, view=dm_view)
            except discord.HTTPException:
                logger.debug(
                    f"Could not DM owner of <gid: {guild.id}>"
                )
        # --- END AI-REPLACED ---
    # --- END AI-REPLACED ---

    @cmds.hybrid_command(
        name=_p('cmd:invite', "invite"),
        description=_p(
            'cmd:invite|desc',
            "Invite LionBot to your own server."
        )
    )
    async def invite_cmd(self, ctx: LionContext):
        t = self.bot.translator.t

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            description=t(_p(
                'cmd:invite|embed|desc',
                "[Click here]({invite_link}) to add me to your server."
            )).format(
                invite_link=self.bot.config.bot.invite_bot,
            )
        )
        embed.add_field(
            name=t(_p(
                'cmd:invite|embed|field:tips|name',
                "Setup Tips"
            )),
            value=t(_p(
                'cmd:invite|embed|field:tips|value',
                "Remember to check out {help_cmd} for the important command list,"
                " including the admin page which displays the hidden admin-level"
                " configuration commands like {dashboard}!\n"
                "Also, if you have any issues or questions,"
                " you can join our [support server]({support_link}) to talk to our friendly"
                " support team!"
            )).format(
                help_cmd=self.bot.core.mention_cmd('help'),
                dashboard=self.bot.core.mention_cmd('dashboard'),
                support_link=self.bot.config.bot.support_guild,
            )
        )
        await ctx.reply(embed=embed, ephemeral=True)

    @cmds.hybrid_command(
        name=_p('cmd:support', "support"),
        description=_p(
            'cmd:support|desc',
            "Have an issue or a question? Speak to my friendly support team here."
        )
    )
    async def support_cmd(self, ctx: LionContext):
        t = self.bot.translator.t
        await ctx.reply(
            t(_p(
                'cmd:support|response',
                "Speak to my friendly support team by joining this server and making a ticket"
                " in the support channel!\n"
                "{support_link}"
            )).format(support_link=self.bot.config.bot.support_guild),
            ephemeral=True,
        )

    @cmds.hybrid_command(
        name=_p('cmd:nerd', "nerd"),
        description=_p(
            'cmd:nerd|desc',
            "View hidden details and statistics about me ('nerd statistics')",
        )
    )
    async def nerd_cmd(self, ctx: LionContext):
        t = self.bot.translator.t

        if ctx.interaction:
            await ctx.interaction.response.defer(thinking=True)

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=t(_p(
                'cmd:nerd|title',
                "Nerd Statistics"
            )),
        )
        if ctx.guild:
            embed.set_footer(
                text=f"Your guildid: {ctx.guild.id}"
            )
        else:
            embed.set_footer(
                text="Sent from direct message"
            )

        # Bot Stats
        bot_stats_lines = []

        # Currently {n} people active in {m} rooms of {n} guilds
        query = await Table('voice_sessions_ongoing').bind(self.bot.db).select_one_where(
        ).select(
            total_users='COUNT(userid)',
            total_rooms='COUNT(channelid)',
            total_guilds='COUNT(guildid)',
        )
        bot_stats_lines.append((
            t(_p('cmd:nerd|field:currently|name', "Currently")),
            t(_p(
                'cmd:nerd|field:currently|value',
                "`{people}` people active in `{rooms}` rooms of `{guilds}` guilds."
            )).format(
                people=query['total_users'],
                rooms=query['total_rooms'],
                guilds=query['total_guilds']
            )
        ))

        # Recorded {h} voice hours from {n} people across {n} sessions
        query = await Table('voice_sessions').bind(self.bot.db).select_one_where(
        ).select(
            total_hours='SUM(duration) / 3600',
            total_users='COUNT(userid)',
            total_sessions='COUNT(*)',
        )
        bot_stats_lines.append((
            t(_p('cmd:nerd|field:recorded|name', "Recorded")),
            t(_p(
                'cmd:nerd|field:recorded|value',
                "`{hours}` voice hours from `{users}` people across `{sessions}` sessions."
            )).format(
                hours=query['total_hours'],
                users=query['total_users'],
                sessions=query['total_sessions'],
            )
        ))

        # Registered {n} users and {m} guilds
        query1 = await Table('user_config').bind(self.bot.db).select_one_where(
        ).select(total_users='COUNT(*)')
        query2 = await Table('guild_config').bind(self.bot.db).select_one_where(
        ).select(total_guilds='COUNT(*)')
        bot_stats_lines.append((
            t(_p('cmd:nerd|field:registered|name', "Registered")),
            t(_p(
                'cmd:nerd|field:registered|value',
                "`{users}` users and `{guilds}` guilds."
            )).format(
                users=query1['total_users'],
                guilds=query2['total_guilds'],
            )
        ))

        # {n} tasks completed out of {m}
        query = await Table('tasklist').bind(self.bot.db).select_one_where(
        ).select(
            total_tasks='COUNT(*)',
            total_completed='COUNT(*) filter (WHERE completed_at IS NOT NULL)',
        )
        bot_stats_lines.append((
            t(_p('cmd:nerd|field:tasks|name', "Tasks")),
            t(_p(
                'cmd:nerd|field:tasks|value',
                "`{tasks}` tasks completed out of `{total}`."
            )).format(
                tasks=query['total_completed'], total=query['total_tasks']
            )
        ))

        # {m} timers running across {n} guilds
        query = await Table('timers').bind(self.bot.db).select_one_where(
        ).select(
            total_timers='COUNT(*)',
            guilds='COUNT(guildid)'
        )
        bot_stats_lines.append((
            t(_p('cmd:nerd|field:timers|name', "Timers")),
            t(_p(
                'cmd:nerd|field:timers|value',
                "`{timers}` timers running across `{guilds}` guilds."
            )).format(
                timers=query['total_timers'],
                guilds=query['guilds'],
            )
        ))

        bot_stats_section = '\n'.join(tabulate(*bot_stats_lines))
        embed.add_field(
            name=t(_p('cmd:nerd|section:bot_stats|name', "Bot Stats")),
            value=bot_stats_section,
            inline=False,
        )

        # ----- Process -----
        process_lines = []

        # Shard {n} of {n}
        process_lines.append((
            t(_p('cmd:nerd|field:shard|name', "Shard")),
            t(_p(
                'cmd:nerd|field:shard|value',
                "`{shard_number}` of `{shard_count}`"
            )).format(shard_number=self.bot.shard_id, shard_count=self.bot.shard_count)
        ))

        # Guilds
        process_lines.append((
            t(_p('cmd:nerd|field:guilds|name', "Guilds")),
            t(_p(
                'cmd:nerd|field:guilds|value',
                "`{guilds}` guilds with `{count}` total members."
            )).format(
                guilds=len(self.bot.guilds),
                count=sum(guild.member_count or 0 for guild in self.bot.guilds)
            )
        ))

        # Version
        version = await self.bot.db.version()
        process_lines.append((
            t(_p('cmd:nerd|field:version|name', "Leo Version")),
            t(_p(
                'cmd:nerd|field:version|value',
                "`v{version}`, last updated {timestamp} from `{reason}`."
            )).format(
                version=version.version,
                timestamp=discord.utils.format_dt(version.time, 'D'),
                reason=version.author,
            )
        ))

        # Py version
        py_version = sys.version.split()[0]
        dpy_version = discord.__version__
        process_lines.append((
            t(_p('cmd:nerd|field:py_version|name', "Py Version")),
            t(_p(
                'cmd:nerd|field:py_version|value',
                "`{py_version}` running discord.py `{dpy_version}`"
            )).format(
                py_version=py_version, dpy_version=dpy_version,
            )
        ))

        process_section = '\n'.join(tabulate(*process_lines))
        embed.add_field(
            name=t(_p('cmd:nerd|section:process_section|name', "Process")),
            value=process_section,
            inline=False,
        )

        # ----- Shard Statistics -----
        shard_lines = []

        # Handling `n` events
        shard_lines.append((
            t(_p('cmd:nerd|field:handling|name', "Handling")),
            t(_p(
                'cmd:nerd|field:handling|name',
                "`{events}` active commands and events."
            )).format(
                events=len(self.bot._running_events)
            ),
        ))

        # Working on n background tasks
        shard_lines.append((
            t(_p('cmd:nerd|field:working|name', "Working On")),
            t(_p(
                'cmd:nerd|field:working|value',
                "`{tasks}` background tasks."
            )).format(tasks=len(asyncio.all_tasks()))
        ))

        # Count objects in memory
        shard_lines.append((
            t(_p('cmd:nerd|field:objects|name', "Objects")),
            t(_p(
                'cmd:nerd|field:objects|value',
                "`{objects}` loaded in memory."
            )).format(objects=gc.get_count())
        ))

        # Uptime
        uptime = int((utc_now() - created).total_seconds())
        uptimestr = (
            f"`{uptime // (24 * 3600)}` days, `{uptime // 3600 % 24:02}:{uptime // 60 % 60:02}:{uptime % 60:02}`"
        )
        shard_lines.append((
            t(_p('cmd:nerd|field:uptime|name', "Uptime")),
            uptimestr,
        ))

        shard_section = '\n'.join(tabulate(*shard_lines))
        embed.add_field(
            name=t(_p('cmd:nerd|section:shard_section|name', "Shard Statistics")),
            value=shard_section,
            inline=False,
        )

        await ctx.reply(embed=embed)

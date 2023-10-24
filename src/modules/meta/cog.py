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
from meta import LionBot, LionCog, LionContext
from data import Table
from utils.ui import AButton, AsComponents
from utils.lib import utc_now

from . import babel
from .helpui import HelpUI

_p = babel._p

logger = logging.getLogger(__name__)


created = utc_now()
guide_link = "https://discord.studylions.com/tutorial"

animation_link = (
    "https://media.discordapp.net/attachments/879412267731542047/926837189814419486/ezgif.com-resize.gif"
)


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

    @LionCog.listener('on_guild_join')
    async def post_join_message(self, guild: discord.Guild):
        logger.debug(f"Sending join message to <gid: {guild.id}>")
        # Send join message
        t = self.bot.translator.t
        message = t(_p(
            'new_guild_join_message|desc',
            "Thank you for inviting me to your community!\n"
            "Get started by typing {help_cmd} to see my commands,"
            " and {dash_cmd} to view and set up my configuration options!\n\n"
            "If you need any help configuring me,"
            " or would like to suggest a feature,"
            " report a bug, and stay updated,"
            " make sure to join our main support server by [clicking here]({support})."
        )).format(
            dash_cmd=self.bot.core.mention_cmd('dashboard'),
            help_cmd=self.bot.core.mention_cmd('help'),
            support=self.bot.config.bot.support_guild,
        )
        try:
            await guild.me.edit(nick="Leo")
        except discord.HTTPException:
            pass
        if (channel := guild.system_channel) and channel.permissions_for(guild.me).embed_links:
            embed = discord.Embed(
                description=message,
                colour=discord.Colour.orange(),
            )
            embed.set_author(
                name=t(_p(
                    'new_guild_join_message|name',
                    "Hello everyone! My name is Leo, the LionBot!"
                )),
                icon_url="https://cdn.discordapp.com/emojis/933610591459872868.webp"
            )
            embed.set_image(url=animation_link)

            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                logger.warning(
                    f"Could not send join message to <gid: {guild.id}>",
                    exc_info=True,
                )

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

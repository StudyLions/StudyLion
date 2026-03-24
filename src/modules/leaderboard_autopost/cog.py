# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-21
# Purpose: Leaderboard auto-post cog - scheduled posting,
#          role management, coin rewards, DMs, and action queue
# ============================================================
import asyncio
import calendar
import datetime as dt
import io
import json
import traceback
from typing import Optional, List, Dict, Any, Tuple

import discord
from discord.ext import commands as cmds

from meta import LionBot, LionCog
from meta.logger import log_wrap
from utils.lib import utc_now
from modules.economy.data import EconomyData, TransactionType
from modules.statistics.data import StatsData

from . import logger
from .data import AutopostData
from .templates import (
    build_variables, build_dm_variables, render_template,
    truncate, TYPE_LABELS, TYPE_UNITS, FREQUENCY_LABELS,
    DISCORD_LIMITS,
)


def _now_in_tz(tz_name: Optional[str]) -> dt.datetime:
    """Get current time in a named timezone, falling back to UTC."""
    import zoneinfo
    try:
        tz = zoneinfo.ZoneInfo(tz_name) if tz_name else dt.timezone.utc
    except Exception:
        tz = dt.timezone.utc
    return dt.datetime.now(tz)


def _compute_period_bounds(
    config, guild_tz: Optional[str], season_start: Optional[dt.datetime],
) -> Tuple[dt.datetime, dt.datetime, str]:
    """
    Compute (period_start, period_end, human_period_str) based on
    config frequency, guild timezone, and scheduling options.
    Returns timezone-aware datetimes in guild TZ.
    """
    import zoneinfo
    try:
        tz = zoneinfo.ZoneInfo(guild_tz) if guild_tz else dt.timezone.utc
    except Exception:
        tz = dt.timezone.utc

    now = dt.datetime.now(tz)

    freq = config.frequency

    if freq == 'daily':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + dt.timedelta(days=1)
        period_str = start.strftime('%B %d, %Y')

    elif freq == 'weekly':
        ws = config.week_starts_on or 'monday'
        if ws == 'sunday':
            week_start_dow = 6
        elif ws == 'match_dashboard':
            week_start_dow = 0
        else:
            week_start_dow = 0

        current_dow = now.weekday()
        days_back = (current_dow - week_start_dow) % 7
        start = (now - dt.timedelta(days=days_back)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = start + dt.timedelta(days=7)
        end_display = end - dt.timedelta(days=1)
        period_str = f"{start.strftime('%B %d')} to {end_display.strftime('%B %d, %Y')}"

    elif freq == 'monthly':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end = start.replace(year=now.year + 1, month=1)
        else:
            end = start.replace(month=now.month + 1)
        period_str = now.strftime('%B %Y')

    elif freq == 'seasonal':
        mode = config.seasonal_mode or 'guild_season'
        if mode == 'calendar_quarter':
            q = (now.month - 1) // 3
            q_start_month = q * 3 + 1
            start = now.replace(
                month=q_start_month, day=1,
                hour=0, minute=0, second=0, microsecond=0
            )
            if q_start_month + 3 > 12:
                end = start.replace(year=now.year + 1, month=1)
            else:
                end = start.replace(month=q_start_month + 3)
            quarter_names = {0: 'Q1', 1: 'Q2', 2: 'Q3', 3: 'Q4'}
            period_str = f"{quarter_names[q]} {now.year}"
        else:
            if season_start and season_start.tzinfo is None:
                season_start = season_start.replace(tzinfo=tz)
            start = season_start or dt.datetime(2020, 1, 1, tzinfo=tz)
            end = now
            period_str = f"Season (from {start.strftime('%B %d, %Y')})"
    else:
        start = dt.datetime(2020, 1, 1, tzinfo=tz)
        end = now
        period_str = "All Time"

    return start, end, period_str


def _period_already_posted(config, period_start: dt.datetime) -> bool:
    """Check if the config already posted for this period.
    
    Also returns True for brand-new configs (created_at within the current
    period and no prior post) so the first run waits for the NEXT scheduled
    time instead of firing immediately upon creation.
    """
    if config.last_posted_at is None:
        if config.created_at is not None:
            ca = config.created_at
            if ca.tzinfo is None:
                ca = ca.replace(tzinfo=dt.timezone.utc)
            ps = period_start
            if ps.tzinfo is None:
                ps = ps.replace(tzinfo=dt.timezone.utc)
            if ca >= ps:
                return True
        return False
    lp = config.last_posted_at
    if lp.tzinfo is None:
        lp = lp.replace(tzinfo=dt.timezone.utc)
    ps = period_start
    if ps.tzinfo is None:
        ps = ps.replace(tzinfo=dt.timezone.utc)
    return lp >= ps


# --- AI-REPLACED (2026-03-22) ---
# Reason: Original required exact day-of-week/month match, so posts were
#   silently skipped if the bot was down for the entire scheduled day.
# What the new code does better: Computes the scheduled datetime within
#   the current period and checks now >= scheduled_dt, allowing catchup
#   after downtime without waiting for the next period.
# --- Original code (commented out for rollback) ---
# def _should_post_now(config, guild_tz: Optional[str]) -> bool:
#     """Determine if a config is due for posting right now."""
#     now = _now_in_tz(guild_tz)
#     freq = config.frequency
#     post_hour = config.post_hour or 20
#     post_minute = config.post_minute or 0
#     if freq == 'daily':
#         if now.hour < post_hour or (now.hour == post_hour and now.minute < post_minute):
#             return False
#     elif freq == 'weekly':
#         post_day = config.post_day if config.post_day is not None else 0
#         ws = config.week_starts_on or 'monday'
#         if ws == 'sunday':
#             target_dow = (post_day + 6) % 7
#         else:
#             target_dow = post_day
#         if now.weekday() != target_dow:
#             return False
#         if now.hour < post_hour or (now.hour == post_hour and now.minute < post_minute):
#             return False
#     elif freq == 'monthly':
#         post_day = config.post_day if config.post_day is not None else 1
#         last_day = calendar.monthrange(now.year, now.month)[1]
#         actual_day = min(post_day, last_day)
#         if now.day != actual_day:
#             return False
#         if now.hour < post_hour or (now.hour == post_hour and now.minute < post_minute):
#             return False
#     elif freq == 'seasonal':
#         mode = config.seasonal_mode or 'guild_season'
#         if mode == 'calendar_quarter':
#             q = (now.month - 1) // 3
#             q_end_month = q * 3 + 3
#             last_day_qe = calendar.monthrange(now.year, q_end_month)[1]
#             if now.month != q_end_month or now.day != last_day_qe:
#                 return False
#             if now.hour < post_hour or (now.hour == post_hour and now.minute < post_minute):
#                 return False
#     period_start, _, _ = _compute_period_bounds(config, guild_tz, None)
#     return not _period_already_posted(config, period_start)
# --- End original code ---
def _should_post_now(config, guild_tz: Optional[str]) -> bool:
    """Determine if a config is due for posting right now.

    Computes the exact scheduled datetime within the current period and
    checks ``now >= scheduled_dt``.  This allows the bot to catch up on
    missed posts after downtime instead of silently skipping the period.
    """
    import zoneinfo
    try:
        tz = zoneinfo.ZoneInfo(guild_tz) if guild_tz else dt.timezone.utc
    except Exception:
        tz = dt.timezone.utc

    now = dt.datetime.now(tz)
    freq = config.frequency
    post_hour = config.post_hour or 20
    post_minute = config.post_minute or 0

    period_start, _, _ = _compute_period_bounds(config, guild_tz, None)

    if freq == 'daily':
        scheduled_dt = now.replace(
            hour=post_hour, minute=post_minute, second=0, microsecond=0,
        )

    elif freq == 'weekly':
        post_day = config.post_day if config.post_day is not None else 0
        ws = config.week_starts_on or 'monday'
        if ws == 'sunday':
            target_dow = (post_day + 6) % 7
        else:
            target_dow = post_day

        days_ahead = (target_dow - period_start.weekday()) % 7
        scheduled_dt = (period_start + dt.timedelta(days=days_ahead)).replace(
            hour=post_hour, minute=post_minute, second=0, microsecond=0,
        )

    elif freq == 'monthly':
        post_day = config.post_day if config.post_day is not None else 1
        last_day = calendar.monthrange(now.year, now.month)[1]
        actual_day = min(post_day, last_day)
        scheduled_dt = now.replace(
            day=actual_day, hour=post_hour, minute=post_minute,
            second=0, microsecond=0,
        )

    elif freq == 'seasonal':
        mode = config.seasonal_mode or 'guild_season'
        if mode == 'calendar_quarter':
            q = (now.month - 1) // 3
            q_end_month = q * 3 + 3
            last_day_qe = calendar.monthrange(now.year, q_end_month)[1]
            scheduled_dt = now.replace(
                month=q_end_month, day=last_day_qe,
                hour=post_hour, minute=post_minute,
                second=0, microsecond=0,
            )
        else:
            scheduled_dt = now.replace(
                hour=post_hour, minute=post_minute,
                second=0, microsecond=0,
            )
    else:
        scheduled_dt = now.replace(
            hour=post_hour, minute=post_minute,
            second=0, microsecond=0,
        )

    if now < scheduled_dt:
        return False

    return not _period_already_posted(config, period_start)
# --- END AI-REPLACED ---


class LeaderboardAutopostCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data: AutopostData = bot.db.load_registry(AutopostData())
        self._autopost_task: Optional[asyncio.Task] = None
        self._action_task: Optional[asyncio.Task] = None

    # --- AI-MODIFIED (2026-03-21) ---
    # Purpose: Premium-only gate for leaderboard autopost
    async def _is_premium(self, guildid: int) -> bool:
        premcog = self.bot.get_cog('PremiumCog')
        if not premcog:
            return False
        try:
            return await premcog.is_premium_guild(guildid)
        except Exception:
            return False
    # --- END AI-MODIFIED ---

    async def cog_load(self):
        if self.bot.shard_id != 0:
            logger.debug(
                f"Leaderboard autopost: not shard 0 (shard {self.bot.shard_id}), skipping loops."
            )
            return

        self._autopost_task = asyncio.create_task(self._autopost_loop())
        self._action_task = asyncio.create_task(self._action_queue_loop())
        logger.info("Leaderboard autopost loops started on shard 0.")

    async def cog_unload(self):
        for task in (self._autopost_task, self._action_task):
            if task and not task.done():
                task.cancel()

    # ─── Main scheduled loop ────────────────────────────────────

    async def _autopost_loop(self):
        """Check all enabled configs every 60s and post when due."""
        try:
            await self.bot.wait_until_ready()
            await asyncio.sleep(30)

            while True:
                try:
                    configs = await self.data.Config.fetch_enabled()
                    for config in configs:
                        try:
                            # --- AI-MODIFIED (2026-03-21) ---
                            # Purpose: Skip non-premium guilds
                            if not await self._is_premium(config.guildid):
                                continue
                            # --- END AI-MODIFIED ---
                            lguild = await self.bot.core.lions.fetch_guild(config.guildid)
                            guild_tz = lguild.data.timezone if lguild else None
                            if _should_post_now(config, guild_tz):
                                season_start = lguild.data.season_start if lguild else None
                                await self._execute_post(config, guild_tz, season_start)
                        except Exception:
                            logger.error(
                                f"Autopost error for config {config.configid}",
                                exc_info=True,
                            )
                except Exception:
                    logger.error("Autopost loop iteration error", exc_info=True)

                await asyncio.sleep(60)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.error("Fatal error in autopost loop", exc_info=True)

    # ─── Action queue consumer ──────────────────────────────────

    async def _action_queue_loop(self):
        """Poll the action queue every 20s for test/run_now/simulate requests."""
        try:
            await self.bot.wait_until_ready()
            await asyncio.sleep(15)

            while True:
                try:
                    await self.data.ActionQueue.expire_stale(300)

                    action = await self.data.ActionQueue.claim_pending()
                    if action:
                        await self._handle_action(action)
                except Exception:
                    logger.error("Action queue loop error", exc_info=True)

                await asyncio.sleep(20)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.error("Fatal error in action queue loop", exc_info=True)

    async def _handle_action(self, action):
        """Dispatch an action from the queue."""
        try:
            config = None
            if action.configid:
                rows = await self.data.Config.fetch_where(configid=action.configid)
                config = rows[0] if rows else None

            if not config:
                await action.update(
                    status='failed',
                    result=json.dumps({'error': 'Config not found'}),
                    processed_at=utc_now(),
                )
                return

            # --- AI-MODIFIED (2026-03-21) ---
            # Purpose: Reject actions for non-premium guilds
            if not await self._is_premium(config.guildid):
                await action.update(
                    status='failed',
                    result=json.dumps({'error': 'This feature requires a premium server subscription'}),
                    processed_at=utc_now(),
                )
                return
            # --- END AI-MODIFIED ---

            lguild = await self.bot.core.lions.fetch_guild(config.guildid)
            guild_tz = lguild.data.timezone if lguild else None
            season_start = lguild.data.season_start if lguild else None

            if action.action_type == 'test':
                await self._execute_post(
                    config, guild_tz, season_start, is_test=True
                )
                await action.update(
                    status='done', processed_at=utc_now(),
                )

            elif action.action_type == 'run_now':
                await self._execute_post(
                    config, guild_tz, season_start, is_run_now=True
                )
                await action.update(
                    status='done', processed_at=utc_now(),
                )

            elif action.action_type == 'simulate':
                result = await self._execute_simulate(config, guild_tz, season_start)
                await action.update(
                    status='done',
                    result=json.dumps(result, default=str),
                    processed_at=utc_now(),
                )
            else:
                await action.update(
                    status='failed',
                    result=json.dumps({'error': f'Unknown action: {action.action_type}'}),
                    processed_at=utc_now(),
                )
        except Exception as e:
            logger.error(f"Error handling action {action.queueid}", exc_info=True)
            try:
                await action.update(
                    status='failed',
                    result=json.dumps({'error': str(e)}),
                    processed_at=utc_now(),
                )
            except Exception:
                pass

    # ─── Core execution ─────────────────────────────────────────

    async def _fetch_leaderboard(
        self, config, period_start: dt.datetime,
    ) -> List[Tuple[int, int]]:
        """
        Fetch leaderboard data: list of (userid, value) sorted desc.
        value = seconds (study), msg count or xp (messages), coins (coins).
        """
        guildid = config.guildid
        lb_type = config.lb_type or 'study'

        if lb_type == 'study':
            return await StatsData.VoiceSessionStats.leaderboard_since(
                guildid, period_start
            )
        elif lb_type == 'messages':
            metric = config.messages_metric or 'count'
            if metric == 'xp':
                return await StatsData.MemberExp.leaderboard_since(
                    guildid, period_start
                )
            else:
                from tracking.text.data import TextTrackerData
                return await TextTrackerData.TextSessions.leaderboard_since(
                    guildid, period_start
                )
        elif lb_type == 'coins':
            async with self.data.Config._connector.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT userid, COALESCE(coins, 0) as value
                        FROM members
                        WHERE guildid = %s AND last_left IS NULL
                        AND coins IS NOT NULL AND coins > 0
                        ORDER BY value DESC
                        """,
                        (guildid,),
                    )
                    return [
                        (row['userid'], int(row['value']))
                        for row in await cursor.fetchall()
                    ]
        return []

    def _format_value(self, value: int, lb_type: str) -> str:
        """Format a leaderboard value for display."""
        if lb_type == 'study':
            hours = value / 3600
            return f"{hours:.1f}"
        return str(value)

    async def _execute_post(
        self, config, guild_tz, season_start,
        is_test=False, is_run_now=False,
    ):
        """Execute a full leaderboard post cycle."""
        period_start, period_end, period_str = _compute_period_bounds(
            config, guild_tz, season_start,
        )

        if not is_test and not is_run_now:
            if _period_already_posted(config, period_start):
                return

        lb_data = await self._fetch_leaderboard(config, period_start)

        threshold = config.min_threshold or 0
        if threshold > 0:
            lb_data = [(uid, val) for uid, val in lb_data if val >= threshold]

        top_count = config.top_count or 10
        lb_data = lb_data[:top_count]

        if not lb_data and config.skip_if_empty and not is_test:
            await self.data.History.create(
                configid=config.configid,
                guildid=config.guildid,
                status='skipped_empty',
            )
            return

        if (
            config.skip_if_same_as_last
            and not is_test
            and not is_run_now
            and config.last_winner_ids_list
        ):
            current_ids = sorted([uid for uid, _ in lb_data])
            if current_ids == sorted(config.last_winner_ids_list):
                await self.data.History.create(
                    configid=config.configid,
                    guildid=config.guildid,
                    status='skipped_empty',
                    error_message='Same winners as last run',
                )
                return

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Cross-shard guild lookup - fetch via API if not cached on shard 0
        guild = self.bot.get_guild(config.guildid)
        guild_cached = guild is not None
        if not guild:
            try:
                guild = await self.bot.fetch_guild(config.guildid)
            except Exception:
                raise ValueError(
                    f"Guild {config.guildid} not found - the bot may not be in this server"
                )
        # --- END AI-MODIFIED ---

        server_name = guild.name
        lb_type = config.lb_type or 'study'

        winners = []
        for i, (userid, value) in enumerate(lb_data):
            member = guild.get_member(userid)
            # --- AI-MODIFIED (2026-03-22) ---
            # Purpose: Fetch member via API for cross-shard display names
            if not member and not guild_cached:
                try:
                    member = await guild.fetch_member(userid)
                except Exception:
                    pass
            # --- END AI-MODIFIED ---
            winners.append({
                'userid': userid,
                'rank': i + 1,
                'value': self._format_value(value, lb_type),
                'raw_value': value,
                'name': member.display_name if member else f'User {userid}',
            })

        variables = build_variables(
            server_name=server_name,
            frequency=config.frequency or 'weekly',
            lb_type=lb_type,
            top_count=top_count,
            period_str=period_str,
            winners=winners,
            reward_tiers=config.reward_tiers_list,
            top1_role_ids=config.top1_roles_list,
            topn_role_ids=config.topn_roles_list,
        )

        embed = discord.Embed()
        embed_title = render_template(config.embed_title, variables)
        if embed_title:
            embed.title = truncate(embed_title, DISCORD_LIMITS['embed_title'])
        embed_desc = render_template(config.embed_description, variables)
        if embed_desc:
            embed.description = truncate(embed_desc, DISCORD_LIMITS['embed_description'])
        embed_footer = render_template(config.embed_footer, variables)
        if is_test:
            footer_parts = [embed_footer or '', 'TEST -- no rewards or roles applied']
            embed_footer = ' | '.join(p for p in footer_parts if p)
        if embed_footer:
            embed.set_footer(text=truncate(embed_footer, DISCORD_LIMITS['embed_footer']))
        if config.embed_color:
            embed.color = config.embed_color
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Only set embed URLs if they look like real URLs (have scheme + dot, no spaces)
        def _is_valid_url(v):
            v = str(v).strip()
            if ' ' in v or '.' not in v:
                return False
            return v.startswith(('http://', 'https://'))

        if config.embed_url and _is_valid_url(config.embed_url):
            embed.url = str(config.embed_url).strip()
        if config.embed_author_url and not _is_valid_url(config.embed_author_url):
            config.embed_author_url = None
        # --- END AI-MODIFIED ---
        if config.embed_author_name:
            author_kwargs = {
                'name': truncate(
                    render_template(config.embed_author_name, variables),
                    DISCORD_LIMITS['embed_author_name']
                ),
            }
            if config.embed_author_url:
                author_kwargs['url'] = config.embed_author_url
            embed.set_author(**author_kwargs)

        for field_def in config.embed_fields_list[:DISCORD_LIMITS['embed_fields_max']]:
            fname = render_template(field_def.get('name', ''), variables) or '\u200b'
            fvalue = render_template(field_def.get('value', ''), variables) or '\u200b'
            embed.add_field(
                name=truncate(fname, DISCORD_LIMITS['embed_field_name']),
                value=truncate(fvalue, DISCORD_LIMITS['embed_field_value']),
                inline=field_def.get('inline', False),
            )

        content = render_template(config.announce_content, variables)
        if config.mention_winners and not is_test:
            mentions = ' '.join(f"<@{w['userid']}>" for w in winners)
            if content:
                content = f"{content}\n{mentions}"
            else:
                content = mentions
        if content:
            content = truncate(content, DISCORD_LIMITS['content'])

        card_image = None
        if config.include_image and lb_data:
            try:
                from modules.statistics.graphics.leaderboard import get_leaderboard_card
                from gui.base import CardMode

                mode = CardMode.STUDY if lb_type == 'study' else CardMode.TEXT
                entry_data = [
                    (uid, i + 1, val)
                    for i, (uid, val) in enumerate(lb_data)
                ]
                card = await get_leaderboard_card(
                    self.bot, 0, config.guildid, mode, entry_data,
                    guild=guild,
                )
                card_bytes = await card.render()
                card_image = discord.File(
                    io.BytesIO(card_bytes), filename='leaderboard.png'
                )
                embed.set_image(url='attachment://leaderboard.png')
            except Exception:
                logger.error("Failed to render leaderboard card", exc_info=True)

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Use bot.fetch_channel for cross-shard channel access
        channel = guild.get_channel(config.post_channel)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(config.post_channel)
            except Exception:
                pass
        # --- END AI-MODIFIED ---

        history_data = {
            'configid': config.configid,
            'guildid': config.guildid,
            'top_users': json.dumps([
                {
                    'userid': w['userid'],
                    'rank': w['rank'],
                    'value': w['value'],
                }
                for w in winners
            ]),
            'roles_added': 0,
            'roles_removed': 0,
            'coins_awarded': 0,
            'dms_sent': 0,
            'dms_failed': 0,
            'status': 'success',
        }

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Surface channel errors to dashboard actions instead of silently succeeding
        posted_msg = None
        if config.notify_public_post or is_test:
            if channel:
                try:
                    kwargs = {'content': content, 'embed': embed}
                    if card_image:
                        kwargs['file'] = card_image
                    posted_msg = await channel.send(**kwargs)
                except Exception as e:
                    logger.error(f"Failed to post to channel {config.post_channel}", exc_info=True)
                    if is_test or is_run_now:
                        raise ValueError(f"Failed to send to channel: {e}")
                    if not config.continue_on_partial:
                        history_data['status'] = 'failed'
                        history_data['error_message'] = str(e)
                        await self.data.History.create(**history_data)
                        return
            else:
                if is_test or is_run_now:
                    raise ValueError(
                        f"Channel not found or bot lacks access to channel {config.post_channel}"
                    )
                logger.warning(f"Channel {config.post_channel} not found for config {config.configid}")
                if not config.continue_on_partial:
                    history_data['status'] = 'failed'
                    history_data['error_message'] = 'Channel not found'
                    await self.data.History.create(**history_data)
                    return
        # --- END AI-MODIFIED ---

        if is_test:
            return

        if posted_msg and config.pin_post:
            try:
                await posted_msg.pin()
            except Exception:
                logger.warning(f"Failed to pin message in {channel.id}")

        if config.delete_previous and config.last_message_id and channel:
            try:
                old_msg = await channel.fetch_message(config.last_message_id)
                await old_msg.delete()
            except Exception:
                pass

        roles_added = 0
        roles_removed = 0
        role_errors = []

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Multi-role support, cross-shard compat, stale-holder tracking
        top1_role_ids = config.top1_roles_list
        topn_role_ids = config.topn_roles_list

        if guild_cached:
            top1_roles = [r for rid in top1_role_ids if (r := guild.get_role(rid)) and r.is_assignable()]
            topn_roles = [r for rid in topn_role_ids if (r := guild.get_role(rid)) and r.is_assignable()]
        else:
            top1_roles = [r for rid in top1_role_ids if (r := guild.get_role(rid))]
            topn_roles = [r for rid in topn_role_ids if (r := guild.get_role(rid))]
        all_managed_roles = set(top1_roles + topn_roles)

        known_role_holders = set()

        if all_managed_roles:
            winner_ids = {w['userid'] for w in winners}
            top1_uid = winners[0]['userid'] if winners else None

            if config.auto_remove_roles:
                if guild_cached:
                    for role in all_managed_roles:
                        is_top1 = role in top1_roles
                        is_topn = role in topn_roles
                        for member in role.members:
                            should_keep = False
                            if is_top1 and member.id == top1_uid:
                                should_keep = True
                            if is_topn and member.id in winner_ids:
                                should_keep = True
                            if not should_keep:
                                try:
                                    await member.remove_roles(
                                        role, reason="Leaderboard auto-post: removing old holder"
                                    )
                                    roles_removed += 1
                                except Exception as e:
                                    known_role_holders.add(member.id)
                                    role_errors.append(f"Remove {role.name} from {member}: {e}")
                            else:
                                known_role_holders.add(member.id)
                else:
                    prev_holders = set(config.last_winner_ids_list or [])
                    to_remove = prev_holders - winner_ids
                    for uid in to_remove:
                        try:
                            prev_member = await guild.fetch_member(uid)
                            removed_any = False
                            for role in all_managed_roles:
                                if role in prev_member.roles:
                                    await prev_member.remove_roles(
                                        role, reason="Leaderboard auto-post: removing old holder"
                                    )
                                    roles_removed += 1
                                    removed_any = True
                            if not removed_any:
                                pass
                        except Exception as e:
                            known_role_holders.add(uid)
                            role_errors.append(f"Remove roles from user {uid}: {e}")

            for w in winners:
                member = guild.get_member(w['userid'])
                if not member and not guild_cached:
                    try:
                        member = await guild.fetch_member(w['userid'])
                    except Exception:
                        pass
                if not member:
                    continue
                rank = w['rank']

                roles_to_add = []
                if rank == 1:
                    roles_to_add.extend(r for r in top1_roles if r not in member.roles)
                roles_to_add.extend(r for r in topn_roles if r not in member.roles)

                for role in roles_to_add:
                    try:
                        await member.add_roles(
                            role, reason=f"Leaderboard auto-post: rank #{rank}"
                        )
                        roles_added += 1
                    except Exception as e:
                        role_errors.append(f"Add {role.name} to {member}: {e}")

                known_role_holders.add(w['userid'])

        known_role_holders.update(w['userid'] for w in winners)
        # --- END AI-MODIFIED ---

        history_data['roles_added'] = roles_added
        history_data['roles_removed'] = roles_removed

        total_coins = 0
        reward_tiers = config.reward_tiers_list
        if reward_tiers:
            for w in winners:
                rank = w['rank']
                coins_for_rank = 0
                for tier in reward_tiers:
                    if tier['from'] <= rank <= tier['to']:
                        coins_for_rank = tier.get('coins', 0)
                        break
                if coins_for_rank > 0:
                    cap = config.max_coins_per_user
                    if cap and coins_for_rank > cap:
                        coins_for_rank = cap
                    try:
                        await EconomyData.Transaction.execute_transaction(
                            TransactionType.OTHER,
                            guildid=config.guildid,
                            actorid=config.guildid,
                            from_account=None,
                            to_account=w['userid'],
                            amount=coins_for_rank,
                        )
                        total_coins += coins_for_rank
                        w['got_coins'] = coins_for_rank
                    except Exception:
                        logger.error(
                            f"Failed to award {coins_for_rank} coins to {w['userid']}",
                            exc_info=True,
                        )

        history_data['coins_awarded'] = total_coins

        dms_sent = 0
        dms_failed = 0
        if config.notify_dm_winners:
            scope = config.dm_scope or 'top_n'
            if scope == 'top_1':
                dm_winners = winners[:1]
            elif scope == 'top_3':
                dm_winners = winners[:3]
            else:
                dm_winners = winners

            stagger = max(1, config.dm_stagger_seconds or 2)

            for w in dm_winners[:30]:
                try:
                    user = self.bot.get_user(w['userid'])
                    if not user:
                        user = await self.bot.fetch_user(w['userid'])
                    dm_vars = build_dm_variables(
                        variables, w['userid'], w['rank'],
                        w['value'], w.get('got_coins', 0),
                    )
                    dm_embed = discord.Embed(color=config.embed_color or 16766720)
                    dm_title = render_template(config.dm_template_title, dm_vars)
                    if dm_title:
                        dm_embed.title = truncate(dm_title, DISCORD_LIMITS['embed_title'])
                    dm_body = render_template(config.dm_template_body, dm_vars)
                    if dm_body:
                        dm_embed.description = truncate(dm_body, DISCORD_LIMITS['embed_description'])
                    else:
                        dm_embed.description = (
                            f"Congratulations! You placed **#{w['rank']}** on the "
                            f"{variables['frequency']} {variables['type']} leaderboard "
                            f"in **{server_name}**!"
                        )
                    await user.send(embed=dm_embed)
                    dms_sent += 1
                except Exception:
                    dms_failed += 1

                if stagger > 0:
                    await asyncio.sleep(stagger)

        history_data['dms_sent'] = dms_sent
        history_data['dms_failed'] = dms_failed

        if config.notify_mod_log and config.mod_log_channel:
            # --- AI-MODIFIED (2026-03-22) ---
            # Purpose: Cross-shard mod log channel access
            mod_channel = guild.get_channel(config.mod_log_channel)
            if not mod_channel:
                try:
                    mod_channel = await self.bot.fetch_channel(config.mod_log_channel)
                except Exception:
                    pass
            # --- END AI-MODIFIED ---
            if mod_channel:
                try:
                    summary_lines = [
                        f"**Leaderboard Auto-Post Summary** ({config.config_name})",
                        f"Period: {period_str}",
                        f"Winners: {len(winners)}",
                        f"Roles added: {roles_added}, removed: {roles_removed}",
                        f"LionCoins awarded: {total_coins:,}",
                        f"DMs sent: {dms_sent}, failed: {dms_failed}",
                    ]
                    if role_errors:
                        summary_lines.append(
                            f"Role errors: {'; '.join(role_errors[:5])}"
                        )
                    mod_embed = discord.Embed(
                        title="Leaderboard Auto-Post Report",
                        description='\n'.join(summary_lines),
                        color=0x2F3136,
                    )
                    await mod_channel.send(embed=mod_embed)
                except Exception:
                    logger.warning("Failed to send mod log", exc_info=True)

        if history_data.get('status') == 'success' and (role_errors or dms_failed):
            history_data['status'] = 'partial'
            history_data['error_message'] = '; '.join(role_errors[:3])

        history_data['top_users'] = json.dumps([
            {
                'userid': w['userid'],
                'rank': w['rank'],
                'value': w['value'],
                'got_role': bool(config.top1_roles_list or config.topn_roles_list),
                'got_coins': w.get('got_coins', 0),
                'dm_ok': w['userid'] not in {
                    dw['userid'] for dw in dm_winners
                } if config.notify_dm_winners else None,
            }
            for w in winners
        ] if winners else [])

        await self.data.History.create(**history_data)

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Store all known role holders (not just current winners)
        # so cross-shard cleanup can find stale holders from older periods
        update_fields = {
            'last_posted_at': utc_now(),
            'last_winner_ids': json.dumps(sorted(known_role_holders)),
        }
        # --- END AI-MODIFIED ---
        if posted_msg:
            update_fields['last_message_id'] = posted_msg.id
        await config.update(**update_fields)

    # ─── Simulate (read-only) ───────────────────────────────────

    async def _execute_simulate(self, config, guild_tz, season_start) -> dict:
        """Compute what would happen without any side effects."""
        period_start, period_end, period_str = _compute_period_bounds(
            config, guild_tz, season_start,
        )

        lb_data = await self._fetch_leaderboard(config, period_start)

        threshold = config.min_threshold or 0
        if threshold > 0:
            lb_data = [(uid, val) for uid, val in lb_data if val >= threshold]

        top_count = config.top_count or 10
        lb_data = lb_data[:top_count]

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Cross-shard guild lookup for simulate
        guild = self.bot.get_guild(config.guildid)
        if not guild:
            try:
                guild = await self.bot.fetch_guild(config.guildid)
            except Exception:
                pass
        # --- END AI-MODIFIED ---
        lb_type = config.lb_type or 'study'

        winners = []
        total_coins = 0
        roles_add = 0
        roles_remove = 0
        reward_tiers = config.reward_tiers_list

        for i, (userid, value) in enumerate(lb_data):
            rank = i + 1
            member = guild.get_member(userid) if guild else None
            # --- AI-MODIFIED (2026-03-22) ---
            # Purpose: Fetch member via API for cross-shard display names in simulate
            if not member and guild:
                try:
                    member = await guild.fetch_member(userid)
                except Exception:
                    pass
            # --- END AI-MODIFIED ---
            coins_for_rank = 0
            for tier in reward_tiers:
                if tier['from'] <= rank <= tier['to']:
                    coins_for_rank = tier.get('coins', 0)
                    break
            cap = config.max_coins_per_user
            if cap and coins_for_rank > cap:
                coins_for_rank = cap
            total_coins += coins_for_rank

            role_count = 0
            if rank == 1:
                role_count += len(config.top1_roles_list)
            role_count += len(config.topn_roles_list)
            would_get_role = role_count > 0
            if would_get_role:
                roles_add += role_count

            winners.append({
                'userid': userid,
                'rank': rank,
                'value': self._format_value(value, lb_type),
                'name': member.display_name if member else f'User {userid}',
                'would_get_coins': coins_for_rank,
                'would_get_role': would_get_role,
            })

        if config.auto_remove_roles and guild:
            all_role_ids = set(config.top1_roles_list + config.topn_roles_list)
            winner_ids = {w['userid'] for w in winners}
            for role_id in all_role_ids:
                role = guild.get_role(role_id)
                if role:
                    for member in role.members:
                        if member.id not in winner_ids:
                            roles_remove += 1

        dm_count = 0
        if config.notify_dm_winners:
            scope = config.dm_scope or 'top_n'
            if scope == 'top_1':
                dm_count = min(1, len(winners))
            elif scope == 'top_3':
                dm_count = min(3, len(winners))
            else:
                dm_count = len(winners)

        return {
            'period': period_str,
            'winners': winners,
            'roles_add': roles_add,
            'roles_remove': roles_remove,
            'total_coins': total_coins,
            'dms_would_send': dm_count,
        }

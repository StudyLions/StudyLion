# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-13
# Purpose: HTTP API for rendering profile/stats cards as PNGs
#          for the web dashboard. Runs on shard 0.
# ============================================================
import asyncio
import aiohttp
from typing import Optional
from io import BytesIO

from aiohttp import web
from PIL import Image

from meta import LionBot, WEBSITE_URL
from meta.logger import log_wrap
from babel.translator import ctx_locale

from . import logger


class RenderAPI:
    def __init__(self, bot: LionBot, port: int = 7100):
        self.bot = bot
        self.port = port
        self._runner: Optional[web.AppRunner] = None
        # --- AI-MODIFIED (2026-03-14) ---
        # Purpose: cache for sample card renders (keyed by (card_type, skin_name))
        self._sample_cache: dict[tuple[str, str], bytes] = {}
        # --- END AI-MODIFIED ---

    async def start(self):
        app = web.Application()
        app.router.add_get('/render', self._handle_render)
        app.router.add_get('/render-sample', self._handle_render_sample)
        # --- AI-MODIFIED (2026-03-14) ---
        # Purpose: POST endpoint for live branding preview with custom color properties
        app.router.add_post('/render-preview', self._handle_render_preview)
        # --- END AI-MODIFIED ---
        app.router.add_get('/health', self._handle_health)
        # --- AI-MODIFIED (2026-03-15) ---
        # Purpose: cache invalidation endpoint for website branding saves
        app.router.add_post('/invalidate-branding', self._handle_invalidate_branding)
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-03-13) ---
        # Purpose: pomodoro timer status, card, and control endpoints
        app.router.add_get('/timer-status', self._handle_timer_status)
        app.router.add_get('/timer-card', self._handle_timer_card)
        app.router.add_post('/timer-control', self._handle_timer_control)
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-03-15) ---
        # Purpose: marketplace DM notification endpoint
        app.router.add_post('/marketplace-notify', self._handle_marketplace_notify)
        # --- END AI-MODIFIED ---
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f"Card render API started on port {self.port}")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.Response(text='ok')

    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: invalidate branding caches across all shards after a website save
    async def _handle_invalidate_branding(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text='Unauthorized')

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')

        guildid = body.get('guildid')
        if not guildid:
            return web.Response(status=400, text='guildid required')

        try:
            guildid = int(guildid)
        except (ValueError, TypeError):
            return web.Response(status=400, text='Invalid guildid')

        premium_cog = self.bot.get_cog('PremiumCog')
        skinid = 0
        if premium_cog:
            premium_cog.data.PremiumGuild._cache_.pop(guildid, None)
            row = await premium_cog.data.PremiumGuild.fetch(guildid)
            skinid = row.custom_skin_id if row else 0

        await self.bot.global_dispatch('branding_cache_invalidate', guildid, skinid or 0)

        logger.info(
            f"Branding cache invalidated for guild {guildid}, skin {skinid}"
        )
        return web.json_response({'success': True, 'guildid': str(guildid), 'skinid': skinid})
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-04-25) ---
    # Purpose: Sniff output magic bytes so we send the correct content-type.
    #          Animated supporter cards are GIFs but the old code always
    #          replied with image/png, breaking inline rendering in the
    #          dashboard preview frame.
    @staticmethod
    def _sniff_content_type(payload: bytes) -> str:
        if payload[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if payload[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        return 'image/png'
    # --- END AI-MODIFIED ---

    async def _handle_render(self, request: web.Request) -> web.Response:
        auth = request.headers.get('Authorization', '')
        try:
            expected = self.bot.config.render_api.get('auth', '')
        except Exception:
            expected = ''
        if expected and auth != expected:
            return web.Response(status=401, text='Unauthorized')

        card_type = request.query.get('type', 'profile')
        userid_str = request.query.get('userid')
        guildid_str = request.query.get('guildid')
        skin_name = request.query.get('skin', None)
        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Extract supporter_tier query param to pass through to renderers
        supporter_tier = request.query.get('supporter_tier', None)
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Extract custom color and effects_enabled params for card preferences
        sparkle_color = request.query.get('sparkle_color', None)
        ring_color = request.query.get('ring_color', None)
        effects_enabled_str = request.query.get('effects_enabled', None)
        effects_enabled = True
        if effects_enabled_str is not None:
            effects_enabled = effects_enabled_str.lower() not in ('false', '0', 'no')
        # --- END AI-MODIFIED ---

        if not userid_str:
            return web.Response(status=400, text='userid required')
        if not guildid_str:
            return web.Response(status=400, text='guildid required')

        try:
            userid = int(userid_str)
            guildid = int(guildid_str)
        except ValueError:
            return web.Response(status=400, text='Invalid userid/guildid')

        try:
            # First try the standard bot path (if guild is on this shard)
            guild = self.bot.get_guild(guildid)
            if guild is not None:
                png_bytes = await self._render_via_bot(card_type, userid, guildid, skin_name)
            else:
                # --- AI-MODIFIED (2026-03-16) ---
                # Purpose: Pass supporter_tier to _render_from_db
                # --- Original code (commented out for rollback) ---
                # png_bytes = await self._render_from_db(card_type, userid, guildid, skin_name)
                # --- End original code ---
                png_bytes = await self._render_from_db(
                    card_type, userid, guildid, skin_name,
                    supporter_tier=supporter_tier,
                    sparkle_color=sparkle_color, ring_color=ring_color,
                    effects_enabled=effects_enabled,
                )
                # --- END AI-MODIFIED ---

            # --- AI-MODIFIED (2026-04-25) ---
            # Purpose: detect GIF vs PNG so animated supporter cards render
            #          correctly in browsers (was hardcoded to image/png).
            content_type = self._sniff_content_type(png_bytes)
            return web.Response(
                body=png_bytes,
                content_type=content_type,
                headers={'Cache-Control': 'public, max-age=300'},
            )
            # --- END AI-MODIFIED ---
        except Exception as e:
            logger.warning(f"Render API error: {e}", exc_info=True)
            return web.Response(status=500, text=str(e))

    # --- AI-MODIFIED (2026-03-14) ---
    # Purpose: accept skin_name override, fix missing CardMode for stats
    async def _render_via_bot(
        self, card_type: str, userid: int, guildid: int,
        skin_name: Optional[str] = None
    ) -> bytes:
        if card_type == 'profile':
            from modules.statistics.graphics.profile import get_profile_card
            card = await get_profile_card(self.bot, userid, guildid)
            if skin_name:
                card.kwargs['skin'] = {'base_skin_id': skin_name}
            return await card.render()
        elif card_type == 'stats':
            from modules.statistics.graphics.stats import get_stats_card
            from gui.base import CardMode
            card = await get_stats_card(self.bot, userid, guildid, CardMode.STUDY)
            if skin_name:
                card.kwargs['skin'] = {'base_skin_id': skin_name}
            return await card.render()
        raise ValueError(f"Unknown card type: {card_type}")
    # --- END AI-MODIFIED ---

    async def _fetch_avatar(self, userid: int, avatar_hash: Optional[str], size: int = 256) -> bytes:
        """Fetch avatar from Discord CDN or return a default."""
        if avatar_hash:
            ext = 'gif' if avatar_hash.startswith('a_') else 'png'
            url = f"https://cdn.discordapp.com/avatars/{userid}/{avatar_hash}.{ext}?size={size}"
        else:
            index = (userid >> 22) % 6
            url = f"https://cdn.discordapp.com/embed/avatars/{index}.png?size={size}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception:
            pass

        index = (userid >> 22) % 6
        fallback_url = f"https://cdn.discordapp.com/embed/avatars/{index}.png?size={size}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(fallback_url) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception:
            pass

        img = Image.new('RGBA', (size, size), (88, 101, 242, 255))
        buf = BytesIO()
        img.save(buf, 'PNG')
        return buf.getvalue()

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Accept supporter_tier param, fetch from DB if not provided
    # --- Original code (commented out for rollback) ---
    # async def _render_from_db(
    #     self, card_type: str, userid: int, guildid: int,
    #     skin_name: Optional[str] = None
    # ) -> bytes:
    # --- End original code ---
    async def _render_from_db(
        self, card_type: str, userid: int, guildid: int,
        skin_name: Optional[str] = None,
        supporter_tier: Optional[str] = None,
        sparkle_color: Optional[str] = None,
        ring_color: Optional[str] = None,
        effects_enabled: bool = True,
    ) -> bytes:
    # --- END AI-MODIFIED ---
        """Render using direct DB queries for guilds not on this shard."""
        async with self.bot.db.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT coins, display_name FROM members WHERE guildid=%s AND userid=%s",
                (guildid, userid),
            )
            member = await cur.fetchone()

            # --- AI-MODIFIED (2026-03-14) ---
            # Purpose: Fetch user locale from DB instead of hardcoding en_GB
            cur = await conn.execute(
                "SELECT gems, avatar_hash, locale, locale_hint FROM user_config WHERE userid=%s",
                (userid,),
            )
            user = await cur.fetchone()

        user_locale = (user['locale'] or user['locale_hint'] or 'en_GB') if user else 'en_GB'
        ctx_locale.set(user_locale)
        # --- END AI-MODIFIED ---

        coins = member['coins'] if member else 0
        display_name = (member['display_name'] if member else None) or f"User"
        gems = user['gems'] if user else 0
        avatar_hash = user['avatar_hash'] if user else None

        avatar_bytes = await self._fetch_avatar(userid, avatar_hash)
        avatar_image = Image.open(BytesIO(avatar_bytes)).convert('RGBA').resize((256, 256))

        skin_args = {}
        if skin_name:
            skin_args['base_skin_id'] = skin_name
        else:
            skins_cog = self.bot.get_cog('CustomSkinCog')
            if skins_cog:
                try:
                    from gui.cards import ProfileCard as PC
                    skin_args = await skins_cog.get_skinargs_for(
                        guildid, userid, PC.card_id
                    )
                except Exception:
                    pass

        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Fetch supporter tier from DB if not already provided
        if supporter_tier is None:
            try:
                sub_row = await self.bot.db.fetchrow(
                    "SELECT tier, status FROM user_subscriptions WHERE userid = $1", userid
                )
                if sub_row and sub_row['status'] == 'ACTIVE':
                    supporter_tier = sub_row['tier']
            except Exception:
                supporter_tier = None
        # --- END AI-MODIFIED ---

        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Fetch card preferences from DB when not provided via query params
        if supporter_tier and sparkle_color is None and ring_color is None:
            try:
                prefs_row = await self.bot.db.fetchrow(
                    "SELECT effects_enabled, sparkle_color, ring_color "
                    "FROM user_card_preferences WHERE userid = $1", userid
                )
                if prefs_row:
                    if sparkle_color is None:
                        sparkle_color = prefs_row['sparkle_color']
                    if ring_color is None:
                        ring_color = prefs_row['ring_color']
                    effects_enabled = prefs_row['effects_enabled']
            except Exception:
                pass
        # --- END AI-MODIFIED ---

        if card_type == 'profile':
            from gui.cards.profile import ProfileLayout, ProfileSkin
            skin = ProfileSkin('profile', locale='en_GB', **skin_args)
            skin.load()
            # --- AI-MODIFIED (2026-03-16) ---
            # Purpose: Added supporter_tier kwarg
            # --- Original code (commented out for rollback) ---
            # layout = ProfileLayout(
            #     skin,
            #     user=(display_name, ''),
            #     avatar=avatar_image,
            #     coins=coins,
            #     gems=gems,
            #     gifts=0,
            #     profile_badges=[],
            #     achievements=(),
            #     current_rank=None,
            #     rank_progress=0.0,
            #     next_rank=None,
            # )
            # --- End original code ---
            layout = ProfileLayout(
                skin,
                user=(display_name, ''),
                avatar=avatar_image,
                coins=coins,
                gems=gems,
                gifts=0,
                profile_badges=[],
                achievements=(),
                current_rank=None,
                rank_progress=0.0,
                next_rank=None,
                supporter_tier=supporter_tier,
            )
            # --- END AI-MODIFIED ---
            return layout._execute_draw(
                supporter_tier=supporter_tier,
                sparkle_color=sparkle_color,
                ring_color=ring_color,
                effects_enabled=effects_enabled,
            )

        elif card_type == 'stats':
            from gui.cards.stats import StatsLayout, StatsSkin
            skin = StatsSkin('stats', locale='en_GB', **skin_args)
            skin.load()
            layout = StatsLayout(
                skin,
                lb_data=None,
                period_activity=['0h', '0h', '0h', '0h'],
                month_activity='0h',
                workouts=0,
                streak_data=[],
            )
            return layout._execute_draw()

        raise ValueError(f"Unknown card type: {card_type}")

    # --- AI-MODIFIED (2026-03-14) ---
    # Purpose: sample card render endpoint for website skin previews, supports all 7 card types
    async def _handle_render_sample(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text='Unauthorized')

        card_type = request.query.get('type', 'profile')
        skin_name = request.query.get('skin', 'original')

        try:
            png_bytes = await self._render_sample(card_type, skin_name)
            return web.Response(
                body=png_bytes,
                content_type='image/png',
                headers={'Cache-Control': 'public, max-age=86400'},
            )
        except Exception as e:
            logger.warning(f"Render sample error: {e}", exc_info=True)
            return web.Response(status=500, text=str(e))

    async def _handle_render_preview(self, request: web.Request) -> web.Response:
        """POST endpoint for live branding preview with custom color property overrides."""
        if not self._check_auth(request):
            return web.Response(status=401, text='Unauthorized')

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON body')

        card_type = body.get('type', 'profile')
        skin_name = body.get('skin', 'original')
        properties = body.get('properties', {})

        if not isinstance(properties, dict):
            return web.Response(status=400, text='properties must be a dict')

        try:
            png_bytes = await self._render_with_overrides(card_type, skin_name, properties)
            return web.Response(
                body=png_bytes,
                content_type='image/png',
                headers={'Cache-Control': 'no-cache'},
            )
        except Exception as e:
            logger.warning(f"Render preview error: {e}", exc_info=True)
            return web.Response(status=500, text=str(e))

    async def _render_with_overrides(
        self, card_type: str, skin_name: str, properties: dict
    ) -> bytes:
        """Render a sample card with base skin + custom color property overrides."""
        ctx_locale.set('en_GB')
        skin_args = {'base_skin_id': skin_name} if skin_name else {}
        skin_args.update(properties)
        return await self._render_card_sample(card_type, skin_args)

    async def _render_sample(self, card_type: str, skin_name: str) -> bytes:
        cache_key = (card_type, skin_name)
        if cache_key in self._sample_cache:
            return self._sample_cache[cache_key]

        ctx_locale.set('en_GB')
        skin_args = {'base_skin_id': skin_name} if skin_name else {}
        result = await self._render_card_sample(card_type, skin_args)
        self._sample_cache[cache_key] = result
        return result

    async def _render_card_sample(self, card_type: str, skin_args: dict) -> bytes:
        """Shared rendering logic for all 7 card types with arbitrary skin args."""
        if card_type == 'profile':
            from gui.cards.profile import ProfileLayout, ProfileSkin

            avatar_bytes = await self._fetch_avatar(0, None)
            avatar_image = Image.open(BytesIO(avatar_bytes)).convert('RGBA').resize((256, 256))

            skin = ProfileSkin('profile', locale='en_GB', **skin_args)
            skin.load()
            layout = ProfileLayout(
                skin,
                user=('John Doe', '#0000'),
                avatar=avatar_image,
                coins=58596,
                gems=10000,
                gifts=100,
                profile_badges=(
                    'STUDYING: MEDICINE',
                    'HOBBY: MATHS',
                    'CAREER: STUDENT',
                    'FROM: EUROPE',
                    'LOVES CATS <3'
                ),
                achievements=(0, 2, 5, 7),
                current_rank=('VAMPIRE', '3000 - 4000h'),
                rank_progress=0.5,
                next_rank=('WIZARD', '4000 - 8000h'),
            )
            return layout._execute_draw()

        elif card_type == 'stats':
            from gui.cards.stats import StatsLayout, StatsSkin
            from datetime import datetime as dt

            skin = StatsSkin('stats', locale='en_GB', **skin_args)
            skin.load()
            layout = StatsLayout(
                skin,
                lb_data=(21, 123),
                period_activity=("01:00", "10:00", "36:25", "57:30"),
                month_activity="36 hours",
                workouts=50,
                streak_data=[(1, 3), (7, 8), (10, 10), (12, 16), (18, 25), (27, 31)],
                date=dt(2022, 2, 1),
            )
            return layout._execute_draw()

        elif card_type == 'weekly_stats':
            from gui.cards.weekly import WeeklyStatsPage, WeeklyStatsSkin
            import random
            from datetime import datetime, timedelta, timezone as tz

            skin = WeeklyStatsSkin('weekly_stats', locale='en_GB', **skin_args)
            skin.load()

            now = datetime.now(tz=tz.utc)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = day_start - timedelta(days=day_start.weekday())

            daily = [
                random.uniform(1.0, 8.0) * 3600 for _ in range(14)
            ]
            sessions = []
            scan = week_start - timedelta(days=7)
            for d in range(14):
                ds = scan + timedelta(days=d)
                pointer = int(abs(random.gauss(6 * 60, 60)))
                while pointer < 20 * 60:
                    dur = int(abs(random.gauss(90, 30)))
                    sessions.append((
                        int((ds + timedelta(minutes=pointer)).timestamp()),
                        int((ds + timedelta(minutes=pointer + dur)).timestamp()),
                    ))
                    pointer += dur + int(abs(random.gauss(120, 40)))

            layout = WeeklyStatsPage(
                skin,
                user=('John Doe', '#0000'),
                timezone='UTC',
                now=int(now.timestamp()),
                week=int(week_start.timestamp()),
                daily=daily,
                sessions=sessions,
            )
            return layout._execute_draw()

        elif card_type == 'monthly_stats':
            from gui.cards.monthly import MonthlyStatsPage, MonthlyStatsSkin
            import random
            from datetime import datetime, timedelta, timezone as tz

            skin = MonthlyStatsSkin('monthly_stats', locale='en_GB', **skin_args)
            skin.load()

            now = datetime.now(tz=tz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            month = now.replace(day=1)

            months = [month]
            for _ in range(3):
                months.append((months[-1] - timedelta(days=1)).replace(day=1))
            months.reverse()

            monthly = []
            for m in months:
                day_count = ((m + timedelta(days=32)).replace(day=1) - timedelta(days=1)).day
                monthly.append([
                    random.uniform(0, 8.0) * 3600 if random.random() > 0.15 else 0.0
                    for _ in range(day_count)
                ])

            layout = MonthlyStatsPage(
                skin,
                user=('John Doe', '#0000'),
                timezone='UTC',
                now=int(now.timestamp()),
                month=int(month.timestamp()),
                monthly=monthly,
                current_streak=12,
                longest_streak=31,
            )
            return layout._execute_draw()

        elif card_type in ('weekly_goals', 'monthly_goals'):
            from gui.cards.goals import GoalPage, WeeklyGoalSkin, MonthlyGoalSkin
            from datetime import datetime, timezone as tz

            if card_type == 'weekly_goals':
                skin_cls = WeeklyGoalSkin
            else:
                skin_cls = MonthlyGoalSkin

            skin = skin_cls(card_type, locale='en_GB', **skin_args)
            skin.load()

            avatar_bytes = await self._fetch_avatar(0, None)
            avatar_image = Image.open(BytesIO(avatar_bytes)).convert('RGBA').resize((256, 256))

            goals = [
                (0, 'Write a 200 page thesis', False),
                (1, 'Feed the kangaroo', True),
                (2, 'Cure world hunger', False),
                (3, 'Finish assignment 2', True),
            ]

            layout = GoalPage(
                skin,
                name='John Doe',
                discrim='#0000',
                avatar=avatar_image,
                badges=(
                    'STUDYING: MEDICINE',
                    'HOBBY: MATHS',
                    'CAREER: STUDENT',
                    'FROM: EUROPE',
                    'LOVES CATS <3'
                ),
                tasks_done=100 if card_type == 'weekly_goals' else 400,
                studied_hours=160 if card_type == 'weekly_goals' else 64,
                attendance=0.9 if card_type == 'weekly_goals' else 0.95,
                tasks_goal=300 if card_type == 'weekly_goals' else 1200,
                studied_goal=480 if card_type == 'weekly_goals' else 128,
                goals=goals,
                date=datetime.now(tz=tz.utc),
            )
            return layout._execute_draw()

        elif card_type == 'leaderboard':
            from gui.cards.leaderboard import LeaderboardPage, LeaderboardSkin, LeaderboardEntry

            skin = LeaderboardSkin('leaderboard', locale='en_GB', **skin_args)
            skin.load()

            avatar_bytes = await self._fetch_avatar(0, None)

            names = [
                'John Doe', 'Abioye', 'Lacey', 'Chesed', 'Almas',
                'Uche', 'Boitumelo', 'Abimbola', 'Keone', 'Desta'
            ]
            times = [1474481, 1445975, 1127296, 1112495, 854514,
                     824414, 634560, 540633, 417487, 257274]

            entries = []
            for i, (name, t) in enumerate(zip(names, times)):
                entry = LeaderboardEntry(i, i + 1, t, name, (0, None))
                entry.image = avatar_bytes
                entry.convert_avatar()
                entries.append(entry)

            layout = LeaderboardPage(
                skin,
                server_name='Sample Server',
                entries=entries,
                highlight=4,
            )
            return layout._execute_draw()

        raise ValueError(f"Unknown card type: {card_type}")
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-13) ---
    # Purpose: pomodoro timer status, card rendering, and control endpoints

    def _check_auth(self, request: web.Request) -> bool:
        auth = request.headers.get('Authorization', '')
        try:
            expected = self.bot.config.render_api.get('auth', '')
        except Exception:
            expected = ''
        return not expected or auth == expected

    async def _handle_timer_status(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text='Unauthorized')

        guildid_str = request.query.get('guildid')
        if not guildid_str:
            return web.Response(status=400, text='guildid required')

        try:
            guildid = int(guildid_str)
        except ValueError:
            return web.Response(status=400, text='Invalid guildid')

        pom_cog = self.bot.get_cog('PomCog')
        if not pom_cog:
            return web.json_response({'timers': []})

        guild_timers = pom_cog.timers.get(guildid, {})
        result = []
        for chid, timer in guild_timers.items():
            try:
                from utils.lib import utc_now
                stage = timer.current_stage
                info = {
                    'channelid': str(chid),
                    'channelName': timer.channel.name if timer.channel else None,
                    'prettyName': timer.data.pretty_name or timer.base_name,
                    'running': timer.running,
                    'focusLength': timer.data.focus_length // 60,
                    'breakLength': timer.data.break_length // 60,
                    'autoRestart': timer.auto_restart,
                    'membersInChannel': len(timer.members) if timer.channel else 0,
                    'voiceAlerts': timer.voice_alerts,
                }
                if stage:
                    now = utc_now()
                    remaining = max(0, (stage.end - now).total_seconds())
                    info.update({
                        'stage': 'focus' if stage.focused else 'break',
                        'stageStartedAt': stage.start.isoformat(),
                        'stageEndsAt': stage.end.isoformat(),
                        'remainingSeconds': int(remaining),
                        'stageDurationSeconds': stage.duration,
                    })
                else:
                    info.update({
                        'stage': None, 'stageStartedAt': None,
                        'stageEndsAt': None, 'remainingSeconds': 0,
                        'stageDurationSeconds': 0,
                    })
                result.append(info)
            except Exception as e:
                logger.warning(f"Error getting timer status for {chid}: {e}")

        return web.json_response({'timers': result})

    async def _handle_timer_card(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text='Unauthorized')

        guildid_str = request.query.get('guildid')
        channelid_str = request.query.get('channelid')
        if not guildid_str or not channelid_str:
            return web.Response(status=400, text='guildid and channelid required')

        try:
            guildid, channelid = int(guildid_str), int(channelid_str)
        except ValueError:
            return web.Response(status=400, text='Invalid IDs')

        pom_cog = self.bot.get_cog('PomCog')
        if not pom_cog:
            return web.Response(status=404, text='Pomodoro not loaded')

        timer = pom_cog.timers.get(guildid, {}).get(channelid)
        if not timer or not timer.running:
            return web.Response(status=204)

        try:
            from modules.pomodoro.graphics import get_timer_card
            stage = timer.current_stage
            if not stage:
                return web.Response(status=204)
            card = await get_timer_card(self.bot, timer, stage)
            png_bytes = await card.request()
            return web.Response(body=png_bytes, content_type='image/png',
                                headers={'Cache-Control': 'public, max-age=30'})
        except Exception as e:
            logger.warning(f"Timer card render error: {e}", exc_info=True)
            return web.Response(status=500, text=str(e))

    async def _handle_timer_control(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text='Unauthorized')

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')

        guildid = body.get('guildid')
        channelid = body.get('channelid')
        action = body.get('action')

        if not guildid or not channelid or not action:
            return web.Response(status=400, text='guildid, channelid, and action required')

        try:
            guildid, channelid = int(guildid), int(channelid)
        except (ValueError, TypeError):
            return web.Response(status=400, text='Invalid IDs')

        pom_cog = self.bot.get_cog('PomCog')
        if not pom_cog:
            return web.Response(status=404, text='Pomodoro not loaded')

        timer = pom_cog.timers.get(guildid, {}).get(channelid)

        if action == 'reload':
            try:
                await pom_cog._load_timers(guildid)
                return web.json_response({'success': True, 'action': 'reload'})
            except Exception as e:
                return web.Response(status=500, text=str(e))

        if not timer:
            return web.Response(status=404, text='Timer not found in memory')

        if action == 'start' and not timer.running:
            await timer.start()
            return web.json_response({'success': True, 'action': 'start', 'running': True})
        elif action == 'stop' and timer.running:
            await timer.stop()
            return web.json_response({'success': True, 'action': 'stop', 'running': False})
        elif action == 'unload':
            await timer.destroy()
            return web.json_response({'success': True, 'action': 'unload'})
        else:
            return web.json_response({
                'success': False,
                'reason': f"Timer is {'running' if timer.running else 'stopped'}, cannot {action}",
            })
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-15) ---
    # Purpose: Marketplace DM notification - website calls this
    # when an item is sold so the seller gets a Discord DM
    async def _handle_marketplace_notify(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(status=401, text='Unauthorized')

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')

        notify_type = body.get('type', 'SALE')
        seller_userid = body.get('seller_userid')
        if not seller_userid:
            return web.Response(status=400, text='Missing seller_userid')

        asyncio.create_task(self._send_marketplace_dm(body))
        return web.json_response({'success': True})

    async def _send_marketplace_dm(self, body: dict):
        import discord

        try:
            seller_id = int(body['seller_userid'])
            user = self.bot.get_user(seller_id)
            if user is None:
                user = await self.bot.fetch_user(seller_id)

            notify_type = body.get('type', 'SALE')

            if notify_type == 'SALE':
                buyer_name = body.get('buyer_name', 'Someone')
                item_name = body.get('item_name', 'an item')
                quantity = body.get('quantity', 1)
                total_price = body.get('total_price', 0)
                currency = body.get('currency', 'GOLD')
                remaining = body.get('remaining', 0)

                currency_emoji = '🪙' if currency == 'GOLD' else '💎'

                embed = discord.Embed(
                    title='🛒 Item Sold!',
                    description=f'**{buyer_name}** bought **{quantity}x {item_name}** from your marketplace listing!',
                    color=0xFFD700 if currency == 'GOLD' else 0x00CED1,
                )
                embed.add_field(name='Revenue', value=f'{currency_emoji} {total_price:,} {currency}', inline=True)
                embed.add_field(name='Remaining', value=f'{remaining} left' if remaining > 0 else 'Listing complete!', inline=True)
                embed.set_footer(text=f'View your listings at {WEBSITE_URL}/pet/marketplace/my-listings')

                await user.send(embed=embed)
            else:
                logger.info(f"Unknown marketplace notify type: {notify_type}")

        except discord.Forbidden:
            logger.info(f"Cannot DM marketplace notification to user {body.get('seller_userid')}")
        except Exception as e:
            logger.warning(f"Marketplace DM error: {e}")
    # --- END AI-MODIFIED ---

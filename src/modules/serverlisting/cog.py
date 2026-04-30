# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-30
# Purpose: Bot-side cog for the "Feature Your Server" website
#          feature. Exposes an aiohttp HTTP server on shard 0
#          with two routes:
#
#            POST /listing/invite/create
#                Picks a suitable text channel in the requesting
#                guild, calls Discord's create_invite, persists
#                the resulting code in server_listings, and
#                returns the discord.gg URL. Used by the dashboard
#                editor's "Regenerate via Leo" button.
#
#            POST /listing/notify
#                Posts a rich embed to channel 1499358894466662410
#                tagging Ari with copy-paste SQL UPDATE snippets
#                so he can approve / reject the listing without
#                logging into a separate admin dashboard.
#
#          Both routes require the BOT_HTTP_SHARED_SECRET in
#          the Authorization header (Bearer <secret>). The cog
#          loads on shard 0 only so we don't have 32 instances
#          of the listener fighting for the same port.
# ============================================================
from typing import Optional
import asyncio

import discord
from aiohttp import web

from meta import LionCog, LionBot, WEBSITE_URL
from meta.logger import log_wrap
from utils.lib import utc_now

from . import logger
from . import data as listing_data


REVIEW_CHANNEL_ID = 1499358894466662410
REVIEWER_USER_ID = 757652191656804413


class ServerListingCog(LionCog):
    """HTTP listener for the website's server-listing feature."""

    def __init__(self, bot: LionBot):
        self.bot = bot
        self._runner: Optional[web.AppRunner] = None
        self._auth: str = ''

    async def cog_load(self):
        # Pull config: shared secret + port + enable toggle. We tolerate
        # missing config entirely (feature disabled) so existing bot
        # deployments without these settings keep working.
        try:
            section = self.bot.config.serverlisting
        except (KeyError, AttributeError):
            logger.info("No [SERVERLISTING] config section -- module idle.")
            return

        if not section.getboolean('enabled', False):
            logger.info("Server-listing module disabled via config.")
            return

        # --- AI-MODIFIED (2026-04-30) ---
        # Purpose: Mirror the topgg pattern -- HTTP listener runs on
        # shard 0 only, every other shard idles.
        if self.bot.shard_id != 0:
            logger.debug(
                f"Server-listing HTTP listener skipped on shard {self.bot.shard_id}."
            )
            return
        # --- END AI-MODIFIED ---

        self._auth = section.get('auth', '')
        port = section.getint('port', 7001)

        app = web.Application()
        app.router.add_post('/listing/invite/create', self._handle_create_invite)
        app.router.add_post('/listing/notify', self._handle_notify)
        app.router.add_get('/listing/health', self._handle_health)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"Server-listing HTTP listener bound on port {port}.")

    async def cog_unload(self):
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    # ── Auth helper ─────────────────────────────────────────

    def _check_auth(self, request: web.Request) -> bool:
        if not self._auth:
            # No secret configured -- refuse everything; we never want
            # an open endpoint creating invites in the wild.
            return False
        header = request.headers.get('Authorization', '')
        return header == f"Bearer {self._auth}"

    # ── Health check ────────────────────────────────────────

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({'ok': True, 'shard': self.bot.shard_id})

    # ── Create / rotate invite ──────────────────────────────

    @log_wrap(action="ServerListing CreateInvite")
    async def _handle_create_invite(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({'ok': False, 'error': 'Unauthorized'}, status=401)
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({'ok': False, 'error': 'Bad JSON'}, status=400)

        try:
            guildid = int(payload.get('guildid', 0))
        except (TypeError, ValueError):
            guildid = 0
        if not guildid:
            return web.json_response({'ok': False, 'error': 'Missing guildid'}, status=400)

        guild = self.bot.get_guild(guildid)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(guildid)
            except discord.HTTPException:
                guild = None
        if guild is None:
            return web.json_response(
                {'ok': False, 'error_code': 'BOT_NOT_IN_GUILD',
                 'error': "Leo isn't in this guild."},
                status=404,
            )

        channel = self._pick_invite_channel(guild)
        if channel is None:
            return web.json_response(
                {'ok': False, 'error_code': 'NO_CHANNELS',
                 'error': "No channel where Leo can create invites."},
                status=403,
            )

        try:
            invite = await channel.create_invite(
                max_age=0,
                max_uses=0,
                unique=True,
                reason="LionBot server listing -- via dashboard",
            )
        except discord.Forbidden:
            return web.json_response(
                {'ok': False, 'error_code': 'MISSING_PERMS',
                 'error': "Leo lacks the Create Invite permission."},
                status=403,
            )
        except discord.HTTPException as exc:
            logger.warning(f"Discord invite-create failed for {guildid}: {exc}")
            return web.json_response(
                {'ok': False, 'error': f"Discord error: {exc}"}, status=502,
            )

        try:
            await listing_data.update_listing_invite(
                self.bot, guildid, invite_code=invite.code,
            )
        except Exception:
            logger.warning("DB update failed after creating invite.", exc_info=True)
            # We still return success -- the invite exists, the website
            # can re-attempt the DB write on its end.

        return web.json_response({
            'ok': True,
            'invite_code': invite.code,
            'invite_url': str(invite.url),
        })

    @staticmethod
    def _pick_invite_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Pick the most appropriate channel for a public join invite.

        Preference order:
          1. The guild's `system_channel` if Leo can create invites there
          2. A channel literally named "general" / "welcome" / "lobby"
          3. The first text channel where Leo has create_instant_invite

        Returns None if no suitable channel is found.
        """
        me = guild.me
        if me is None:
            return None

        def can_invite_here(ch: discord.abc.GuildChannel) -> bool:
            if not isinstance(ch, discord.TextChannel):
                return False
            perms = ch.permissions_for(me)
            return perms.create_instant_invite and perms.view_channel

        sysc = guild.system_channel
        if sysc is not None and can_invite_here(sysc):
            return sysc

        preferred_names = ('general', 'welcome', 'lobby', 'main', 'chat', 'home')
        for ch in guild.text_channels:
            if ch.name.lower() in preferred_names and can_invite_here(ch):
                return ch

        for ch in guild.text_channels:
            if can_invite_here(ch):
                return ch

        return None

    # ── Review notification ────────────────────────────────

    @log_wrap(action="ServerListing Notify")
    async def _handle_notify(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({'ok': False, 'error': 'Unauthorized'}, status=401)
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({'ok': False, 'error': 'Bad JSON'}, status=400)

        try:
            guildid = int(payload.get('guildid', 0))
        except (TypeError, ValueError):
            guildid = 0
        kind = payload.get('kind', 'new')
        if not guildid:
            return web.json_response({'ok': False, 'error': 'Missing guildid'}, status=400)

        listing = await listing_data.fetch_listing_by_guildid(self.bot, guildid)
        if listing is None:
            return web.json_response(
                {'ok': False, 'error': 'Listing not found'}, status=404,
            )

        try:
            await self._post_review_embed(listing, kind=kind)
        except Exception:
            logger.warning("Failed to post review embed.", exc_info=True)
            return web.json_response({'ok': False, 'error': 'Embed post failed'}, status=502)

        try:
            await listing_data.mark_notification_sent(self.bot, guildid)
        except Exception:
            logger.debug("notification_sent_at update failed.", exc_info=True)

        return web.json_response({'ok': True})

    async def _post_review_embed(self, listing: dict, *, kind: str) -> None:
        channel = self.bot.get_channel(REVIEW_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(REVIEW_CHANNEL_ID)
            except discord.HTTPException:
                logger.warning(
                    f"Review channel {REVIEW_CHANNEL_ID} not accessible to bot."
                )
                return

        guildid = listing['guildid']
        slug = listing['slug']
        guild_name = await listing_data.fetch_guild_name(self.bot, guildid) or 'Unknown server'
        is_edit = (kind == 'edit')

        # Compose the human-readable summary block
        title = (
            f"🛠️ Listing edits awaiting re-approval -- {guild_name}"
            if is_edit else
            f"📝 New server listing for review -- {guild_name}"
        )

        category = listing.get('category') or 'uncategorised'
        sec_tags = ', '.join(listing.get('secondary_tags') or []) or '—'
        tagline = listing.get('tagline') or '—'
        description = (listing.get('description') or '').strip()
        if len(description) > 800:
            description = description[:800] + '…'
        external = listing.get('external_link_url') or '—'
        country = listing.get('primary_country') or '—'
        language = listing.get('primary_language') or '—'
        nsfw_ok = '✅' if listing.get('nsfw_confirmed') else '⚠️ NOT CONFIRMED'

        preview_url = f"{WEBSITE_URL}/servers/{slug}"

        embed = discord.Embed(
            title=title[:256],
            description=(
                f"**Slug:** `{slug}`\n"
                f"**Tagline:** {tagline}\n\n"
                f"{description}"
            )[:4000],
            colour=discord.Colour.gold() if is_edit else discord.Colour.blurple(),
            timestamp=utc_now(),
        )
        embed.add_field(name='Guild ID', value=f"`{guildid}`", inline=True)
        embed.add_field(name='Category', value=category, inline=True)
        embed.add_field(name='Secondary tags', value=sec_tags, inline=True)
        embed.add_field(name='Country / Language', value=f"{country} / {language}", inline=True)
        embed.add_field(name='Audience age', value=listing.get('audience_age') or '—', inline=True)
        embed.add_field(name='NSFW confirmed?', value=nsfw_ok, inline=True)
        embed.add_field(
            name='External link (DoFollow)',
            value=external,
            inline=False,
        )
        embed.add_field(
            name='Preview the page',
            value=f"[Open preview]({preview_url}) (preview token sent separately)",
            inline=False,
        )
        if listing.get('cover_image_url'):
            embed.set_image(url=listing['cover_image_url'])
        if listing.get('guild_icon_url'):
            embed.set_thumbnail(url=listing['guild_icon_url'])

        # SQL approval block, in a separate message so it's always
        # easy to copy without dragging through the embed.
        sql_block = (
            f"```sql\n"
            f"-- APPROVE:\n"
            f"UPDATE server_listings\n"
            f"SET status = 'APPROVED',\n"
            f"    approved_at = NOW(),\n"
            f"    approved_by = {REVIEWER_USER_ID},\n"
            f"    rejection_reason = NULL,\n"
            f"    pending_changes = NULL\n"
            f"WHERE guildid = {guildid};\n"
            f"\n"
            f"-- REJECT:\n"
            f"UPDATE server_listings\n"
            f"SET status = 'REJECTED',\n"
            f"    rejection_reason = '<your reason here>'\n"
            f"WHERE guildid = {guildid};\n"
            f"```"
        )

        try:
            await channel.send(
                content=f"<@{REVIEWER_USER_ID}>",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=REVIEWER_USER_ID)]),
            )
            await channel.send(content=sql_block)
        except discord.HTTPException as exc:
            logger.warning(f"Couldn't post review notification: {exc}")
            raise

from typing import Optional
import asyncio
import datetime
import time

import discord
from discord.ext import commands as cmds
import discord.app_commands as appcmds
from discord.ui.button import Button, ButtonStyle
from aiohttp import web
from data.queries import ORDER

from meta import LionCog, LionBot, LionContext, WEBSITE_URL
from meta.logger import log_wrap
from wards import sys_admin_ward
from utils.lib import utc_now
from babel.translator import ctx_locale

# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Import GemTransactionType for vote gem rewards
from modules.premium.data import GemTransactionType
# --- END AI-MODIFIED ---

from . import logger, babel
from .data import TopggData

_p = babel._p

topgg_upvote_link = 'https://top.gg/bot/889078613817831495/vote'

# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Tier-scaled vote reward constants for LionHeart subscription integration
VOTE_GEM_REWARDS = {
    'NONE': 5, 'LIONHEART': 10, 'LIONHEART_PLUS': 15, 'LIONHEART_PLUS_PLUS': 30,
}
VOTE_LIONCOIN_BOOST = {
    'NONE': 1.25, 'LIONHEART': 1.5, 'LIONHEART_PLUS': 1.75, 'LIONHEART_PLUS_PLUS': 2.0,
}
VOTE_LG_GOLD_BOOST = {
    'NONE': 1.0, 'LIONHEART': 1.15, 'LIONHEART_PLUS': 1.25, 'LIONHEART_PLUS_PLUS': 1.5,
}
# --- END AI-MODIFIED ---


# --- AI-MODIFIED (2026-03-13) ---
# Purpose: Replaced topggpy WebhookManager with custom aiohttp webhook server
# to support both top.gg v1 and v2 webhook payload formats.
# topggpy 1.4.0 (latest) does not handle the v2 format.
class TopggCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data: TopggData = bot.db.load_registry(TopggData())

        self._webhook_runner: Optional[web.AppRunner] = None
        self._webhook_auth: str = ''
        # --- AI-MODIFIED (2026-03-16) ---
        # Purpose: Track vote reminder background task
        self._reminder_task: Optional[asyncio.Task] = None
        # --- END AI-MODIFIED ---
        # --- AI-MODIFIED (2026-03-21) ---
        # Purpose: Deduplication for vote reminders -- prevents sending 2-3x DMs per vote cycle
        # because the SQL window (15min) is wider than the loop interval (5min)
        self._reminded_users: dict = {}
        # --- END AI-MODIFIED ---

    async def cog_load(self):
        await self.data.init()

        tgg_config = self.bot.config.topgg
        if tgg_config.getboolean('enabled', False):
            economy = self.bot.get_cog('Economy')
            economy.register_economy_bonus(self.voting_bonus, name='voting')

            if self.bot.shard_id != 0:
                logger.debug(
                    f"Not initialising topgg executor in shard {self.bot.shard_id}"
                )
            else:
                self._webhook_auth = tgg_config.get('auth', '')
                route = tgg_config.get('route', '/dbl')
                port = tgg_config.getint('port', 7000)

                app = web.Application()
                app.router.add_post(route, self._webhook_handler)
                self._webhook_runner = web.AppRunner(app)
                await self._webhook_runner.setup()
                site = web.TCPSite(self._webhook_runner, '0.0.0.0', port)
                await site.start()

                logger.info(
                    f"Topgg webhook registered on port {port} route {route}."
                )

                # --- AI-MODIFIED (2026-03-16) ---
                # Purpose: Start vote reminder background task on shard 0
                self._reminder_task = self.bot.loop.create_task(self._vote_reminder_loop())
                logger.info("Vote reminder background task started on shard 0.")
                # --- END AI-MODIFIED ---
        else:
            logger.info(
                "Topgg disabled via config, not initialising module."
            )

    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Added _recent_votes dict for deduplication -- top.gg sends both v1 and v2
    # webhooks for every vote, causing double-processing (double gems, double DMs).
    # A 120-second cooldown per user prevents the duplicate since top.gg only allows
    # voting once every 12 hours.
    _recent_votes: dict[int, float] = {}
    VOTE_DEDUP_SECONDS = 120

    async def _webhook_handler(self, request: web.Request) -> web.Response:
        """Handle incoming top.gg webhook POST requests (v1 and v2 formats)."""
        if self._webhook_auth:
            auth_header = request.headers.get('Authorization', '')
            if auth_header and auth_header != self._webhook_auth:
                return web.Response(status=401, text='Unauthorized')

        try:
            payload = await request.json()
        except Exception:
            logger.warning("Topgg webhook received non-JSON request.")
            return web.Response(status=400, text='Bad Request')

        userid = self._extract_userid(payload)
        if userid is None:
            logger.warning(f"Could not extract user ID from topgg payload: {payload}")
            return web.Response(status=400, text='Bad Request')

        now = time.monotonic()
        last_vote = self._recent_votes.get(userid)
        if last_vote is not None and (now - last_vote) < self.VOTE_DEDUP_SECONDS:
            logger.info(
                f"Duplicate topgg webhook for user {userid} within {self.VOTE_DEDUP_SECONDS}s, "
                f"ignoring. Payload type: {payload.get('type', 'v1')}"
            )
            return web.Response(status=200, text='OK')

        self._recent_votes[userid] = now

        stale = [uid for uid, ts in self._recent_votes.items() if (now - ts) > self.VOTE_DEDUP_SECONDS * 2]
        for uid in stale:
            del self._recent_votes[uid]

        self.bot.loop.create_task(self._process_vote(userid, payload))
        return web.Response(status=200, text='OK')
    # --- END AI-MODIFIED ---

    @staticmethod
    def _extract_userid(payload: dict) -> Optional[int]:
        """Extract Discord user ID from either v1 or v2 top.gg webhook payload."""
        try:
            if payload.get('type') == 'vote.create' and 'data' in payload:
                return int(payload['data']['user']['platform_id'])
            if 'user' in payload:
                return int(payload['user'])
        except (KeyError, ValueError, TypeError):
            pass
        return None

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Add gem rewards and tier-aware bonuses to vote processing
    # --- Original code (commented out for rollback) ---
    # async def _process_vote(self, userid: int, payload: dict):
    #     """Record the vote and send a thank-you DM."""
    #     logger.info(f"Processing TopGG vote for user {userid} (payload type: {payload.get('type', 'v1')})")
    #
    #     await self.data.TopGG.create(
    #         userid=userid,
    #         boostedtimestamp=utc_now()
    #     )
    #     await self._send_thanks_dm(userid)
    # --- End original code ---
    async def _process_vote(self, userid: int, payload: dict):
        """Record the vote, award gems based on subscription tier, and send a thank-you DM."""
        logger.info(f"Processing TopGG vote for user {userid} (payload type: {payload.get('type', 'v1')})")

        await self.data.TopGG.create(
            userid=userid,
            boostedtimestamp=utc_now()
        )

        tier = await self._get_voter_tier(userid)
        gems_earned = VOTE_GEM_REWARDS.get(tier, 5)

        premium_cog = self.bot.get_cog('PremiumCog')
        if premium_cog:
            try:
                await premium_cog.gem_transaction(
                    GemTransactionType.AUTOMATIC,
                    actorid=userid,
                    from_account=None,
                    to_account=userid,
                    amount=gems_earned,
                    description=f"Top.gg vote reward ({tier})",
                    reference=f"topgg_vote_{userid}_{int(utc_now().timestamp())}",
                )
                logger.info(f"Awarded {gems_earned} gems to user {userid} for voting (tier: {tier})")
            except Exception:
                logger.warning(
                    f"Failed to award gems to user {userid} for voting.",
                    exc_info=True,
                )
        else:
            logger.warning("PremiumCog not loaded, skipping gem reward for vote.")

        await self._send_thanks_dm(userid, tier=tier, gems_earned=gems_earned)
    # --- END AI-MODIFIED ---

    @LionCog.listener('on_dbl_vote')
    @log_wrap(action="Handle DBL Vote")
    async def handle_dbl_vote(self, data):
        """Legacy event handler kept for compatibility if anything dispatches on_dbl_vote."""
        logger.info(f"Received TopGG vote via event: {data}")
        userid = self._extract_userid(data)
        if userid is None:
            logger.warning(f"Could not extract user ID from dbl_vote event data: {data}")
            return

        await self._process_vote(userid, data)
# --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Tier-aware voting bonus and helper to resolve subscription tier
    # --- Original code (commented out for rollback) ---
    # async def voting_bonus(self, guildid, userid, **kwargs):
    #     # Provides 1.25 multiplicative bonus if they have voted within 12h
    #     if await self.check_voted_recently(userid):
    #         return 1.25
    #     else:
    #         return 1
    # --- End original code ---
    async def voting_bonus(self, guildid, userid, **kwargs):
        if await self.check_voted_recently(userid):
            tier = await self._get_voter_tier(userid)
            return VOTE_LIONCOIN_BOOST.get(tier, 1.25)
        return 1

    async def _get_voter_tier(self, userid):
        """Resolve the user's LionHeart subscription tier, defaulting to 'NONE'."""
        premium_cog = self.bot.get_cog('PremiumCog')
        if premium_cog and hasattr(premium_cog, 'get_user_subscription_tier'):
            try:
                return await premium_cog.get_user_subscription_tier(userid)
            except Exception:
                logger.debug(f"Could not fetch subscription tier for user {userid}", exc_info=True)
        return 'NONE'
    # --- END AI-MODIFIED ---

    async def check_voted_recently(self, userid):
        records = await self.data.TopGG.fetch_where(
            userid=userid
        ).order_by('boostedtimestamp', ORDER.DESC).limit(1)

        return records and (utc_now() - records[0].boostedtimestamp).total_seconds() < 3600 * 12

    # --- AI-REPLACED (2026-03-19) ---
    # Reason: Vote button now always visible with countdown timer when on cooldown
    # What the new code does better: shows gem reward + countdown so button is always useful
    # --- Original code (commented out for rollback) ---
    # def vote_button(self, gems: int = None):
    #     t = self.bot.translator.t
    #     if gems is not None:
    #         label = t(_p('button:vote_gems|label', "Vote ({gems} free LionGems!)")).format(gems=gems)
    #     else:
    #         label = t(_p('button:vote|label', "Vote for me!"))
    #     button = Button(
    #         style=ButtonStyle.link, label=label,
    #         emoji=self.bot.config.emojis.gem if hasattr(self.bot.config.emojis, 'gem') else '\U0001f48e',
    #         url=topgg_upvote_link,
    #     )
    #     return button
    # async def vote_button_for_user(self, userid: int):
    #     tier = await self._get_voter_tier(userid)
    #     gems = VOTE_GEM_REWARDS.get(tier, 5)
    #     return self.vote_button(gems=gems)
    # --- End original code ---
    async def get_last_vote_time(self, userid):
        """Get the timestamp of the user's most recent vote, or None."""
        records = await self.data.TopGG.fetch_where(
            userid=userid
        ).order_by('boostedtimestamp', ORDER.DESC).limit(1)
        if records:
            return records[0].boostedtimestamp
        return None

    def vote_button(self, gems: int = None, cooldown_seconds: float = None):
        t = self.bot.translator.t
        gem_emoji = self.bot.config.emojis.gem if hasattr(self.bot.config.emojis, 'gem') else '\U0001f48e'

        if cooldown_seconds is not None and cooldown_seconds > 0:
            hours = int(cooldown_seconds // 3600)
            minutes = int((cooldown_seconds % 3600) // 60)
            time_str = f"{hours}h {minutes:02d}m" if hours > 0 else f"{minutes}m"
            if gems is not None:
                label = f"\u2714 Voted \u2022 {gems} gems in {time_str}"
            else:
                label = f"\u2714 Voted \u2022 Vote again in {time_str}"
        elif gems is not None:
            label = t(_p(
                'button:vote_gems|label',
                "Vote ({gems} free LionGems!)"
            )).format(gems=gems)
        else:
            label = t(_p(
                'button:vote|label',
                "Vote for me!"
            ))

        button = Button(
            style=ButtonStyle.link,
            label=label,
            emoji=gem_emoji,
            url=topgg_upvote_link,
        )
        return button

    async def vote_button_for_user(self, userid: int):
        """Return a vote button with gem reward and countdown if on cooldown."""
        tier = await self._get_voter_tier(userid)
        gems = VOTE_GEM_REWARDS.get(tier, 5)

        last_vote = await self.get_last_vote_time(userid)
        if last_vote:
            remaining = 3600 * 12 - (utc_now() - last_vote).total_seconds()
            if remaining > 0:
                return self.vote_button(gems=gems, cooldown_seconds=remaining)

        return self.vote_button(gems=gems)

    async def add_vote_to_view(self, view, userid, guildid=None, row=4):
        """Add a vote button to a raw discord.ui.View. Stores it as view._vote_btn for re-adding after clear_items."""
        try:
            btn = await self.vote_button_for_user(userid)
            btn.row = row
            view._vote_btn = btn
            view.add_item(btn)
        except Exception:
            pass
    # --- END AI-REPLACED ---

    # --- AI-MODIFIED (2026-03-21) ---
    # Purpose: Vote reminder loop -- fixed row key (dict_row), added deduplication,
    # added safe .format() fallback for malformed locale strings
    async def _vote_reminder_loop(self):
        """Background task: remind users to vote again when their 12h bonus expires."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(300)  # 5 minutes

                # Prune stale entries from dedup cache (keep 13h so next vote cycle gets a fresh reminder)
                now_ts = time.time()
                self._reminded_users = {
                    uid: ts for uid, ts in self._reminded_users.items()
                    if now_ts - ts < 13 * 3600
                }

                now = utc_now()
                window_start = now - datetime.timedelta(hours=12, minutes=15)
                window_end = now - datetime.timedelta(hours=12)

                async with self.bot.db.connection() as conn:
                    cursor = await conn.execute(
                        """
                        SELECT t.userid
                        FROM (
                            SELECT userid, MAX(boostedtimestamp) AS last_vote
                            FROM topgg
                            GROUP BY userid
                        ) t
                        LEFT JOIN user_config uc ON uc.userid = t.userid
                        WHERE t.last_vote BETWEEN %s AND %s
                          AND (uc.topgg_vote_reminder IS NULL OR uc.topgg_vote_reminder = true)
                        """,
                        [window_start, window_end],
                    )
                    rows = await cursor.fetchall()
                    eligible = [row['userid'] for row in rows] if rows else []

                eligible = [uid for uid in eligible if uid not in self._reminded_users]

                if not eligible:
                    continue

                logger.info(f"Sending vote reminders to {len(eligible)} users.")
                t = self.bot.translator.t

                title_default = "Your vote bonus has expired! {coin}"
                desc_default = (
                    "Your **12-hour vote boost** just ran out.\n"
                    "Vote again to earn **{gems} LionGems** "
                    "and a **{boost}x LionCoin** bonus!\n\n"
                    "Use `/votereminder` to turn these reminders off."
                )

                for uid in eligible:
                    try:
                        user = self.bot.get_user(uid)
                        if user is None:
                            user = await self.bot.fetch_user(uid)

                        tier = await self._get_voter_tier(uid)
                        gems = VOTE_GEM_REWARDS.get(tier, 5)
                        boost = VOTE_LIONCOIN_BOOST.get(tier, 1.25)

                        try:
                            title_text = t(_p(
                                'embed:vote_reminder|title', title_default
                            )).format(coin=self.bot.config.emojis.coin)
                        except (ValueError, KeyError):
                            title_text = title_default.format(coin=self.bot.config.emojis.coin)

                        try:
                            desc_text = t(_p(
                                'embed:vote_reminder|desc', desc_default
                            )).format(gems=gems, boost=boost)
                        except (ValueError, KeyError):
                            desc_text = desc_default.format(gems=gems, boost=boost)

                        embed = discord.Embed(
                            colour=discord.Colour.gold(),
                            title=title_text,
                            description=desc_text,
                        )

                        if tier == 'NONE':
                            embed.set_footer(text=t(_p(
                                'embed:vote_reminder|footer_upsell',
                                "Tip: LionHeart subscribers earn up to 30 gems and 2x LionCoins per vote!"
                            )))

                        view = discord.ui.View()
                        view.add_item(self.vote_button(gems=gems))

                        await user.send(embed=embed, view=view)
                        self._reminded_users[uid] = time.time()
                    except discord.Forbidden:
                        self._reminded_users[uid] = time.time()
                        logger.debug(f"Cannot DM user {uid} (DMs disabled), skipping reminder.")
                    except discord.HTTPException:
                        logger.debug(f"Failed to send vote reminder to user {uid}.", exc_info=True)
                    except Exception:
                        logger.warning(f"Unexpected error sending vote reminder to {uid}.", exc_info=True)

                    await asyncio.sleep(1)  # rate-limit DMs

            except asyncio.CancelledError:
                return
            except Exception:
                logger.warning("Error in vote reminder loop.", exc_info=True)
                await asyncio.sleep(60)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: /votereminder slash command to toggle vote reminder DMs
    # Uses hybrid_command to match project pattern (LionCog._inject has a bug with pure appcmds)
    @cmds.hybrid_command(
        name=_p('cmd:votereminder', "votereminder"),
        description=_p(
            'cmd:votereminder|desc',
            "Toggle Top.gg vote reminder DMs on or off."
        ),
    )
    async def votereminder_cmd(self, ctx: LionContext, enabled: bool):
        userid = ctx.author.id
        t = self.bot.translator.t

        user_model = self.bot.core.data.User
        rows = await user_model.fetch_where(userid=userid)
        if not rows:
            await user_model.create(userid=userid, topgg_vote_reminder=enabled)
        else:
            await user_model.table.update_where(userid=userid).set(topgg_vote_reminder=enabled)

        if enabled:
            msg = t(_p(
                'cmd:votereminder|enabled',
                "Vote reminders are now **enabled**. "
                "I'll DM you when your 12-hour vote bonus expires!"
            ))
        else:
            msg = t(_p(
                'cmd:votereminder|disabled',
                "Vote reminders are now **disabled**. "
                "You won't receive DMs when your vote bonus expires."
            ))

        await ctx.reply(msg, ephemeral=True)
    # --- END AI-MODIFIED ---

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: Improved thank-you DM with gem reward info, tier bonuses, and premium upsell
    # --- Original code (commented out for rollback) ---
    # async def _send_thanks_dm(self, userid: int):
    #     user = self.bot.get_user(userid)
    #     if user is None:
    #         try:
    #             user = await self.bot.fetch_user(userid)
    #         except discord.HTTPException:
    #             logger.warning(
    #                 f"Could not find voting user <uid: {userid}> to send thanks."
    #             )
    #             return
    #
    #     t = self.bot.translator.t
    #     luser = await self.bot.core.lions.fetch_user(userid)
    #     locale = await self.bot.get_cog('BabelCog').get_user_locale(userid)
    #     ctx_locale.set(locale)
    #
    #     embed = discord.Embed(
    #         colour=discord.Colour.brand_green(),
    #         title=t(_p(
    #             'embed:voting_thanks|title',
    #             "Thank you for supporting me on Top.gg! {yay}"
    #         )).format(yay=self.bot.config.emojis.lionyay),
    #         description=t(_p(
    #             'embed:voting_thanks|desc',
    #             "Thank you for supporting us, enjoy your LionCoins boost!"
    #         ))
    #
    #     ).set_image(
    #         url="https://cdn.discordapp.com/attachments/908283085999706153/932737228440993822/lion-yay.png"
    #     )
    #
    #     try:
    #         await user.send(embed=embed)
    #     except discord.HTTPException:
    #         logger.warning(
    #             f"Could not send voting thanks to user <uid: {userid}>."
    #         )
    # --- End original code ---
    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Improved thank-you DM -- shows tier-specific gem count on vote button,
    # explains what gems can buy, removes unused luser fetch, fixes broken /dashboard/supporter link
    async def _send_thanks_dm(self, userid: int, *, tier: str = 'NONE', gems_earned: int = 5):
        user = self.bot.get_user(userid)
        if user is None:
            try:
                user = await self.bot.fetch_user(userid)
            except discord.HTTPException:
                logger.warning(
                    f"Could not find voting user <uid: {userid}> to send thanks."
                )
                return

        t = self.bot.translator.t
        locale = await self.bot.get_cog('BabelCog').get_user_locale(userid)
        ctx_locale.set(locale)

        coin_boost = VOTE_LIONCOIN_BOOST.get(tier, 1.25)
        gold_boost = VOTE_LG_GOLD_BOOST.get(tier, 1.0)
        gem_emoji = self.bot.config.emojis.gem if hasattr(self.bot.config.emojis, 'gem') else '\U0001f48e'

        bonuses = t(_p(
            'embed:voting_thanks_v3|bonuses',
            "**Active Bonuses (12 hours):**\n"
            "{coin} **{coin_boost}x** LionCoin earnings\n"
            "{gem} **+{gems}** LionGems earned"
        )).format(
            coin=self.bot.config.emojis.coin,
            coin_boost=coin_boost,
            gem=gem_emoji,
            gems=gems_earned,
        )

        if gold_boost > 1.0:
            bonuses += "\n" + t(_p(
                'embed:voting_thanks_v3|gold_bonus',
                "\U0001fa99 **{gold_boost}x** LionGotchi Gold earnings"
            )).format(gold_boost=gold_boost)

        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Removed gem-based server premium reference (now Stripe subscriptions)
        gem_uses = t(_p(
            'embed:voting_thanks_v3|gem_uses',
            "\n**What can you do with LionGems?**\n"
            "\u2022 Buy **profile skins** to customize your look\n"
            "\u2022 Gift gems to friends with `/gift`\n"
            "\u2022 Subscribe to **server premium** at lionbot.org/donate"
        ))
        # --- END AI-MODIFIED ---

        description = t(_p(
            'embed:voting_thanks_v3|desc',
            "Thank you for voting for LionBot! {yay}\n\n{bonuses}\n{gem_uses}"
        )).format(
            yay=self.bot.config.emojis.lionyay,
            bonuses=bonuses,
            gem_uses=gem_uses,
        )

        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'embed:voting_thanks_v3|title',
                "Vote Received! {yay}"
            )).format(yay=self.bot.config.emojis.lionyay),
            description=description,
        ).set_image(
            url="https://cdn.discordapp.com/attachments/908283085999706153/932737228440993822/lion-yay.png"
        )

        if tier != 'NONE':
            embed.set_footer(text=t(_p(
                'embed:voting_thanks_v3|footer_subscriber',
                "LionHeart {tier} \u2022 Enhanced vote rewards active"
            )).format(tier=tier.replace('_', ' ').title()))
        else:
            # --- AI-MODIFIED (2026-03-21) ---
            # Purpose: Replace /donate command with website link, show missed gems, add supporter appreciation message
            extra_gems = VOTE_GEM_REWARDS['LIONHEART_PLUS_PLUS'] - gems_earned
            embed.add_field(
                name=t(_p(
                    'embed:voting_thanks_v3|upsell_title',
                    "\U0001f31f Earn more with LionHeart!"
                )),
                value=t(_p(
                    'embed:voting_thanks_v3|upsell_desc',
                    "You could have earned **{extra_gems} more gems** this vote as an active LionHeart supporter! "
                    "That's **up to {max_gems} gems** and **2x LionCoins** per vote.\n\n"
                    "Your support helps us keep building new features and pay for server maintenance "
                    "to keep LionBot running for everyone \u2014 we really appreciate it! \u2764\ufe0f\n\n"
                    "\U0001f517 **[Become a Supporter]({donate_url})**"
                )).format(
                    extra_gems=extra_gems,
                    max_gems=VOTE_GEM_REWARDS['LIONHEART_PLUS_PLUS'],
                    donate_url=f"{WEBSITE_URL}/donate",
                ),
                inline=False,
            )
            # --- END AI-MODIFIED ---

        view = discord.ui.View()
        view.add_item(self.vote_button(gems=gems_earned))

        try:
            await user.send(embed=embed, view=view)
        except discord.HTTPException:
            logger.warning(
                f"Could not send voting thanks to user <uid: {userid}>."
            )
    # --- END AI-MODIFIED ---

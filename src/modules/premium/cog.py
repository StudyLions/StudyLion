from typing import Optional
import asyncio
# --- AI-MODIFIED (2026-05-29) ---
# Purpose: monotonic clock for the is_premium_guild() short-TTL cache
import time as _time
# --- END AI-MODIFIED ---

import discord
from discord.ext import commands as cmds
import discord.app_commands as appcmds

from meta import conf, WEBSITE_URL

from discord.ui.button import Button, ButtonStyle
from discord.ui.text_input import TextInput, TextStyle

from meta import LionCog, LionBot, LionContext
from meta.errors import SafeCancellation, UserInputError
from meta.logger import log_wrap
from utils.lib import utc_now
from utils.ui import FastModal
from wards import sys_admin_ward
from constants import MAX_COINS

from . import logger, babel
from .data import PremiumData, GemTransactionType
from .ui.transactions import TransactionList
from .ui.premium import PremiumUI
from .errors import GemTransactionFailed, BalanceTooLow, BalanceTooHigh

_p = babel._p


class PremiumCog(LionCog):
    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Use central config-driven URL instead of hardcoded domain
    buy_gems_link = f"{WEBSITE_URL}/donate"
    # --- END AI-MODIFIED ---

    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data: PremiumData = bot.db.load_registry(PremiumData())

        self.gem_logger: Optional[discord.Webhook] = None

        # --- AI-MODIFIED (2026-05-29) ---
        # Purpose: Short-TTL cache for is_premium_guild() so server-premium
        # renewals written by the website/Stripe webhook are reflected within
        # _premium_status_ttl seconds, instead of being masked for the lifetime
        # of the shard process by PremiumGuild's model cache (_cache_={}).
        # Maps guildid -> (monotonic_timestamp, is_premium).
        self._premium_status_cache: dict[int, tuple[float, bool]] = {}
        self._premium_status_ttl: float = 300.0
        # --- END AI-MODIFIED ---

    async def cog_load(self):
        await self.data.init()

        if (leo_setting_cog := self.bot.get_cog('LeoSettings')) is not None:
            self.crossload_group(self.leo_group, leo_setting_cog.leo_group)

        if (gem_log_url := self.bot.config.endpoints.get('gem_log', None)) is not None:
            self.gem_logger = discord.Webhook.from_url(gem_log_url, session=self.bot.web_client)


    # ----- API -----
    def buy_gems_button(self) -> Button:
        t = self.bot.translator.t

        button = Button(
            style=ButtonStyle.link,
            label=t(_p(
                'button:gems|label',
                "Buy Gems"
            )),
            emoji=self.bot.config.emojis.gem,
            url=self.buy_gems_link,
        )
        return button

    async def get_gem_balance(self, userid: int) -> int:
        """
        Get the up-to-date gem balance for this user.

        Creates the User row if it does not already exist.
        """
        record = await self.bot.core.data.User.fetch(userid, cached=False)
        if record is None:
            record = await self.bot.core.data.User.create(userid=userid)
        return record.gems

    async def get_gift_count(self, userid: int) -> int:
        """
        Compute the number of gifts this user has sent, by counting Transaction rows.
        """
        record = await self.data.GemTransaction.table.select_where(
            from_account=userid,
            transaction_type=GemTransactionType.GIFT,
        ).select(
            gift_count='COUNT(*)'
        ).with_no_adapter()

        return record[0]['gift_count'] or 0

    async def is_premium_guild(self, guildid: int) -> bool:
        """
        Check whether the given guild currently has premium status.
        """
        # --- AI-REPLACED (2026-05-29) ---
        # Reason: PremiumGuild uses a process-lifetime model cache (_cache_={}),
        # and server-premium is written EXTERNALLY by the Next.js/Stripe webhook
        # via Prisma -- the bot never mutates its own cached row. So once a shard
        # cached a guild's row, a later renewal/extension stayed invisible until
        # the shard restarted. Observed in the wild: guild 1498620321421332541
        # ("Kevinmathscience") renewed to premium_until=2026-06-28 in the DB, but
        # shard leo-32-30 (8d uptime) kept treating it as lapsed for >12h,
        # silently disabling anti_afk, leaderboard_autopost and sticky_messages.
        # What the new code does better: bypasses the stale model cache
        # (cached=False) but memoises the resulting boolean for a short TTL, so
        # renewals are reflected within _premium_status_ttl seconds while the hot
        # path (every voice/text reward) still avoids a per-call DB round-trip.
        # --- Original code (commented out for rollback) ---
        # row = await self.data.PremiumGuild.fetch(guildid)
        # now = utc_now()
        #
        # premium = (row is not None) and row.premium_until and (row.premium_until > now)
        # return premium
        # --- End original code ---
        now_mono = _time.monotonic()
        cached = self._premium_status_cache.get(guildid)
        if cached is not None and (now_mono - cached[0]) < self._premium_status_ttl:
            return cached[1]

        row = await self.data.PremiumGuild.fetch(guildid, cached=False)
        premium = bool(
            (row is not None) and row.premium_until and (row.premium_until > utc_now())
        )
        self._premium_status_cache[guildid] = (now_mono, premium)
        return premium
        # --- END AI-REPLACED ---

    # --- AI-MODIFIED (2026-04-26) ---
    # Purpose: LionHeart subscription tier checking for user perks.
    #
    # Cache-bypass fix (2026-04-26): PremiumData.UserSubscription is declared
    # with `_cache_ = {}` (a plain dict -> strong references, lifetime of the
    # process). The LionHeart subscription state is written exclusively by the
    # Next.js Stripe webhook straight into `user_subscriptions` via Prisma --
    # the bot never mutates its own cached row on tier change. Result: every
    # shard that cached a user's row BEFORE an upgrade/downgrade/cancellation
    # keeps returning the stale tier until the shard process restarts.
    #
    # Symptoms seen in the wild: user 994057257245483141 upgraded LH+ -> LH++
    # via the Stripe portal on 2026-04-25, DB row was correctly updated, but
    # the LionGotchi pet card on whatever shard served his server kept
    # displaying "+25% Gold (LionHeart+)" / "+40% Drop Rate (LionHeart+ +
    # Server Premium)" / "+25% Harvest Gold (LionHeart+)" -- i.e. the stale
    # LIONHEART_PLUS boosts. Gameplay math (voice/text gold, drop rate,
    # harvest gold, seed discount, uproot refund) was also using the wrong
    # tier, so the user was being shortchanged by ~25 percentage points of
    # gold/drops they had paid for.
    #
    # Fix: pass cached=False so every call goes to Postgres. This is safe to
    # do unconditionally because:
    #   (a) get_user_subscription_tier is called on-demand during user
    #       interactions (/me, harvest, seed buy, stats card render,
    #       leaderboard, embed color, topgg reward) -- NOT in any hot loop.
    #   (b) user_subscriptions.userid is a primary key so the read is a
    #       sub-millisecond indexed lookup against a table that is orders of
    #       magnitude smaller than member/guild tables.
    #   (c) LionHeart subs change rarely (monthly renewals, occasional
    #       upgrades/cancels) so even the historical cache hit rate was
    #       high only because the data was static -- not because the cache
    #       was actually protecting us from load.
    #
    # NOTE: PremiumGuild ALSO uses `_cache_ = {}` and ALSO gets external
    # writes from the Stripe webhook (new server-premium purchases, gem
    # top-ups, extensions). That produced the same class of stale-cache bug
    # for `is_premium_guild()`.
    # --- AI-MODIFIED (2026-05-29) ---
    # FIXED (2026-05-29): is_premium_guild() now bypasses the model cache
    # (cached=False) behind a short per-guild TTL cache (_premium_status_cache /
    # _premium_status_ttl), so renewals reflect within the TTL while the hot
    # path still avoids a per-call DB hit. See is_premium_guild() above.
    # --- END AI-MODIFIED ---
    async def get_user_subscription_tier(self, userid: int) -> str:
        """
        Get the active subscription tier for a user.

        Returns the tier string (e.g. 'LIONHEART', 'LIONHEART_PLUS', 'LIONHEART_PLUS_PLUS')
        or 'NONE' if no active subscription.
        """
        try:
            row = await self.data.UserSubscription.fetch(userid, cached=False)
            if row is not None and row.status == 'ACTIVE':
                return row.tier or 'NONE'
        except Exception:
            logger.warning(f"Failed to fetch subscription tier for {userid}", exc_info=True)
        return 'NONE'
    # --- END AI-MODIFIED ---

    @log_wrap(isolate=True)
    async def _add_gems(self, userid: int, amount: int):
        """
        Transaction helper method to atomically add `amount` gems to account `userid`,
        creating the account if required.

        Do not use this method for a gem transaction. Use `gem_transaction` instead.
        """
        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            async with conn.transaction():
                model = self.bot.core.data.User
                rows = await model.table.update_where(userid=userid).set(gems=model.gems + amount)
                if not rows:
                    # User does not exist, create it
                    if amount < 0:
                        raise BalanceTooLow
                    if amount > MAX_COINS:
                        raise BalanceTooHigh
                    row = (await model.create(userid=userid, gems=amount)).data
                else:
                    row = rows[0]

                if row['gems'] < 0:
                    raise BalanceTooLow

    async def gem_transaction(
        self,
        transaction_type: GemTransactionType,
        *,
        actorid: int,
        from_account: Optional[int], to_account: Optional[int],
        amount: int, description: str,
        note: Optional[str] = None, reference: Optional[str] = None,
    ) -> PremiumData.GemTransaction:
        """
        Perform a gem transaction with the given parameters.

        This atomically creates a row in the 'gem_transactions' table,
        updates the account balances,
        and posts in the gem audit log.

        Parameters
        ----------
        transaction_type: GemTransactionType
            The type of transaction.
        actorid: int
            The userid of the actor who initiated this transaction.
            Automatic actions (e.g. webhook triggered) may have their own unique id.
        from_account: Optional[int]
            The userid of the source account.
            May be `None` if there is no source account (e.g. manual modification by admin).
        to_account: Optional[int]
            The userid of the destination account.
            May be `None` if there is no destination account.
        amount: int
            The number of LionGems to transfer.
        description: str
            An informative description of the transaction for auditing purposes.
            Should include the pathway (e.g. command) through which the transaction was executed.
        note: Optional[str]
            Optional user-readable note added by the actor.
            Usually attached in a notification visible by the target.
            (E.g. thanks message from system/admin, or note attached to gift.)
        reference: str
            Optional admin-readable transaction reference.
            This may be the message link of a command message,
            or an external id/reference for an automatic transaction.
        
        Raises
        ------
        BalanceTooLow:
            Raised if either source or target account would go below 0.
        """
        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            async with conn.transaction():
                if from_account is not None:
                    await self._add_gems(from_account, -amount)
                if to_account is not None:
                    await self._add_gems(to_account, amount)

                row = await self.data.GemTransaction.create(
                    transaction_type=transaction_type,
                    actorid=actorid,
                    from_account=from_account,
                    to_account=to_account,
                    amount=amount,
                    description=description,
                    note=note,
                    reference=reference,
                )
        logger.info(
            f"LionGem Transaction performed. Transaction data: {row!r}"
        )
        await self.audit_log(row)
        return row

    async def audit_log(self, row: PremiumData.GemTransaction):
        """
        Log the provided gem transaction to the global gem audit log.

        If this fails, or the audit log does not exist, logs a warning.
        """
        posted = False
        if self.gem_logger is not None:
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                title=f"Gem Transaction #{row.transactionid}",
                timestamp=row._timestamp,
            )
            embed.add_field(name="Type", value=row.transaction_type.name)
            embed.add_field(name="Amount", value=str(row.amount))
            embed.add_field(name="Actor", value=f"<@{row.actorid}>")
            embed.add_field(name="From Account", value=f"<@{row.from_account}>" if row.from_account else 'None')
            embed.add_field(name="To Account", value=f"<@{row.to_account}>" if row.to_account else 'None')
            embed.add_field(name='Description', value=str(row.description), inline=False)
            if row.note:
                embed.add_field(name='Note', value=str(row.note), inline=False)
            if row.reference:
                embed.add_field(name='Reference', value=str(row.reference), inline=False)

            try:
                await self.gem_logger.send(embed=embed)
                posted = True
            except discord.HTTPException:
                pass

        if not posted:
            logger.warning(
                f"Missed gem audit logging for gem transaction: {row!r}"
            )

    # ----- User Commands -----
    @cmds.hybrid_command(
        name=_p('cmd:free', "free"),
        description=_p(
            'cmd:free|desc',
            "Get free LionGems!"
        )
    )
    async def cmd_free(self, ctx: LionContext):
        t = self.bot.translator.t
        content = t(_p(
            'cmd:free|embed|description',
            "You can get free LionGems by sharing our project on your Discord server and social media!\n"
            "If you have well-established, or YouTube, Instagram, and TikTok accounts,"
            " we will reward you for creating videos and content about the bot.\n"
            "If you have a big server, you can promote our project and get LionGems in return.\n"
            "For more details, contact `arihoresh` or open a Ticket in the [support server](https://discord.gg/studylions)."
        ))
        thumb = "https://cdn.discordapp.com/attachments/890619584158265405/972791204498530364/Untitled_design_44.png"
        title = t(_p(
            'cmd:free|embed|title',
            "Get FREE LionGems!"
        ))
        embed = discord.Embed(
            title=title,
            description=content,
            colour=0x41f097
        )
        embed.set_thumbnail(url=thumb)

        await ctx.reply(embed=embed)

    @cmds.hybrid_command(
        name=_p('cmd:gift', "gift"),
        description=_p(
            'cmd:gift|desc',
            "Gift your LionGems to another user!"
        )
    )
    @appcmds.rename(
        user=_p('cmd:gift|param:user', "user"),
        amount=_p('cmd:gift|param:amount', "amount"),
        note=_p('cmd:gift|param:note', "note"),
    )
    @appcmds.describe(
        user=_p(
            'cmd:gift|param:user|desc',
            "User to which you want to gift your LionGems."
        ),
        amount=_p(
            'cmd:gift|param:amount|desc',
            "Number of LionGems to gift."
        ),
        note=_p(
            'cmd:gift|param:note|desc',
            "Optional note to attach to your gift."
        ),
    )
    async def cmd_gift(self, ctx: LionContext,
                       user: discord.User,
                       amount: appcmds.Range[int, 1, MAX_COINS],
                       note: Optional[appcmds.Range[str, 1, 1024]] = None):
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        # Validate target
        if user.bot:
            raise UserInputError(
                t(_p(
                    'cmd:gift|error:target_bot',
                    "You cannot gift LionGems to bots!"
                ))
            )

        if user.id == ctx.author.id:
            raise UserInputError(
                t(_p(
                    'cmd:gift|error:target_is_author',
                    "You cannot gift LionGems to yourself!"
                ))
            )

        # Prepare and open gift confirmation modal
        amount_field = TextInput(
            label=t(_p(
                'cmd:gift|modal:confirm|field:amount|label',
                "Number of LionGems to Gift"
            )),
            default=str(amount),
            required=True,
        )
        note_field = TextInput(
            label=t(_p(
                'cmd:gift|modal:confirm|field:note|label',
                "Add an optional note to your gift"
            )),
            default=note or '',
            required=False,
            max_length=1024,
            style=TextStyle.long,
        )
        modal = FastModal(
            amount_field, note_field,
            title=t(_p(
                'cmd:gift|modal:confirm|title',
                "Confirm LionGem Gift"
            ))
        )

        await ctx.interaction.response.send_modal(modal)

        try:
            interaction = await modal.wait_for(timeout=300)
        except asyncio.TimeoutError:
            # Presume user cancelled and wants to abort
            raise SafeCancellation

        await interaction.response.defer(thinking=False)

        # Parse amount
        amountstr = amount_field.value
        if not amountstr.isdigit():
            raise UserInputError(
                t(_p(
                    'cmd:gift|error:parse_amount',
                    "Could not parse `{provided}` as a number!"
                )).format(provided=amountstr)
            )
        amount = int(amountstr)

        if amount == 0:
            raise UserInputError(
                t(_p(
                    'cmd:gift|error:amount_zero',
                    "Cannot gift `0` gems."
                ))
            )

        # Get author's balance, make sure they have enough
        author_balance = await self.get_gem_balance(ctx.author.id)
        if author_balance < amount:
            raise UserInputError(
                t(_p(
                    'cmd:gift|error:author_balance_too_low',
                    "Insufficient balance to send {gem}**{amount}**!\n"
                    "Current balance: {gem}**{balance}**"
                )).format(
                    gem=self.bot.config.emojis.gem,
                    amount=amount,
                    balance=author_balance,
                )
            )

        # Everything seems to be in order, run the transaction
        try:
            transaction = await self.gem_transaction(
                GemTransactionType.GIFT,
                actorid=ctx.author.id,
                from_account=ctx.author.id, to_account=user.id,
                amount=amount,
                description="Gift given through command '/gift'",
                note=note_field.value or None
            )
        except BalanceTooLow:
            raise UserInputError(
                t(_p(
                    'cmd:gift|error:balance_too_low',
                    "Insufficient Balance to complete gift!"
                ))
            )

        # Attempt to send note to user

        thumb = "https://cdn.discordapp.com/attachments/925799205954543636/938704034578194443/C85AF926-9F75-466F-9D8E-D47721427F5D.png"
        icon = "https://cdn.discordapp.com/attachments/925799205954543636/938703943683416074/4CF1C849-D532-4DEC-B4C9-0AB11F443BAB.png"
        desc = t(_p(
            'cmd:gift|target_msg|desc',
            "You were just gifted {gem}**{amount}** by {user}!\n"
            "To use them, use the command {skin_cmd} to change your graphics skin!"
        )).format(
            gem=self.bot.config.emojis.gem,
            amount=amount,
            user=ctx.author.mention,
            skin_cmd=self.bot.core.mention_cmd('my skin'),
        )
        embed = discord.Embed(
            description=desc,
            colour=discord.Colour.orange()
        )
        embed.set_thumbnail(url=thumb)
        embed.set_author(
            name=t(_p('cmd:gift|target_msg|author:name', "LionGems Delivery!")),
            icon_url=icon,
        )
        embed.set_footer(
            text=t(_p(
                'cmd:gift|target_msg|footer:text',
                "You now have {balance} LionGems"
            )).format(
                balance=await self.get_gem_balance(user.id),
            )
        )
        embed.timestamp = utc_now()

        note = note_field.value
        if note:
            embed.add_field(
                name=t(_p(
                    'cmd:gift|target_msg|field:note|name',
                    "The sender attached a note"
                )),
                value=note
            )

        notify_sent = False
        try:
            await user.send(embed=embed)
            notify_sent = True
        except discord.HTTPException:
            logger.info(
                f"Could not send LionGem gift target their gift notification. Transaction {transaction.transactionid}"
            )

        # Finally, send the ack back to the author
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'cmd:gift|embed:success|title',
                "Gift Sent!"
            )),
            description=t(_p(
                'cmd:gift|embed:success|description',
                "Your gift of {gem}**{amount}** is on its way to {target}!"
            )).format(
                gem=self.bot.config.emojis.gem,
                amount=amount,
                target=user.mention,
            )
        )
        embed.set_footer(
            text=t(_p(
                'cmd:gift|embed:success|footer',
                "New Balance: {balance} LionGems",
            )).format(balance=await self.get_gem_balance(ctx.author.id))
        )
        if not notify_sent:
            embed.add_field(
                name="",
                value=t(_p(
                    'cmd:gift|embed:success|field:notify_failed|value',
                    "Unfortunately, I couldn't tell them about it! "
                    "They might have direct messages with me turned off."
                ))
            )

        await ctx.reply(embed=embed, ephemeral=True)

    @cmds.hybrid_command(
        name=_p('cmd:premium', "premium"),
        # --- AI-MODIFIED (2026-03-22) ---
        # Purpose: Updated description to reflect Stripe subscription model
        description=_p(
            'cmd:premium|desc',
            "View server premium status and subscribe!"
        )
        # --- END AI-MODIFIED ---
    )
    @appcmds.guild_only
    async def cmd_premium(self, ctx: LionContext):
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        ui = PremiumUI(self.bot, ctx.guild, ctx.luser, callerid=ctx.author.id)
        await ui.run(ctx.interaction)
        await ui.wait()

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: /donate slash command showing LionHeart tiers and links
    @cmds.hybrid_command(
        name=_p('cmd:donate', "donate"),
        description=_p(
            'cmd:donate|desc',
            "Support LionBot and unlock premium perks!"
        )
    )
    async def cmd_donate(self, ctx: LionContext):
        t = self.bot.translator.t

        embed = discord.Embed(
            title=t(_p(
                'cmd:donate|embed|title',
                "❤️ Support LionBot"
            )),
            description=t(_p(
                'cmd:donate|embed|description',
                # --- AI-MODIFIED (2026-03-22) ---
                # Purpose: Updated pricing from USD to EUR
                "Become a **LionHeart** supporter to unlock exclusive perks!\n\n"
                "🦁 **LionHeart** — €4.99/mo\n"
                "• 500 LionGems/month\n"
                "• 10 gems per vote (vs 5)\n"
                "• 1.5x vote bonuses\n"
                "• +15% drop rates & farm boosts\n"
                "• Animated glowing profile cards (Blue)\n\n"
                "🦁 **LionHeart+** — €9.99/mo\n"
                "• 1,200 LionGems/month\n"
                "• 15 gems per vote\n"
                "• 1.75x vote bonuses\n"
                "• +25% drop rates & farm boosts\n"
                "• Animated glowing profile cards (Pink)\n\n"
                "🦁 **LionHeart++** — €19.99/mo\n"
                "• 3,000 LionGems/month\n"
                "• 30 gems per vote\n"
                "• 2.0x vote bonuses\n"
                "• +50% drop rates & max farm boosts\n"
                "• Plants never die from drought!\n"
                "• Animated glowing profile cards (Gold)"
                # --- END AI-MODIFIED ---
            )),
            color=discord.Color.gold()
        )

        user_tier = await self.get_user_subscription_tier(ctx.author.id)
        if user_tier != 'NONE':
            tier_names = {
                'LIONHEART': 'LionHeart',
                'LIONHEART_PLUS': 'LionHeart+',
                'LIONHEART_PLUS_PLUS': 'LionHeart++',
            }
            embed.add_field(
                name=t(_p(
                    'cmd:donate|embed|field:current_tier|name',
                    "Your Current Tier"
                )),
                value=t(_p(
                    'cmd:donate|embed|field:current_tier|value',
                    "✨ **{tier}**"
                )).format(tier=tier_names.get(user_tier, user_tier)),
                inline=False
            )

        # --- AI-MODIFIED (2026-03-17) ---
        # Purpose: Use central WEBSITE_URL for footer and button URLs
        embed.set_footer(
            text=t(_p(
                'cmd:donate|embed|footer',
                "Subscribe on our website • {url}/donate"
            )).format(url=WEBSITE_URL)
        )

        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label=t(_p('cmd:donate|button:subscribe|label', "Subscribe Now")),
            url=f"{WEBSITE_URL}/donate",
            style=discord.ButtonStyle.link,
            emoji="❤️"
        ))
        view.add_item(discord.ui.Button(
            label=t(_p('cmd:donate|button:manage|label', "Manage Subscription")),
            url=f"{WEBSITE_URL}/donate#manage",
            style=discord.ButtonStyle.link,
            emoji="⚙️"
        ))
        # --- END AI-MODIFIED ---

        await ctx.reply(embed=embed, view=view)
    # --- END AI-MODIFIED ---

    # ----- Owner Commands -----
    @LionCog.placeholder_group
    @cmds.hybrid_group("leo", with_app_command=False)
    async def leo_group(self, ctx: LionContext):
        ...


    @leo_group.command(
        name=_p('cmd:leo_gems', "gems"),
        description=_p(
            'cmd:leo_gems|desc',
            "View and adjust a user's LionGem balance."
        )
    )
    @appcmds.rename(
        target=_p('cmd:leo_gems|param:target', "target"),
        adjustment=_p('cmd:leo_gems|param:adjustment', "adjustment"),
        note=_p('cmd:leo_gems|param:note', "note"),
        reason=_p('cmd:leo_gems|param:reason', "reason")
    )
    @appcmds.describe(
        target=_p(
            'cmd:leo_gems|param:target|desc',
            "Target user you wish to view or modify LionGems for."
        ),
        adjustment=_p(
            'cmd:leo_gems|param:adjustment|desc',
            "Number of LionGems to add to the target's balance (may be negative to remove)"
        ),
        note=_p(
            'cmd:leo_gems|param:note|desc',
            "Optional note to attach to the delivery message when adding LionGems."
        ),
        reason=_p(
            'cmd:leo_gems|param:reason|desc',
            'Optional reason or context to add to the gem audit log for this transaction.'
        )
    )
    @sys_admin_ward
    async def cmd_leo_gems(self, ctx: LionContext,
                           target: discord.User,
                           adjustment: Optional[int] = None,
                           note: Optional[appcmds.Range[str, 0, 1024]] = None,
                           reason: Optional[appcmds.Range[str, 0, 1024]] = None,):
        if not ctx.interaction:
            return
        t = self.bot.translator.t

        if adjustment is None or adjustment == 0:
            # History viewing pathway
            ui = TransactionList(self.bot, target.id, callerid=ctx.author.id)
            await ui.run(ctx.interaction)
            await ui.wait()
        else:
            # Adjustment path
            # Show confirmation modal with note and reason
            adjustment_field = TextInput(
                label=t(_p(
                    'cmd:leo_gems|adjust|modal:confirm|field:amount|label',
                    "Number of LionGems to add. May be negative."
                )),
                default=str(adjustment),
                required=True,
            )
            note_field = TextInput(
                label=t(_p(
                    'cmd:leo_gems|adjust|modal:confirm|field:note|label',
                    "Optional note to attach to delivery message."
                )),
                default=note,
                style=TextStyle.long,
                max_length=1024,
                required=False,
            )
            reason_field = TextInput(
                label=t(_p(
                    'cmd:leo_gems|adjust|modal:confirm|field:reason|label',
                    "Optional reason to add to the audit log."
                )),
                default=reason,
                style=TextStyle.long,
                max_length=1024,
                required=False,
            )

            modal = FastModal(
                adjustment_field, note_field, reason_field,
                title=t(_p(
                    'cmd:leo_gems|adjust|modal:confirm|title',
                    "Confirm LionGem Adjustment"
                ))
            )
            await ctx.interaction.response.send_modal(modal)

            try:
                interaction = await modal.wait_for(timeout=300)
            except asyncio.TimeoutError:
                raise SafeCancellation

            await interaction.response.defer(thinking=False)

            # Parse values
            try:
                amount = int(adjustment_field.value)
            except ValueError:
                raise UserInputError(
                    t(_p(
                        'cmd:leo_gems|adjust|error:parse_adjustment',
                        "Could not parse `{given}` as an integer."
                    )).format(given=adjustment_field.value)
                )
            note = note_field.value or None
            reason = reason_field.value or None

            # Run transaction
            try:
                transaction = await self.gem_transaction(
                    GemTransactionType.ADMIN,
                    actorid=ctx.author.id,
                    from_account=None, to_account=target.id,
                    amount=amount,
                    description=f"Admin balance adjustment with '/leo gems'.\n{reason}",
                    note=note
                )
            except GemTransactionFailed:
                raise UserInputError(
                    t(_p(
                        'cmd:leo_gems|adjust|error:unknown',
                        "Balance adjustment failed! Check logs for more information."
                    ))
                )
            # DM user with note if applicable
            if amount > 0:
                thumb = "https://cdn.discordapp.com/attachments/925799205954543636/938704034578194443/C85AF926-9F75-466F-9D8E-D47721427F5D.png"
                icon = "https://cdn.discordapp.com/attachments/925799205954543636/938703943683416074/4CF1C849-D532-4DEC-B4C9-0AB11F443BAB.png"
                desc = t(_p(
                    'cmd:leo_gems|adjust|target_msg|desc',
                    "You were given {gem}**{amount}**!\n"
                    "To use them, use the command {skin_cmd} to change your graphics skin!"
                )).format(
                    gem=self.bot.config.emojis.gem,
                    amount=amount,
                    skin_cmd=self.bot.core.mention_cmd('my skin'),
                )
                embed = discord.Embed(
                    description=desc,
                    colour=discord.Colour.orange()
                )
                embed.set_thumbnail(url=thumb)
                embed.set_author(
                    name=t(_p('cmd:leo_gems|adjust|target_msg|author:name', "LionGems Delivery!")),
                    icon_url=icon,
                )
                embed.set_footer(
                    text=t(_p(
                        'cmd:leo_gems|adjust|target_msg|footer:text',
                        "You now have {balance} LionGems"
                    )).format(
                        balance=await self.get_gem_balance(target.id),
                    )
                )
                embed.timestamp = utc_now()

                note = note_field.value
                if note:
                    embed.add_field(
                        name=t(_p(
                            'cmd:lion_gems|adjust|target_msg|field:note|name',
                            "Note"
                        )),
                        value=note
                    )

                try:
                    await target.send(embed=embed)
                    target_notified = True
                except discord.HTTPException:
                    target_notified = False
            else:
                target_notified = None

            # Ack the operation
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'cmd:lion_gems|adjust|embed:success|title',
                    "Success"
                )),
                description=t(_p(
                    'cmd:lion_gems|adjust|embed:success|description',
                    "Added {gem}**{amount}** to {target}'s account.\n"
                    "They now have {gem}**{balance}**"
                )).format(
                    gem=self.bot.config.emojis.gem,
                    target=target.mention,
                    amount=amount,
                    balance=await self.get_gem_balance(target.id),
                )
            )
            if target_notified is False:
                embed.add_field(
                    name="",
                    value=t(_p(
                        'cmd:lion_gems|adjust|embed:success|field:notify_failed|value',
                        "Could not notify the target, they probably have direct messages disabled."
                    ))
                )

            await ctx.reply(embed=embed, ephemeral=True)

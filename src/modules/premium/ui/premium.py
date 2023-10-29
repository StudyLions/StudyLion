from typing import Optional, TYPE_CHECKING, NamedTuple
import asyncio
import datetime as dt

import discord
from discord.ui.button import button, Button, ButtonStyle
from psycopg import sql

from meta import LionBot, conf
from meta.logger import log_wrap
from core.lion_user import LionUser
from babel.translator import LazyStr
from meta.errors import ResponseTimedOut, UserInputError
from data import RawExpr
from modules.premium.errors import BalanceTooLow

from utils.ui import MessageUI, Confirm, AButton
from utils.lib import MessageArgs, utc_now

from .. import babel, logger
from ..data import GemTransactionType, PremiumData

if TYPE_CHECKING:
    from ..cog import PremiumCog

_p = babel._p


class PremiumPlan(NamedTuple):
    text: LazyStr
    label: LazyStr
    emoji: Optional[discord.PartialEmoji | discord.Emoji | str]
    duration: int
    price: int


plans = [
    PremiumPlan(
        _p('plan:three_months|text', "three months"),
        _p('plan:three_months|label', "Three Months"),
        None,
        90,
        4000
    ),
    PremiumPlan(
        _p('plan:one_year|text', "one year"),
        _p('plan:one_year|label', "One Year"),
        None,
        365,
        12000
    ),
    PremiumPlan(
        _p('plan:one_month|text', "one month"),
        _p('plan:one_month|label', "One Month"),
        None,
        30,
        1500
    ),
]


class PremiumUI(MessageUI):
    def __init__(self, bot: LionBot, guild: discord.Guild, luser: LionUser, **kwargs):
        super().__init__(**kwargs)

        self.bot = bot
        self.guild = guild
        self.luser = luser

        self.cog: 'PremiumCog' = bot.get_cog('PremiumCog')  # type: ignore

        # UI State
        self.premium_status: Optional[PremiumData.PremiumGuild] = None

        self.plan_buttons = self._plan_buttons()
        self.link_button = self.cog.buy_gems_button()

    # ----- API -----
    # ----- UI Components -----

    async def plan_button(self, press: discord.Interaction, pressed: Button, plan: PremiumPlan):
        t = self.bot.translator.t

        # Check Balance
        if self.luser.data.gems < plan.price:
            raise UserInputError(
                t(_p(
                    'ui:premium|button:plan|error:insufficient_gems',
                    "You do not have enough LionGems to purchase this plan!"
                ))
            )

        # Confirm Purchase
        confirm_msg = t(_p(
            'ui:premium|button:plan|confirm|desc',
            "Contributing **{plan_text}** of premium subscription for this server"
            " will cost you {gem}**{plan_price}**.\n"
            "Are you sure you want to proceed?"
        )).format(
            plan_text=t(plan.text),
            gem=self.bot.config.emojis.gem,
            plan_price=plan.price,
        )
        confirm = Confirm(confirm_msg, press.user.id)
        confirm.embed.title = t(_p(
            'ui:premium|button:plan|confirm|title',
            "Confirm Server Upgrade"
        ))
        confirm.embed.set_footer(
            text=t(_p(
                'ui:premium|button:plan|confirm|footer',
                "Your current balance is {balance} LionGems"
            )).format(balance=self.luser.data.gems)
        )
        confirm.embed.colour = 0x41f097

        try:
            result = await confirm.ask(press, ephemeral=True)
        except ResponseTimedOut:
            result = False
        if not result:
            await press.followup.send(
                t(_p(
                    'ui:premium|button:plan|confirm|cancelled',
                    "Purchase cancelled! No LionGems were deducted from your account."
                )),
                ephemeral=True
            )
            return

        # Write transaction, plan contribution, and new plan status, with potential rollback
        try:
            await self._do_premium_upgrade(plan)
        except BalanceTooLow:
            raise UserInputError(
                t(_p(
                    'ui:premium|button:plan|error:insufficient_gems_post_confirm',
                    "Insufficient LionGems to purchase this plan!"
                ))
            )

        # Acknowledge premium
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'ui:premium|button:plan|embed:success|title',
                "Server Upgraded!"
            )),
            description=t(_p(
                'ui:premium|button:plan|embed:success|desc',
                "You have contributed **{plan_text}** of premium subscription to this server!"
            )).format(plan_text=plan.text)
        )
        await press.followup.send(
            embed=embed
        )
        await self.refresh()

    @log_wrap(action='premium upgrade')
    async def _do_premium_upgrade(self, plan: PremiumPlan):
        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            async with conn.transaction():
                # Perform the gem transaction
                transaction = await self.cog.gem_transaction(
                    GemTransactionType.PURCHASE,
                    actorid=self.luser.userid,
                    from_account=self.luser.userid,
                    to_account=None,
                    amount=plan.price,
                    description=(
                        f"User purchased {plan.duration} days of premium"
                        f" for guild {self.guild.id} using the `PremiumUI`."
                    ),
                    note=None,
                    reference=f"iid: {self._original.id if self._original else 'None'}"
                )

                model = self.cog.data.PremiumGuild
                # Ensure the premium guild row exists
                premium_guild = await model.fetch_or_create(self.guild.id)

                # Extend the subscription
                await model.table.update_where(guildid=self.guild.id).set(
                    premium_until=RawExpr(
                        sql.SQL("GREATEST(premium_until, now()) + {}").format(
                            sql.Placeholder()
                        ),
                        (dt.timedelta(days=plan.duration),)
                    )
                )

                # Finally, record the user's contribution
                await self.cog.data.premium_guild_contributions.insert(
                    userid=self.luser.userid, guildid=self.guild.id,
                    transactionid=transaction.transactionid, duration=plan.duration
                )

    def _plan_buttons(self) -> list[Button]:
        """
        Generate the Plan buttons.

        Intended to be used once, upon initialisation.
        """
        t = self.bot.translator.t
        buttons = []
        for plan in plans:
            butt = AButton(
                label=t(plan.label),
                emoji=plan.emoji,
                style=ButtonStyle.blurple,
                pass_kwargs={'plan': plan}
            )
            butt(self.plan_button)
            self.add_item(butt)
            buttons.append(butt)
        return buttons

    # ----- UI Flow -----
    def _current_status(self) -> str:
        t = self.bot.translator.t

        if self.premium_status is None or self.premium_status.premium_until is None:
            status = t(_p(
                'ui:premium|current_status:none',
                "__**Current Server Status:**__ Awaiting Upgrade."
            ))
        elif self.premium_status.premium_until > utc_now():
            status = t(_p(
                'ui:premium|current_status:premium',
                "__**Current Server Status:**__ Upgraded! Premium until {expiry}"
            )).format(expiry=discord.utils.format_dt(self.premium_status.premium_until, 'd'))
        else:
            status = t(_p(
                'ui:premium|current_status:none',
                "__**Current Server Status:**__ Awaiting Upgrade. Premium status expired on {expiry}"
            )).format(expiry=discord.utils.format_dt(self.premium_status.premium_until, 'd'))

        return status

    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t

        blurb = t(_p(
            'ui:premium|embed|description',
            "By supporting our project, you will get access to countless customisation features!\n\n"
            "- **Rebranding:** Customizable HEX colours and"
            " **beautiful premium skins** for all of your community members!\n"
            "- **Remove the vote and sponsor prompt!**\n"
            "- Access to all of the [future premium features](https://staging.lionbot.org/donate)\n\n"
            "Both server owners and **regular users** can"
            " **buy and gift a subscription for this server** using this command!\n"
            "To support both Leo and your server, **use the buttons below**!"
        )) + '\n\n' + self._current_status()

        embed = discord.Embed(
            colour=0x41f097,
            title=t(_p(
                'ui:premium|embed|title',
                "Support Leo and Upgrade your Server!"
            )),
            description=blurb,
        )
        embed.set_thumbnail(
            url="https://i.imgur.com/v1mZolL.png"
        )
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/824196406482305034/972405513570615326/premium_test.png"
        )
        embed.set_footer(
            text=t(_p(
                'ui:premium|embed|footer',
                "Your current balance is {balance} LionGems."
            )).format(balance=self.luser.data.gems)
        )

        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        self.set_layout(
            (*self.plan_buttons, self.link_button),
        )

    async def reload(self):
        self.premium_status = await self.cog.data.PremiumGuild.fetch(self.guild.id, cached=False)
        await self.luser.data.refresh()

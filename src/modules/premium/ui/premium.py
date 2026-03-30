# --- AI-REPLACED (2026-03-22) ---
# Reason: Server premium is now purchased via Stripe recurring subscriptions on the
#         website instead of LionGem deductions in Discord. The PremiumUI no longer
#         needs gem-purchase plan buttons or the _do_premium_upgrade transaction logic.
# What the new code does better: Shows a clean "Subscribe on Website" link button
#         pointing to the server dashboard, keeps status display and gem balance footer.
# --- Original code (commented out for rollback) ---
# from typing import Optional, TYPE_CHECKING, NamedTuple
# import asyncio
# import datetime as dt
# import discord
# from discord.ui.button import button, Button, ButtonStyle
# from psycopg import sql
# from meta import LionBot, conf, WEBSITE_URL
# from meta.logger import log_wrap
# from core.lion_user import LionUser
# from babel.translator import LazyStr
# from meta.errors import ResponseTimedOut, UserInputError
# from data import RawExpr
# from modules.premium.errors import BalanceTooLow
# from utils.ui import MessageUI, Confirm, AButton
# from utils.lib import MessageArgs, utc_now
# from .. import babel, logger
# from ..data import GemTransactionType, PremiumData
# ... (plan buttons, _do_premium_upgrade, gem transaction logic)
# --- End original code ---

from typing import Optional, TYPE_CHECKING

import discord
from discord.ui.button import Button, ButtonStyle

from meta import LionBot, WEBSITE_URL
from core.lion_user import LionUser
from utils.ui import MessageUI
from utils.lib import MessageArgs, utc_now

from .. import babel
from ..data import PremiumData

if TYPE_CHECKING:
    from ..cog import PremiumCog

_p = babel._p


class PremiumUI(MessageUI):
    def __init__(self, bot: LionBot, guild: discord.Guild, luser: LionUser, **kwargs):
        super().__init__(**kwargs)

        self.bot = bot
        self.guild = guild
        self.luser = luser

        self.cog: 'PremiumCog' = bot.get_cog('PremiumCog')  # type: ignore

        self.premium_status: Optional[PremiumData.PremiumGuild] = None

    # ----- UI Flow -----
    def _current_status(self) -> str:
# --- END AI-REPLACED ---
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

    # --- AI-MODIFIED (2026-03-22) ---
    # Purpose: Updated embed to show Stripe subscription pricing instead of gem costs
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t

        blurb = t(_p(
            'ui:premium|embed|description',
            "Upgrade your server with a **premium subscription** "
            "to unlock exclusive features!\n\n"
            "- **Rebranding:** Customizable HEX colours and"
            " **beautiful premium skins** for all of your community members!\n"
            "- **Remove the vote prompt!**\n"
            "- **Ambient Sounds**, **Sticky Messages**, **Leaderboard Auto-Post**\n"
            "- **LionGotchi bonuses:** +15% Gold & +15% Drop rates for all members\n\n"
            "**Pricing:**\n"
            "• **Monthly** — €9.99/month (auto-renews)\n"
            "• **Yearly** — €99.99/year (save 17%)\n\n"
            "Subscribe on the **[LionBot Dashboard]({url}/dashboard)** to get started!"
        )).format(url=WEBSITE_URL) + '\n\n' + self._current_status()

        embed = discord.Embed(
            colour=0x41f097,
            title=t(_p(
                'ui:premium|embed|title',
                "Upgrade your Server with Premium!"
            )),
            description=blurb,
        )
        embed.set_thumbnail(
            url="https://i.imgur.com/v1mZolL.png"
        )
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/824196406482305034/972405513570615326/premium_test.png"
        )
        embed.add_field(
            name=t(_p(
                'ui:premium|embed|field:personal_perks|name',
                "❤️ Personal Perks"
            )),
            value=t(_p(
                'ui:premium|embed|field:personal_perks|value',
                "Get LionHeart for personal bonuses! Use `/donate` to learn more."
            )),
            inline=False
        )
        embed.set_footer(
            text=t(_p(
                'ui:premium|embed|footer',
                "Your current balance is {balance} LionGems."
            )).format(balance=self.luser.data.gems)
        )

        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        self._subscribe_button = discord.ui.Button(
            label="Subscribe on Website", emoji="👑",
            url=f"{WEBSITE_URL}/dashboard/servers/{self.guild.id}/settings",
            style=discord.ButtonStyle.link,
        )
        self._donate_button = discord.ui.Button(
            label="Personal Perks (LionHeart)", emoji="❤️",
            url=f"{WEBSITE_URL}/donate",
            style=discord.ButtonStyle.link,
        )
        self.set_layout(
            (self._subscribe_button, self._donate_button),
        )
    # --- END AI-MODIFIED ---

    async def reload(self):
        self.premium_status = await self.cog.data.PremiumGuild.fetch(self.guild.id, cached=False)
        await self.luser.data.refresh()

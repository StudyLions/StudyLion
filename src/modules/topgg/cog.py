from typing import Optional
import asyncio

import discord
from discord.ext import commands as cmds
import discord.app_commands as appcmds
from discord.ui.button import Button, ButtonStyle
from topgg import WebhookManager
from data.queries import ORDER

from meta import LionCog, LionBot, LionContext
from meta.logger import log_wrap
from wards import sys_admin_ward
from utils.lib import utc_now
from babel.translator import ctx_locale

from . import logger, babel
from .data import TopggData

_p = babel._p

topgg_upvote_link = 'https://top.gg/bot/889078613817831495/vote'


class TopggCog(LionCog):
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data: TopggData = bot.db.load_registry(TopggData())

        self.topgg_webhook: Optional[WebhookManager] = None

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
                self.topgg_webhook = WebhookManager(self.bot).dbl_webhook(
                    route=tgg_config.get('route'),
                    auth_key=tgg_config.get('auth'),
                )
                self.topgg_webhook.run(tgg_config.getint('port'))

                logger.info(
                    "Topgg webhook registered."
                )
        else:
            logger.info(
                "Topgg disabled via config, not initialising module."
            )

    @LionCog.listener('on_dbl_vote')
    @log_wrap(action="Handle DBL Vote")
    async def handle_dbl_vote(self, data):
        logger.info(f"Recieved TopGG vote: {data}")
        userid = data['user']

        await self.data.TopGG.create(
            userid=userid,
            boostedtimestamp=utc_now()
        )
        await self._send_thanks_dm(userid)

    async def voting_bonus(self, userid):
        # Provides 1.25 multiplicative bonus if they have voted within 12h
        if await self.check_voted_recently(userid):
            return 1.25
        else:
            return 1

    async def check_voted_recently(self, userid):
        records = await self.data.TopGG.fetch_where(
            userid=userid
        ).order_by('boostedtimestamp', ORDER.DESC).limit(1)

        return records and (utc_now() - records[0].boostedtimestamp).total_seconds() < 3600 * 12

    def vote_button(self):
        t = self.bot.translator.t

        button = Button(
            style=ButtonStyle.link,
            label=t(_p(
                'button:vote|label',
                "Vote for me!"
            )),
            emoji=self.bot.config.emojis.coin,
            url=topgg_upvote_link,
        )
        return button

    async def _send_thanks_dm(self, userid: int):
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
        luser = await self.bot.core.lions.fetch_user(userid)
        locale = await self.bot.get_cog('BabelCog').get_user_locale(userid)
        ctx_locale.set(locale)

        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'embed:voting_thanks|title',
                "Thank you for supporting me on Top.gg! {yay}"
            )).format(yay=self.bot.config.emojis.lionyay),
            description=t(_p(
                'embed:voting_thanks|desc',
                "Thank you for supporting us, enjoy your LionCoins boost!"
            ))

        ).set_image(
            url="https://cdn.discordapp.com/attachments/908283085999706153/932737228440993822/lion-yay.png"
        )

        try:
            await user.send(embed=embed)
        except discord.HTTPException:
            logger.warning(
                f"Could not send voting thanks to user <uid: {userid}>."
            )

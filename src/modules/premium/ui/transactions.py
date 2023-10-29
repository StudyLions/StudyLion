from typing import Optional
import asyncio
import datetime as dt

import discord
from discord.ui.button import button, Button, ButtonStyle

from meta import LionBot, conf
from data import ORDER

from utils.ui import MessageUI, input
from utils.lib import MessageArgs, tabulate

from .. import babel, logger
from ..data import PremiumData

_p = babel._p


class TransactionList(MessageUI):
    block_len = 5

    def __init__(self, bot: LionBot, userid: int, **kwargs):
        super().__init__(**kwargs)

        self.bot = bot
        self.userid = userid

        self._pagen = 0
        self.blocks: list[list[PremiumData.GemTransaction]] = [[]]

    @property
    def page_count(self):
        return len(self.blocks)

    @property
    def pagen(self):
        self._pagen = self._pagen % self.page_count
        return self._pagen

    @pagen.setter
    def pagen(self, value):
        self._pagen = value % self.page_count

    @property
    def current_page(self):
        return self.blocks[self.pagen]

    # ----- UI Components -----

    # Backwards
    @button(emoji=conf.emojis.backward, style=ButtonStyle.grey)
    async def prev_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        self.pagen -= 1
        await self.refresh(thinking=press)

    # Jump to page
    @button(label="JUMP_PLACEHOLDER", style=ButtonStyle.blurple)
    async def jump_button(self, press: discord.Interaction, pressed: Button):
        """
        Jump-to-page button.
        Loads a page-switch dialogue.
        """
        t = self.bot.translator.t
        try:
            interaction, value = await input(
                press,
                title=t(_p(
                    'ui:transactions|button:jump|input:title',
                    "Jump to page"
                )),
                question=t(_p(
                    'ui:transactions|button:jump|input:question',
                    "Page number to jump to"
                ))
            )
            value = value.strip()
        except asyncio.TimeoutError:
            return

        if not value.lstrip('- ').isdigit():
            error_embed = discord.Embed(
                title=t(_p(
                    'ui:transactions|button:jump|error:invalid_page',
                    "Invalid page number, please try again!"
                )),
                colour=discord.Colour.brand_red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
        else:
            await interaction.response.defer(thinking=True)
            pagen = int(value.lstrip('- '))
            if value.startswith('-'):
                pagen = -1 * pagen
            elif pagen > 0:
                pagen = pagen - 1
            self.pagen = pagen
            await self.refresh(thinking=interaction)

    async def jump_button_refresh(self):
        component = self.jump_button
        component.label = f"{self.pagen + 1}/{self.page_count}"
        component.disabled = (self.page_count <= 1)

    # Forward
    @button(emoji=conf.emojis.forward, style=ButtonStyle.grey)
    async def next_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True)
        self.pagen += 1
        await self.refresh(thinking=press)

    # Quit
    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        """
        Quit the UI.
        """
        await press.response.defer()
        await self.quit()

    # ----- UI Flow -----
    async def make_message(self) -> MessageArgs:
        t = self.bot.translator.t

        title = t(_p(
            'ui:transactions|embed|title',
            "Gem Transactions for user `{userid}`"
        )).format(userid=self.userid)

        rows = self.current_page
        if rows:
            embed = discord.Embed(
                colour=discord.Colour.orange(),
                title=title,
                description=t(_p(
                    'ui:transactions|embed|desc:balance',
                    "User {target} has a LionGem balance of {gem}**{balance}**"
                )).format(
                    gem=self.bot.config.emojis.gem,
                    target=f"<@{self.userid}>",
                    balance=await (self.bot.get_cog('PremiumCog')).get_gem_balance(self.userid),
                )
            )
            for row in rows:
                name = f"Transaction #{row.transactionid}"
                table_rows = (
                    ('timestamp', discord.utils.format_dt(row._timestamp)),
                    ('type', row.transaction_type.name),
                    ('amount', str(row.amount)),
                    ('actor', f"<@{row.actorid}>"),
                    ('from', f"`{row.from_account}`" if row.from_account else 'None'),
                    ('to', f"`{row.to_account}`" if row.to_account else 'None'),
                    ('reference', str(row.reference)),
                )
                table = '\n'.join(tabulate(*table_rows))
                embed.add_field(
                    name=name,
                    value=f"{row.description}\n{table}",
                    inline=False
                )
        else:
            embed = discord.Embed(
                colour=discord.Colour.brand_red(),
                description = t(_p(
                    'ui:transactions|embed|desc:no_transactions',
                    "This user has no related gem transactions!"
                ))
            )
        return MessageArgs(embed=embed)

    async def refresh_layout(self):
        to_refresh = (
            self.jump_button_refresh(),
        )
        await asyncio.gather(*to_refresh)

        if self.page_count > 1:
            self.set_layout(
                (self.prev_button, self.jump_button, self.quit_button, self.next_button),
            )
        else:
            self.set_layout(
                (self.quit_button,)
            )

    async def reload(self):
        model = PremiumData.GemTransaction

        rows = await model.fetch_where(
            (model.from_account == self.userid) | (model.to_account == self.userid)
        ).order_by('_timestamp', ORDER.DESC)

        blocks = [
            rows[i:i+self.block_len]
            for i in range(0, len(rows), self.block_len)
        ]
        self.blocks = blocks or [[]]

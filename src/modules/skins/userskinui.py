from typing import Optional
import asyncio
import datetime as dt

import discord
from discord.ui.button import button, Button, ButtonStyle
from discord.ui.select import select, Select, SelectOption
from gui.base.AppSkin import AppSkin
from gui.base.Card import Card

from meta import LionBot, conf
from meta.errors import ResponseTimedOut, UserInputError
from meta.logger import log_wrap
from modules.premium.data import GemTransactionType
from modules.premium.errors import BalanceTooLow
from modules.skins.skinlib import CustomSkin, appskin_as_option
from utils.ui import MessageUI, input, Confirm
from utils.lib import MessageArgs, utc_now
from gui import cards

from . import babel, logger
from .data import CustomSkinData as Data

_p = babel._p


class UserSkinUI(MessageUI):
    card_classes = [
        cards.ProfileCard,
        cards.StatsCard,
        cards.WeeklyGoalCard,
        cards.WeeklyStatsCard,
        cards.MonthlyGoalCard,
        cards.MonthlyStatsCard,
    ]

    def __init__(self, bot: LionBot, userid: int, callerid: int, **kwargs):
        super().__init__(callerid=callerid, **kwargs)

        self.bot = bot
        self.cog = bot.get_cog('CustomSkinCog')
        self.gems = bot.get_cog('PremiumCog')

        self.userid = userid

        # UI State
        # Map of app_skin_id -> itemid
        self.inventory: dict[str, int] = {}

        # Active app skin, if any
        self.active: Optional[str] = None

        # Skins available for purchase
        self.available = self._get_available()

        # Index of card currently showing
        self._card: int = 0

        # Name of skin currently displayed, 'default' for default
        self._skin: Optional[str] = None

        self.balance: int = 0

    @property
    def current_card(self) -> Card:
        return self.card_classes[self._card]

    @property
    def current_skin(self) -> AppSkin:
        if self._skin is None:
            raise ValueError("Cannot get current skin before load.")
        return self.available[self._skin]

    @property
    def is_default(self) -> bool:
        return (self._skin == 'default')

    @property
    def is_owned(self) -> bool:
        return self.is_default or (self._skin in self.inventory)

    @property
    def is_equipped(self) -> bool:
        return (self.active == self._skin) or (self.is_default and not self.active)

    def _get_available(self) -> dict[str, AppSkin]:
        skins = {
            skin.skin_id: skin for skin in AppSkin.get_all()
            if skin.public or (
                skin.user_whitelist is not None and 
                self.userid in skin.user_whitelist
            )
        }
        skins['default'] = self._make_default()
        return skins

    def _make_default(self) -> AppSkin:
        """
        Create a placeholder 'default' skin.
        """
        t = self.bot.translator.t

        skin = AppSkin(None)
        skin.skin_id = 'default'
        skin.display_name = t(_p(
            'ui:userskins|default_skin:display_name',
            "Default"
        ))
        skin.description = t(_p(
            'ui:userskins|default_skin:description',
            "My default interface theme"
        ))
        skin.price = 0
        return skin

    # ----- UI API -----

    @log_wrap(action='equip skin')
    async def _equip_owned_skin(self, itemid: Optional[int]):
        """
        Equip the provided item.

        if `itemid` is None, 'equips' the default skin.
        """
        # Global dispatch
        await self.cog.data.UserSkin.table.update_where(
            userid=self.userid
        ).set(active=False)
        if itemid is not None:
            await self.cog.data.UserSkin.table.update_where(
                userid=self.userid, itemid=itemid
            ).set(active=True)

        await self.bot.global_dispatch('userset_skin', self.userid)

    @log_wrap(action='purchase skin')
    async def _purchase_skin(self, app_skin_name: str):
        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            async with conn.transaction():
                skin = self.current_skin
                skinid = self.cog.appskin_names.inverse[skin.skin_id]

                # Perform transaction
                transaction = await self.gems.gem_transaction(
                    GemTransactionType.PURCHASE,
                    actorid=self.userid,
                    from_account=self.userid,
                    to_account=None,
                    amount=skin.price,
                    description=(
                        f"User purchased custom app skin {skin.skin_id} via UserSkinUI."
                    ),
                    note=None,
                    reference=f"iid: {self._original.id if self._original else 'None'}"
                )

                # Create custom skin
                custom_skin = await self.cog.data.CustomisedSkin.create(
                    base_skin_id=skinid,
                )

                # Update inventory actives
                await self.cog.data.UserSkin.table.update_where(
                    userid=self.userid
                ).set(active=False)

                # Insert into inventory
                await self.cog.data.UserSkin.create(
                    userid=self.userid,
                    custom_skin_id=custom_skin.custom_skin_id,
                    transactionid=transaction.transactionid,
                    active=True
                )

        # Global dispatch update
        await self.bot.global_dispatch('userset_skin', self.userid)

        logger.info(
            f"<uid: {self.userid}> purchased skin {skin.skin_id}."
        )

    # ----- UI Components -----
    
    # Gift Button
    @button(
        label="GIFT_BUTTON_PLACEHOLDER",
        style=ButtonStyle.green,
    )
    async def gift_button(self, press: discord.Interaction, pressed: Button):
        # TODO: Replace with an actual gifting interface

        t = self.bot.translator.t
        skin = self.current_skin
        gift_hint = t(_p(
            'ui:userskins|button:gift|response',
            "To gift **{skin}** to a friend,"
            " send them {gem}**{price}** with {gift_cmd}."
        )).format(
            skin=skin.display_name,
            gem=self.bot.config.emojis.gem,
            price=skin.price,
            gift_cmd=self.bot.core.mention_cmd('gift'),
        )
        await press.response.send_message(gift_hint, ephemeral=True)

    async def gift_button_refresh(self):
        button = self.gift_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:userskins|button:gift|label',
            "Gift to a friend"
        ))
        price = self.current_skin.price
        button.disabled = (
            not price or (price > self.balance)
        )

    # Purchase Button
    @button(
        label="PURCHASE_BUTTON_PLACEHOLDER",
        style=ButtonStyle.green
    )
    async def purchase_button(self, press: discord.Interaction, pressed: Button):
        t = self.bot.translator.t

        skin = self.current_skin

        # Verify we can purchase this skin
        await self.reload()

        if self.is_owned:
            raise UserInputError(
                t(_p(
                    'ui:userskins|button:purchase|error:already_owned',
                    "You already own this skin!"
                ))
            )
        elif skin.price > self.balance:
            raise UserInputError(
                t(_p(
                    'ui:userskins|button:purchase|error:insufficient_gems',
                    "You don't have enough LionGems to purchase this skin!"
                ))
            )

        # Confirm purchase
        confirm_msg = t(_p(
            'ui:userskins|button:purchase|confirm|desc',
            "Are you sure you want to purchase this skin?\n"
            "The price of the skin is {gem}**{price}**."
        )).format(price=skin.price, gem=self.bot.config.emojis.gem)
        confirm = Confirm(confirm_msg, press.user.id)

        confirm.embed.set_footer(
            text=t(_p(
                'ui:userskins|button:purchase|confirm|footer',
                "Your current balance is {balance} LionGems"
            )).format(balance=self.balance)
        )

        try:
            result = await confirm.ask(press, ephemeral=True)
        except ResponseTimedOut:
            result = False

        if result:
            try:
                await self._purchase_skin(skin.skin_id)
            except BalanceTooLow:
                raise UserInputError(
                    t(_p(
                        'ui:userskins|button:purchase|error:insufficient_gems_post_confirm',
                        "Insufficient LionGems to purchase this skin!"
                    ))
                )

            # Ack purchase and refresh
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                title=t(_p(
                    'ui:userskins|button:purchase|embed:success|title',
                    "Skin Purchase"
                )),
                description=t(_p(
                    'ui:userskins|button:purchase|embed:success|desc',
                    "You have purchased and equipped the skin **{name}**!\n"
                    "Thank you for your support, and enjoy your new purchase!"
                )).format(name=skin.display_name)
            )
            await press.followup.send(embed=embed, ephemeral=True)
            await self.refresh()
    
    async def purchase_button_refresh(self):
        button = self.purchase_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:userskins|button:purchase|label',
            "Purchase Skin"
        ))
        button.disabled = (
            self.is_owned
            or self.current_skin.price > self.balance
        )

    # Equip Button
    @button(
        label="EQUIP_BUTTON_PLACEHOLDER",
        style=ButtonStyle.green
    )
    async def equip_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=True, ephemeral=True)
        t = self.bot.translator.t

        to_equip = None if self.is_default else self.inventory[self._skin]
        await self._equip_owned_skin(to_equip)

        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            title=t(_p(
                'ui:userskins|button:equip|embed:success|title',
                "Skin Equipped"
            )),
            description=t(_p(
                'ui:userskins|button:equip|embed:success|desc',
                "You have equpped your **{name}** skin!"
            )).format(name=self.current_skin.display_name)
        )
        await press.edit_original_response(embed=embed)
        await self.refresh()
    
    async def equip_button_refresh(self):
        button = self.equip_button
        t = self.bot.translator.t
        button.label = t(_p(
            'ui:userskins|button:equip|label',
            "Equip Skin"
        ))
        button.disabled = (
            self.is_equipped or not self.is_owned
        )

    # Price button
    @button(
        label="PRICE_BUTTON_PLACEHOLDER",
        style=ButtonStyle.green,
        emoji=conf.emojis.gem,
    )
    async def price_button(self, press: discord.Interaction, pressed: Button):
        await press.response.defer(thinking=False)
    
    async def price_button_refresh(self):
        button = self.price_button
        t = self.bot.translator.t

        price = self.current_skin.price
        button.label = t(_p(
            'ui:userskins|button:price|label',
            "{price} Gems"
        )).format(price=price)
        if price < self.balance:
            button.style = ButtonStyle.green
        else:
            button.style = ButtonStyle.danger

    # Card Menu
    @select(
        cls=Select,
        placeholder="CARD_MENU_PLACEHOLDER",
        min_values=1, max_values=1
    )
    async def card_menu(self, selection: discord.Interaction, selected: Select):
        await selection.response.defer(thinking=True, ephemeral=True)
        self._card = int(selected.values[0])
        await self.refresh(thinking=selection)
    
    async def card_menu_refresh(self):
        menu = self.card_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:userskins|menu:card|placeholder',
            "Select a card to preview"
        ))
        options = []
        for i, card in enumerate(self.card_classes):
            option = SelectOption(
                label=t(card.display_name),
                value=str(i),
                default=(i == self._card)
            )
            options.append(option)
        menu.options = options

    @button(emoji=conf.emojis.cancel, style=ButtonStyle.red)
    async def quit_button(self, press: discord.Interaction, pressed: Button):
        """
        Quit the UI.
        """
        await press.response.defer()
        await self.quit()

    # Skin Menu
    @select(
        cls=Select,
        placeholder="SKIN_MENU_PLACEHOLDER",
        min_values=1, max_values=1
    )
    async def skin_menu(self, selection: discord.Interaction, selected: Select):
        await selection.response.defer(thinking=True, ephemeral=True)
        self._skin = selected.values[0]
        await self.refresh(thinking=selection)
    
    async def skin_menu_refresh(self):
        menu = self.skin_menu
        t = self.bot.translator.t
        menu.placeholder = t(_p(
            'ui:userskins|menu:skin|placeholder',
            "Select a skin."
        ))
        options = []
        for skin in self.available.values():
            option = appskin_as_option(skin)
            if skin.skin_id == self._skin:
                option.default = True
            options.append(option)
        menu.options = options

    # ----- UI Flow -----
    async def _render_card(self) -> discord.File:
        if not self._skin:
            raise ValueError("Rendering UserSkinUI before load.")

        use_skin = None
        if self._skin == 'default':
            use_skin = await self.cog.get_default_skin()
        else:
            use_skin = self._skin
        skin = {'base_skin_id': use_skin} if use_skin else {}

        return await self.current_card.generate_sample(skin=skin)

    async def make_message(self) -> MessageArgs:
        if not self._skin:
            raise ValueError("Rendering UserSkinUI before load.")

        t = self.bot.translator.t

        skin = self.current_skin

        # Compute tagline
        if not self.is_owned:
            if skin.price <= self.balance:
                tagline = t(_p(
                    'ui:userskins|tagline:purchase',
                    "Purchase this skin for {gem}{price}"
                ))
            else:
                tagline = t(_p(
                    'ui:userskins|tagline:insufficient',
                    "You don't have enough LionGems to buy this skin!"
                ))
        elif not self.is_equipped:
            tagline = t(_p(
                'ui:userskins|tagline:equip',
                "You already own this skin! Clock Equip to use it!"
            ))
        else:
            tagline = t(_p(
                'ui:userskins|tagline:current',
                "This is your current skin!"
            ))

        tagline = tagline.format(
            gem=self.bot.config.emojis.gem,
            price=skin.price,
        )

        embed = discord.Embed(
            colour=discord.Colour.orange(),
            title=skin.display_name,
            description=f"{skin.description}\n\n***{tagline}***"
        )
        embed.set_footer(
            icon_url="https://cdn.discordapp.com/attachments/925799205954543636/938703943683416074/4CF1C849-D532-4DEC-B4C9-0AB11F443BAB.png",
            text=t(_p(
                'ui:userskins|footer',
                "Current Balance: {balance} LionGems"
            )).format(balance=self.balance)
        )
        embed.set_image(url='attachment://sample.png')

        file = await self._render_card()

        return MessageArgs(embed=embed, files=[file])

    async def refresh_layout(self):
        """
        (gift_button, price_button, action_button)
        (skin_menu,),
        (card_menu,),
        """
        to_refresh = (
            self.gift_button_refresh(),
            self.price_button_refresh(),
            self.purchase_button_refresh(),
            self.equip_button_refresh(),
            self.card_menu_refresh(),
            self.skin_menu_refresh(),
        )
        await asyncio.gather(*to_refresh)

        # Determine action button
        skin = self.current_skin
        if not self.is_owned:
            if skin.price <= self.balance:
                action = self.purchase_button
            else:
                action = self.gems.buy_gems_button()
        else:
            action = self.equip_button

        self.set_layout(
            (self.gift_button, self.price_button, action, self.quit_button,),
            (self.skin_menu,),
            (self.card_menu,),
        )

    async def reload(self):
        """
        Load the user's skin inventory.
        """
        records = await self.cog.data.UserSkin.table.select_where(
            userid=self.userid
        ).join(
            'customised_skins', using=('custom_skin_id',)
        ).select(
            'itemid', 'custom_skin_id', 'base_skin_id', 'active'
        ).with_no_adapter()
        active = None
        inventory = {}
        for record in records:
            base_skin_name = self.cog.appskin_names[record['base_skin_id']]
            inventory[base_skin_name] = record['itemid']
            if record['active']:
                active = base_skin_name

        self.inventory = inventory
        self.active = active
        if self._skin is None:
            self._skin = active or 'default'

        self.balance = await self.gems.get_gem_balance(self.userid)

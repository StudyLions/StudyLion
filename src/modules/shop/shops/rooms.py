# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-23
# Purpose: Room rental shop module - allows admins to create
#          room rental packages that users can buy via /shop open
# ============================================================
from typing import TYPE_CHECKING, Optional
import logging

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.ui.select import select, Select, SelectOption
from discord.ui.button import button, Button

from meta import conf, WEBSITE_URL
from meta import LionCog, LionContext, LionBot
from meta.errors import SafeCancellation
from meta.logger import log_wrap
from utils.lib import error_embed, MessageArgs
from constants import MAX_COINS

from .. import babel

from ..data import ShopData, ShopItemType
from .base import ShopCog, Shop, Customer, Store, ShopItem

if TYPE_CHECKING:
    from ..cog import Shopping
    from modules.economy.cog import Economy
    from modules.rooms.cog import RoomCog
    from modules.rooms.settings import RoomSettings

_p = babel._p

logger = logging.getLogger(__name__)


class RoomRentalItem(ShopItem):
    """
    ShopItem representing a room rental package with a fixed duration.
    """
    @property
    def duration(self) -> int:
        return self.data.duration

    @property
    def price(self) -> int:
        return self.data.price

    @property
    def itemid(self) -> int:
        return self.data.itemid

    @property
    def name(self) -> str:
        if self.duration == 1:
            return "1-Day Room"
        return f"{self.duration}-Day Room"

    def select_option_for(self, customer: Customer) -> SelectOption:
        t = customer.bot.translator.t
        label = t(_p(
            'ui:roomstore|menu:buyroom|label',
            "{name} ({price} LC)"
        )).format(name=self.name, price=self.price)
        description = t(_p(
            'ui:roomstore|menu:buyroom|desc',
            "Private voice room for {duration} days"
        )).format(duration=self.duration)
        return SelectOption(
            label=label,
            value=str(self.itemid),
            description=description,
        )


class RoomRentalShop(Shop):
    """
    A Shop class representing a Room Rental shop for a given customer.
    """
    _name_ = _p("shop:rooms|name", "Room Rental")
    _item_type_ = ShopItemType.ROOM_RENTAL

    def _get_room_cog(self) -> Optional['RoomCog']:
        return self.bot.get_cog('RoomCog')

    def _has_room_category(self) -> bool:
        from modules.rooms.settings import RoomSettings
        guild = self.bot.get_guild(self.customer.guildid)
        if guild is None:
            return False
        # --- AI-MODIFIED (2026-03-25) ---
        # Purpose: Fix AttributeError -- Lions uses lion_guilds, not _guild_cache
        # --- Original code (commented out for rollback) ---
        # lguild = self.bot.core.lions._guild_cache.get(guild.id)
        # --- End original code ---
        lguild = self.bot.core.lions.lion_guilds.get(guild.id)
        # --- END AI-MODIFIED ---
        if lguild is None:
            return False
        cat = lguild.config.get(RoomSettings.Category.setting_id)
        return cat is not None and cat.value is not None

    def _already_owns_room(self) -> bool:
        room_cog = self._get_room_cog()
        if room_cog is None:
            return False
        rooms = room_cog.get_rooms(self.customer.guildid, self.customer.userid)
        return bool(rooms)

    def purchasable(self):
        """
        Returns room rental items the customer can afford.
        Also checks: no existing room, room category configured.
        """
        if self._already_owns_room():
            return []
        if not self._has_room_category():
            return []
        balance = self.customer.balance
        return [item for item in self.items if item.price <= balance]

    @log_wrap(action='purchase')
    async def purchase(self, itemid) -> RoomRentalItem:
        t = self.bot.translator.t
        from modules.rooms.settings import RoomSettings

        async with self.bot.db.connection() as conn:
            self.bot.db.conn = conn
            async with conn.transaction():
                item = await self.data.ShopItemInfo.table.select_one_where(itemid=itemid)
                if not item['purchasable'] or item['deleted']:
                    raise SafeCancellation(
                        t(_p(
                            'shop:room|purchase|error:not_purchasable',
                            "This room rental package is not available!"
                        ))
                    )

                await self.customer.refresh()

                guild = self.bot.get_guild(self.customer.guildid)
                if guild is None:
                    raise SafeCancellation(
                        t(_p(
                            'shop:room|purchase|error:no_guild',
                            "Could not retrieve the server from Discord!"
                        ))
                    )

                member = await self.customer.lion.fetch_member()
                if member is None:
                    raise SafeCancellation(
                        t(_p(
                            'shop:room|purchase|error:no_member',
                            "Could not retrieve the member from Discord."
                        ))
                    )

                if self.customer.balance < item['price']:
                    raise SafeCancellation(
                        t(_p(
                            'shop:room|purchase|error:low_balance',
                            "This package costs {coin}{amount}!\nYour balance is {coin}{balance}"
                        )).format(
                            coin=self.bot.config.emojis.getemoji('coin'),
                            amount=item['price'],
                            balance=self.customer.balance
                        )
                    )

                if self._already_owns_room():
                    raise SafeCancellation(
                        t(_p(
                            'shop:room|purchase|error:already_owns',
                            "You already own a private room in this server!"
                        ))
                    )

                lguild = await self.bot.core.lions.fetch_guild(guild.id)
                room_cat = lguild.config.get(RoomSettings.Category.setting_id)
                if room_cat is None or room_cat.value is None:
                    raise SafeCancellation(
                        t(_p(
                            'shop:room|purchase|error:no_category',
                            "Private rooms are not configured in this server."
                        ))
                    )

                room_cog: 'RoomCog' = self._get_room_cog()
                if room_cog is None:
                    raise SafeCancellation(
                        t(_p(
                            'shop:room|purchase|error:no_cog',
                            "The room system is not available right now."
                        ))
                    )

                economy_cog: Economy = self.bot.get_cog('Economy')
                economy_data = economy_cog.data
                transaction = await economy_data.ShopTransaction.purchase_transaction(
                    guild.id,
                    member.id,
                    member.id,
                    itemid,
                    item['price']
                )

                duration = item['duration']
                daily_rent = lguild.config.get(RoomSettings.Price.setting_id).value or 1000
                initial_balance = (duration - 1) * daily_rent

                try:
                    room = await room_cog.create_private_room(
                        guild,
                        member,
                        initial_balance,
                        member.display_name,
                        members=[]
                    )
                except discord.Forbidden:
                    raise SafeCancellation(
                        t(_p(
                            'shop:room|purchase|error:permissions',
                            "I don't have permission to create a private room channel!"
                        ))
                    )
                except discord.HTTPException:
                    raise SafeCancellation(
                        t(_p(
                            'shop:room|purchase|error:create_failed',
                            "Failed to create the private room channel."
                        ))
                    )

                lguild.log_event(
                    title=t(_p(
                        'eventlog|event:purchase_room|title',
                        "Member Purchased Room Rental"
                    )),
                    description=t(_p(
                        'eventlog|event:purchase_room|desc',
                        "{member} purchased a {duration}-day room rental from the shop."
                    )).format(member=member.mention, duration=duration),
                    price=item['price'],
                )

                await self.refresh()
                return RoomRentalItem(self.bot, self.data.ShopItemInfo(item))

    async def refresh(self):
        data = await self.data.ShopItemInfo.table.select_where(
            item_type=self._item_type_,
            deleted=False,
            guildid=self.customer.guildid
        ).order_by('itemid')
        self.items = [RoomRentalItem(self.bot, self.data.ShopItemInfo(row)) for row in data]
        await self.customer.refresh()

    def make_store(self, interaction: discord.Interaction):
        return RoomRentalStore(self, interaction)


@ShopCog.register
class RoomShopping(ShopCog):
    """
    Cog in charge of room rental shopping.
    """
    _shop_cls_ = RoomRentalShop

    async def load_into(self, cog: 'Shopping'):
        self.crossload_group(self.editshop_group, cog.editshop_group)
        await cog.bot.add_cog(self)

    @LionCog.placeholder_group
    @cmds.hybrid_group('editshop', with_app_command=False)
    async def editshop_group(self, ctx: LionContext):
        pass

    @editshop_group.group(_p('grp:editshop_rooms', 'rooms'))
    async def editshop_rooms_group(self, ctx: LionContext):
        pass

    @editshop_rooms_group.command(
        name=_p('cmd:editshop_rooms_add', 'add'),
        description=_p(
            'cmd:editshop_rooms_add|desc',
            "Add a room rental package to the shop."
        )
    )
    @appcmds.rename(
        duration=_p('cmd:editshop_rooms_add|param:duration', "duration"),
        price=_p('cmd:editshop_rooms_add|param:price', "price")
    )
    @appcmds.describe(
        duration=_p(
            'cmd:editshop_rooms_add|param:duration|desc',
            "How many days should the room rental last? (1-30)"
        ),
        price=_p(
            'cmd:editshop_rooms_add|param:price|desc',
            "How much should this room rental package cost?"
        )
    )
    async def editshop_rooms_add_cmd(self, ctx: LionContext,
                                     duration: appcmds.Range[int, 1, 30],
                                     price: appcmds.Range[int, 0, MAX_COINS]):
        t = self.bot.translator.t
        if not ctx.interaction:
            return
        if not ctx.guild:
            return

        item = await self.data.ShopItem.create(
            guildid=ctx.guild.id,
            item_type=self._shop_cls_._item_type_,
            price=price,
            purchasable=True
        )
        await self.data.RoomRental.create(
            itemid=item.itemid,
            duration=duration
        )

        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
        )
        embed.title = t(_p(
            'cmd:editshop_rooms_add|resp:done|title',
            "Room Rental Package Added"
        ))
        if duration == 1:
            dur_text = "1 day"
        else:
            dur_text = f"{duration} days"
        embed.description = t(_p(
            'cmd:editshop_rooms_add|resp:done|desc',
            "Added a **{duration}** room rental to the shop for {coin}**{price}**!"
        )).format(
            duration=dur_text,
            coin=self.bot.config.emojis.getemoji('coin'),
            price=price
        )

        await ctx.reply(embed=embed)

    @editshop_rooms_group.command(
        name=_p('cmd:editshop_rooms_edit', 'edit'),
        description=_p(
            'cmd:editshop_rooms_edit|desc',
            "Edit the price or duration of a room rental package."
        )
    )
    @appcmds.rename(
        item_number=_p('cmd:editshop_rooms_edit|param:item', "item_number"),
        duration=_p('cmd:editshop_rooms_edit|param:duration', "duration"),
        price=_p('cmd:editshop_rooms_edit|param:price', "price"),
    )
    @appcmds.describe(
        item_number=_p(
            'cmd:editshop_rooms_edit|param:item|desc',
            "The shop item number to edit (shown in /shop open)."
        ),
        duration=_p(
            'cmd:editshop_rooms_edit|param:duration|desc',
            "New duration in days (1-30)."
        ),
        price=_p(
            'cmd:editshop_rooms_edit|param:price|desc',
            "New price for the package."
        ),
    )
    async def editshop_rooms_edit_cmd(self, ctx: LionContext,
                                      item_number: appcmds.Range[int, 1, 100],
                                      duration: Optional[appcmds.Range[int, 1, 30]] = None,
                                      price: Optional[appcmds.Range[int, 0, MAX_COINS]] = None):
        t = self.bot.translator.t
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        items = await self.data.ShopItemInfo.fetch_where(
            guildid=ctx.guild.id,
            deleted=False,
            item_type=self._shop_cls_._item_type_
        )
        items = sorted(items, key=lambda i: i.itemid)

        if item_number < 1 or item_number > len(items):
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_rooms_edit|error:not_found',
                    "Room rental package #{num} not found! Use `/shop open` to see item numbers."
                )).format(num=item_number)
            )

        item = items[item_number - 1]

        if duration is None and price is None:
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_rooms_edit|error:no_args',
                    "You must provide at least one of `duration` or `price` to update!"
                ))
            )

        lines = []
        tick = self.bot.config.emojis.getemoji('tick')

        if price is not None:
            await self.data.ShopItem.table.update_where(
                itemid=item.itemid
            ).set(price=price)
            lines.append(
                t(_p(
                    'cmd:editshop_rooms_edit|resp:done|line:price',
                    "{tick} Set price to {coin}**{price}**"
                )).format(
                    tick=tick,
                    coin=self.bot.config.emojis.getemoji('coin'),
                    price=price
                )
            )

        if duration is not None:
            await self.data.RoomRental.table.update_where(
                itemid=item.itemid
            ).set(duration=duration)
            lines.append(
                t(_p(
                    'cmd:editshop_rooms_edit|resp:done|line:duration',
                    "{tick} Set duration to **{duration}** days"
                )).format(tick=tick, duration=duration)
            )

        description = '\n'.join(lines)
        await ctx.reply(
            embed=discord.Embed(
                title=t(_p('cmd:editshop_rooms_edit|resp:done|title', "Room Rental Updated")),
                description=description,
                colour=discord.Colour.brand_green()
            )
        )

    @editshop_rooms_group.command(
        name=_p('cmd:editshop_rooms_remove', 'remove'),
        description=_p(
            'cmd:editshop_rooms_remove|desc',
            "Remove a room rental package from the shop."
        )
    )
    @appcmds.rename(
        item_number=_p('cmd:editshop_rooms_remove|param:item', "item_number"),
    )
    @appcmds.describe(
        item_number=_p(
            'cmd:editshop_rooms_remove|param:item|desc',
            "The room rental item number to remove (shown in /shop open)."
        ),
    )
    async def editshop_rooms_remove_cmd(self, ctx: LionContext,
                                        item_number: appcmds.Range[int, 1, 100]):
        t = self.bot.translator.t
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        items = await self.data.ShopItemInfo.fetch_where(
            guildid=ctx.guild.id,
            deleted=False,
            item_type=self._shop_cls_._item_type_
        )
        items = sorted(items, key=lambda i: i.itemid)

        if item_number < 1 or item_number > len(items):
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_rooms_remove|error:not_found',
                    "Room rental package #{num} not found!"
                )).format(num=item_number)
            )

        item = items[item_number - 1]
        await self.data.ShopItem.table.update_where(itemid=item.itemid).set(deleted=True)

        await ctx.reply(
            embed=discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:editshop_rooms_remove|resp:done|desc',
                    "Removed the **{duration}-day** room rental package from the shop."
                )).format(duration=item.duration)
            )
        )


class RoomRentalStore(Store):
    """
    Ephemeral UI providing access to the room rental store.
    """
    shop: RoomRentalShop

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ----- UI Components -----
    @select(placeholder="SELECT_PLACEHOLDER")
    async def select_room(self, interaction: discord.Interaction, selection: Select):
        t = self.shop.bot.translator.t

        itemid = int(selection.values[0])
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            item = await self.shop.purchase(itemid)
        except SafeCancellation as exc:
            embed = discord.Embed(
                title=t(_p('ui:roomstore|menu:buyroom|embed:error|title', "Purchase Failed!")),
                colour=discord.Colour.brand_red(),
                description=exc.msg
            )
            await interaction.edit_original_response(embed=embed)
        else:
            embed = discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'ui:roomstore|menu:buyroom|resp:done|desc',
                    "{tick} You purchased a **{duration}-day** private room! Check the room category for your new channel."
                )).format(
                    tick=self.shop.bot.config.emojis.getemoji('tick'),
                    duration=item.duration,
                )
            )
            await interaction.edit_original_response(embed=embed)
            await self.refresh()
            await self.redraw()

    async def select_room_refresh(self):
        t = self.shop.bot.translator.t
        selector = self.select_room

        purchasable = self.shop.purchasable()
        option_map: dict[int, SelectOption] = {}

        for item in purchasable:
            option_map[item.itemid] = item.select_option_for(self.shop.customer)

        if not option_map:
            if self.shop._already_owns_room():
                selector.placeholder = t(_p(
                    'ui:roomstore|menu:buyroom|placeholder:owns_room',
                    "You already own a room in this server!"
                ))
            elif not self.shop._has_room_category():
                selector.placeholder = t(_p(
                    'ui:roomstore|menu:buyroom|placeholder:no_category',
                    "Private rooms are not enabled in this server."
                ))
            else:
                selector.placeholder = t(_p(
                    'ui:roomstore|menu:buyroom|placeholder:empty',
                    "No room rental packages available!"
                ))
            selector.disabled = True
        else:
            selector.placeholder = t(_p(
                'ui:roomstore|menu:buyroom|placeholder',
                "Select a room rental package to purchase!"
            ))
            selector.disabled = False
            selector.options = list(option_map.values())

    # ----- UI Flow -----
    async def reload(self):
        pass

    async def refresh_layout(self):
        await self.select_room_refresh()
        _web = discord.ui.Button(
            label="Shop on Web", emoji="🌐",
            url=f"{WEBSITE_URL}/dashboard/servers/{self.shop.customer.guildid}/shop",
            style=discord.ButtonStyle.link,
        )
        buttons = (*self.store_row, _web)
        if not self.select_room.options:
            self._layout = [buttons]
        else:
            self._layout = [(self.select_room,), buttons]

    async def make_message(self) -> MessageArgs:
        t = self.shop.bot.translator.t
        if self.shop.items:
            lines = []
            for i, item in enumerate(self.shop.items):
                line = t(_p(
                    'ui:roomstore|embed|line:item',
                    "`[{j:02}]` | `{price} LC` | {name}"
                )).format(j=i+1, price=item.price, name=item.name)
                lines.append(line)
            description = '\n'.join(lines)
        else:
            description = t(_p(
                'ui:roomstore|embed|desc',
                "No room rental packages available!"
            ))

        embed = discord.Embed(
            title=t(_p('ui:roomstore|embed|title', "Room Rental Shop")),
            description=description,
            colour=discord.Colour.dark_teal()
        )

        if self.shop._already_owns_room():
            embed.add_field(
                name=t(_p('ui:roomstore|embed|field:owns_room|name', "Note")),
                value=t(_p(
                    'ui:roomstore|embed|field:owns_room|value',
                    "You already own a private room in this server. "
                    "Use `/room deposit` to extend it, or wait for it to expire before renting a new one."
                ))
            )
        elif not self.shop._has_room_category():
            embed.add_field(
                name=t(_p('ui:roomstore|embed|field:no_rooms|name', "Not Available")),
                value=t(_p(
                    'ui:roomstore|embed|field:no_rooms|value',
                    "Private rooms have not been configured in this server."
                ))
            )

        balance = self.shop.customer.balance
        embed.set_footer(text=t(_p(
            'ui:roomstore|embed|footer',
            "Your balance: {balance} LC"
        )).format(balance=balance))

        return MessageArgs(embed=embed)

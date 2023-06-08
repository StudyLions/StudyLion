from typing import TYPE_CHECKING, Optional
import logging
import asyncio

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds
from discord.ui.select import select, Select, SelectOption
from discord.ui.button import button, Button

from meta import LionCog, LionContext, LionBot
from meta.errors import SafeCancellation
from utils import ui
from utils.lib import error_embed
from constants import MAX_COINS

from .. import babel

from ..data import ShopData, ShopItemType
from .base import ShopCog, Shop, Customer, Store, ShopItem

if TYPE_CHECKING:
    from ..cog import Shopping
    from modules.economy.cog import Economy


_p = babel._p

logger = logging.getLogger(__name__)


class ColourRoleItem(ShopItem):
    """
    ShopItem representing an equippable Colour Role.
    """
    @property
    def role(self) -> Optional[discord.Role]:
        """
        Retrieves the discord Role corresponding to this colour role,
        if it exists.
        """
        guild = self.bot.get_guild(self.data.guildid)
        if guild is not None:
            return guild.get_role(self.data.roleid)

    @property
    def name(self):
        """
        An appropriate name for this Colour Role.

        Tries to use the role name if it is available.
        If it doesn't exist, instead uses the saved role id.
        """
        if (role := self.role) is not None:
            return role.name
        else:
            return str(self.data.roleid)

    @property
    def mention(self):
        """
        Helper method to mention the contained role.

        Avoids using the role object, in case it is not cached
        or no longer exists.
        """
        return f"<@&{self.data.roleid}>"

    @property
    def price(self):
        """
        The price of the item.
        """
        return self.data.price

    @property
    def itemid(self):
        """
        The global itemid for this item.
        """
        return self.data.itemid

    @property
    def colour(self) -> Optional[discord.Colour]:
        """
        Returns the colour of the linked role.

        If the linked role does not exist or cannot be found,
        returns None.
        """
        if (role := self.role) is not None:
            return role.colour
        else:
            return None

    def select_option_for(self, customer: Customer, owned=False) -> SelectOption:
        t = customer.bot.translator.t

        value = str(self.itemid)
        if not owned:
            label = t(_p(
                'ui:colourstore|menu:buycolours|label',
                "{name} ({price} LC)"
            )).format(name=self.name, price=self.price)
        else:
            label = t(_p(
                'ui:colourstore|menu:buycolours|label',
                "{name} (This is your colour!)"
            )).format(name=self.name)
        if (colour := self.colour) is not None:
            description = t(_p(
                'ui:colourstore|menu:buycolours|desc',
                "Colour: {colour}"
            )).format(colour=str(colour))
        else:
            description = t(_p(
                'ui:colourstore|menu:buycolours|desc',
                "Colour: Unknown"
            ))
        return SelectOption(
            label=label,
            value=value,
            description=description,
            default=owned
        )


class ColourShop(Shop):
    """
    A Shop class representing a Colour shop for a given customer.
    """
    _name_ = _p("shop:colours|name", 'Colour Shop')
    _item_type_ = ShopItemType.COLOUR

    def purchasable(self):
        """
        Returns a list of ColourRoleItems
        that the customer can afford, and does not own.
        """
        owned = self.owned()
        balance = self.customer.balance

        return [
            item for item in self.items
            if (owned is None or item.itemid != owned.itemid) and (item.price <= balance)
        ]

    async def purchase(self, itemid) -> ColourRoleItem:
        """
        Atomically handle a purchase of a ColourRoleItem.

        Various errors may occur here, from the user not actually having enough funds,
        to the ColourRole not being purchasable (because of e.g. permissions),
        or even the `itemid` somehow not referring to a colour role in the correct guild.

        If the purchase completes successfully, returns the purchased ColourRoleItem.
        If the purchase fails for a known reason, raises SafeCancellation, with the error information.
        """
        t = self.bot.translator.t
        conn = await self.bot.db.get_connection()
        async with conn.transaction():
            # Retrieve the item to purchase from data
            item = await self.data.ShopItemInfo.table.select_one_where(itemid=itemid)
            # Ensure the item is purchasable and not deleted
            if not item['purchasable'] or item['deleted']:
                raise SafeCancellation(
                    t(_p(
                        'shop:colour|purchase|error:not_purchasable',
                        "This item may not be purchased!"
                    ))
                )

            # Refresh the customer
            await self.customer.refresh()

            # Ensure the guild exists in cache
            guild = self.bot.get_guild(self.customer.guildid)
            if guild is None:
                raise SafeCancellation(
                    t(_p(
                        'shop:colour|purchase|error:no_guild',
                        "Could not retrieve the server from Discord!"
                    ))
                )

            # Ensure the customer member actually exists
            member = await self.customer.lion.fetch_member()
            if member is None:
                raise SafeCancellation(
                    t(_p(
                        'shop:colour|purchase|error:no_member',
                        "Could not retrieve the member from Discord."
                    ))
                )

            # Ensure the purchased role actually exists
            role = guild.get_role(item['roleid'])
            if role is None:
                raise SafeCancellation(
                    t(_p(
                        'shop:colour|purchase|error:no_role',
                        "This colour role could not be found in the server."
                    ))
                )

            # Ensure the customer has enough coins for the item
            if self.customer.balance < item['price']:
                raise SafeCancellation(
                    t(_p(
                        'shop:colour|purchase|error:low_balance',
                        "This item costs {coin}{amount}!\nYour balance is {coin}{balance}"
                    )).format(
                        coin=self.bot.config.emojis.getemoji('coin'),
                        amount=item['price'],
                        balance=self.customer.balance
                    )
                )

            owned = self.owned()
            if owned is not None:
                # Ensure the customer does not already own the item
                if owned.itemid == item['itemid']:
                    raise SafeCancellation(
                        t(_p(
                            'shop:colour|purchase|error:owned',
                            "You already own this item!"
                        ))
                    )

            # Charge the customer for the item
            economy_cog: Economy = self.bot.get_cog('Economy')
            economy_data = economy_cog.data
            transaction = await economy_data.ShopTransaction.purchase_transaction(
                guild.id,
                member.id,
                member.id,
                itemid,
                item['price']
            )

            # Add the item to the customer's inventory
            await self.data.MemberInventory.create(
                guildid=guild.id,
                userid=member.id,
                transactionid=transaction.transactionid,
                itemid=itemid
            )

            # Give the customer the role (do rollback if this fails)
            try:
                await member.add_roles(
                    role,
                    atomic=True,
                    reason="Purchased colour role"
                )
            except discord.NotFound:
                raise SafeCancellation(
                    t(_p(
                        'shop:colour|purchase|error:failed_no_role',
                        "This colour role no longer exists!"
                    ))
                )
            except discord.Forbidden:
                raise SafeCancellation(
                    t(_p(
                        'shop:colour|purchase|error:failed_permissions',
                        "I do not have enough permissions to give you this colour role!"
                    ))
                )
            except discord.HTTPException:
                raise SafeCancellation(
                    t(_p(
                        'shop:colour|purchase|error:failed_unknown',
                        "An unknown error occurred while giving you this colour role!"
                    ))
                )

            # At this point, the purchase has succeeded and the user has obtained the colour role
            # Now, remove their previous colour role (if applicable)
            # TODO: We should probably add an on_role_delete event to clear defunct colour roles
            if owned is not None:
                owned_role = owned.role
                if owned_role is not None:
                    try:
                        await member.remove_roles(
                            owned_role,
                            reason="Removing old colour role.",
                            atomic=True
                        )
                    except discord.HTTPException:
                        # Possibly Forbidden, or the role doesn't actually exist anymore (cache failure)
                        pass
                await self.data.MemberInventory.table.delete_where(inventoryid=owned.data.inventoryid)

            # Purchase complete, update the shop and customer
            await self.refresh()
            return self.owned()

    async def refresh(self):
        """
        Refresh the customer and item data.
        """
        data = await self.data.ShopItemInfo.table.select_where(
            item_type=self._item_type_,
            deleted=False,
            guildid=self.customer.guildid
        ).order_by('itemid')
        self.items = [ColourRoleItem(self.bot, self.data.ShopItemInfo(row)) for row in data]
        await self.customer.refresh()

    def owned(self) -> Optional[ColourRoleItem]:
        """
        Returns the ColourRoleItem currently owned by the Customer, if any.

        Since this item may have been deleted, it may not appear in the shop inventory!
        """
        for item in self.customer.inventory:
            if item.item_type is self._item_type_:
                return ColourRoleItem(self.bot, item)

    def make_store(self, interaction: discord.Interaction):
        return ColourStore(self, interaction)


@ShopCog.register
class ColourShopping(ShopCog):
    """
    Cog in charge of colour shopping.

    Registers colour shop related commands and methods.
    """
    _shop_cls_ = ColourShop

    async def load_into(self, cog: 'Shopping'):
        self.crossload_group(self.editshop_group, cog.editshop_group)
        await cog.bot.add_cog(self)

    @LionCog.placeholder_group
    @cmds.hybrid_group('editshop', with_app_command=False)
    async def editshop_group(self, ctx: LionContext):
        pass

    @editshop_group.group(_p('grp:editshop_colours', 'colours'))
    async def editshop_colours_group(self, ctx: LionContext):
        pass

    @editshop_colours_group.command(
        name=_p('cmd:editshop_colours_create', 'create'),
        description=_p(
            'cmd:editshop_colours_create|desc',
            "Create a new colour role with the given colour."
        )
    )
    @appcmds.rename(
        colour=_p('cmd:editshop_colours_create|param:colour', "colour"),
        name=_p('cmd:editshop_colours_create|param:name', "name"),
        price=_p('cmd:editshop_colours_create|param:price', "price")
    )
    @appcmds.describe(
        colour=_p(
            'cmd:editshop_colours_create|param:colour|desc',
            "What colour should the role be? (As a hex code, e.g. #AB22AB)"
        ),
        name=_p(
            'cmd:editshop_colours_create|param:name|desc',
            "What should the colour role be called?"
        ),
        price=_p(
            'cmd:editshop_colours_create|param:price|desc',
            "How much should the colour role cost?"
        )
    )
    async def editshop_colours_create_cmd(self, ctx: LionContext,
                                          colour: appcmds.Range[str, 3, 100],
                                          name: appcmds.Range[str, 1, 100],
                                          price: appcmds.Range[int, 0, MAX_COINS]):
        """
        Create a new colour role with the specified attributes.
        """
        t = self.bot.translator.t
        if not ctx.interaction:
            return
        if not ctx.guild:
            return

        try:
            actual_colour = discord.Colour.from_str(colour)
        except ValueError:
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_colours_create|error:parse_colour',
                    "I could not extract a colour value from `{colour}`!\n"
                    "Please enter the colour as a hex string, e.g. `#FA0BC1`"
                )).format(colour=colour)
            )

        # Check we actually have permissions to create the role
        if not ctx.guild.me.guild_permissions.manage_roles:
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_colours_create|error:perms',
                    "I do not have permission to create server roles!\n"
                    "Please either give me this permission, "
                    "or create the role manually and use `/editshop colours add` instead."
                ))
            )

        # Check our current colour roles, make sure we don't have 25 already
        current = await self.data.ShopItemInfo.fetch_where(
            guildid=ctx.guild.id,
            item_type=self._shop_cls_._item_type_,
            deleted=False
        )
        if len(current) >= 25:
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_colours_create|error:max_colours',
                    "This server already has the maximum of `25` colour roles!\n"
                    "Please remove some before adding or creating more."
                ))
            )

        # Create the role
        try:
            role = await ctx.guild.create_role(
                name=name,
                colour=actual_colour,
                hoist=False,
                mentionable=False,
                reason="Creating Colour Role (/editshop colours create)"
            )
        except discord.HTTPException:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:editshop_colours_create|error:failed_unknown',
                        "An unknown Discord error occurred while creating your colour role!\n"
                        "Please try again in a few minutes."
                    ))
                ),
                ephemeral=True
            )
            await logger.warning(
                "Unexpected Discord exception occurred while creating a colour role.",
                exc_info=True
            )
            return

        # Identify where we should put the role
        # If the server already has colour roles, we put it underneath those,
        # as long as that is below our own top role.
        # Otherwise, we leave them alone

        current_roles = (ctx.guild.get_role(item.roleid) for item in current)
        current_roles = [role for role in current_roles if role is not None]
        if current_roles:
            position = min(*current_roles, ctx.guild.me.top_role).position
            position -= 1
        else:
            position = 0

        if position > 0:
            # Due to the imprecise nature of Discord role ordering, this may fail.
            try:
                role = await role.edit(position=position)
            except discord.Forbidden:
                position = 0

        # Now that the role is set up, add it to data
        item = await self.data.ShopItem.create(
            guildid=ctx.guild.id,
            item_type=self._shop_cls_._item_type_,
            price=price,
            purchasable=True
        )
        await self.data.ColourRole.create(
            itemid=item.itemid,
            roleid=role.id
        )

        # And finally ack the request
        embed = discord.Embed(
            colour=actual_colour,
        )
        embed.title = t(_p(
            'cmd:editshop_colours_create|resp:done|title',
            "Colour Role Created"
        ))
        embed.description = t(_p(
            'cmd:editshop_colours_create|resp:done|desc',
            "You have created the role {mention}, "
            "and added it to the colour shop for {coin}**{price}**!"
        )).format(mention=role.mention, coin=self.bot.config.emojis.getemoji('coin'), price=price)

        if position == 0:
            note = t(_p(
                'cmd:editshop_colours_create|resp:done|field:position_note|value',
                "The new colour role was added below all other roles. "
                "Remember a member's active colour is determined by their highest coloured role!"
            ))
            embed.add_field(
                name=t(_p('cmd:editshop_colours_create|resp:done|field:position_note|name', "Note")),
                value=note
            )

        await ctx.reply(
            embed=embed,
        )

    @editshop_colours_group.command(
        name=_p('cmd:editshop_colours_edit', 'edit'),
        description=_p(
            'cmd:editshop_colours_edit|desc',
            "Edit the name, colour, or price of a colour role."
        )
    )
    @appcmds.rename(
        role=_p('cmd:editshop_colours_edit|param:role', "role"),
        name=_p('cmd:editshop_colours_edit|param:name', "name"),
        colour=_p('cmd:editshop_colours_edit|param:colour', "colour"),
        price=_p('cmd:editshop_colours_edit|param:price', "price"),
    )
    @appcmds.describe(
        role=_p(
            'cmd:editshop_colours_edit|param:role|desc',
            "Select a colour role to edit."
        ),
        name=_p(
            'cmd:editshop_colours_edit|param:name|desc',
            "New name to give the colour role."
        ),
        colour=_p(
            'cmd:editshop_colours_edit|param:colour|desc',
            "New colour for the colour role (as hex, e.g. #AB12AB)."
        ),
        price=_p(
            'cmd:editshop_colours_edit|param:price|desc',
            "New price for the colour role."
        ),
    )
    async def editshop_colours_edit_cmd(self, ctx: LionContext,
                                        role: discord.Role,
                                        name: Optional[appcmds.Range[str, 1, 100]],
                                        colour: Optional[appcmds.Range[str, 3, 100]],
                                        price: Optional[appcmds.Range[int, 0, MAX_COINS]]):
        """
        Edit the provided colour role with the given attributes.
        """
        t = self.bot.translator.t
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # First check the provided role is actually a colour role
        items = await self.data.ShopItemInfo.fetch_where(
            guildid=ctx.guild.id,
            deleted=False,
            item_type=self._shop_cls_._item_type_,
            roleid=role.id
        )
        if not items:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:editshop_colours_edit|error:invalid_role',
                        "{mention} is not in the colour role shop!"
                    )).format(mention=role.mention)
                ),
                ephemeral=True
            )
            return
        item = items[0]

        # Check that we actually have something to edit
        if name is None and colour is None and price is None:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:editshop_colours_edit|error:no_args',
                        "You must give me one of `name`, `colour`, or `price` to update!"
                    ))
                ),
                ephemeral=True
            )
            return

        # Check the colour works
        if colour is not None:
            try:
                actual_colour = discord.Colour.from_str(colour)
            except ValueError:
                await ctx.reply(
                    embed=error_embed(
                        t(_p(
                            'cmd:editshop_colours_edit|error:parse_colour',
                            "I could not extract a colour value from `{colour}`!\n"
                            "Please enter the colour as a hex string, e.g. `#FA0BC1`"
                        )).format(colour=colour)
                    ),
                    ephemeral=True
                )
                return

        if name is not None or colour is not None:
            # Check we actually have permissions to update the role if needed
            if not ctx.guild.me.guild_permissions.manage_roles or not ctx.guild.me.top_role > role:
                await ctx.reply(
                    embed=error_embed(
                        t(_p(
                            'cmd:editshop_colours_edit|error:perms',
                            "I do not have sufficient server permissions to edit this role!"
                        ))
                    ),
                    ephemeral=True
                )
                return

        # Now update the information
        lines = []
        if price is not None:
            await self.data.ShopItem.table.update_where(
                itemid=item.itemid
            ).set(price=price)
            lines.append(
                t(_p(
                    'cmd:editshop_colours_edit|resp:done|line:price',
                    "{tick} Set price to {coin}**{price}**"
                )).format(
                    tick=self.bot.config.emojis.getemoji('tick'),
                    coin=self.bot.config.emojis.getemoji('coin'),
                    price=price
                )
            )
        if name is not None or colour is not None:
            args = {}
            if name is not None:
                args['name'] = name
            if colour is not None:
                args['colour'] = actual_colour
            role = await role.edit(**args)
            lines.append(
                t(_p(
                    'cmd:editshop_colours_edit|resp:done|line:role',
                    "{tick} Updated role to {mention}"
                )).format(
                    tick=self.bot.config.emojis.getemoji('tick'),
                    mention=role.mention
                )
            )

        description = '\n'.join(lines)
        await ctx.reply(
            embed=discord.Embed(
                title=t(_p('cmd:editshop_colours_edit|resp:done|embed:title', "Colour Role Updated")),
                description=description
            )
        )

    @editshop_colours_group.command(
        name=_p('cmd:editshop_colours_auto', 'auto'),
        description=_p('cmd:editshop_colours_auto|desc', "Automatically create a set of colour roles.")
    )
    async def editshop_colours_auto_cmd(self, ctx: LionContext):
        """
        Automatically create a set of colour roles.
        """
        await ctx.reply("Not Implemented Yet")

    @editshop_colours_group.command(
        name=_p('cmd:editshop_colours_add', 'add'),
        description=_p(
            'cmd:editshop_colours_add|desc',
            "Add an existing role to the colour shop."
        )
    )
    @appcmds.rename(
        role=_p('cmd:editshop_colours_add|param:role', "role"),
        price=_p('cmd:editshop_colours_add|param:price', "price")
    )
    @appcmds.describe(
        role=_p(
            'cmd:editshop_colours_add|param:role|desc',
            "Select a role to add to the colour shop."
        ),
        price=_p(
            'cmd:editshop_colours_add|param:price|desc',
            "How much should this role cost?"
        )
    )
    async def editshop_colours_add_cmd(self, ctx: LionContext,
                                       role: discord.Role,
                                       price: appcmds.Range[int, 0, MAX_COINS]):
        """
        Add a new colour role from an existing role.
        """
        t = self.bot.translator.t
        if not ctx.interaction:
            return
        if not ctx.guild:
            return

        # Check our current colour roles, make sure we don't have 25 already
        current = await self.data.ShopItemInfo.fetch_where(
            guildid=ctx.guild.id,
            item_type=self._shop_cls_._item_type_,
            deleted=False
        )
        if len(current) >= 25:
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_colours_add|error:max_colours',
                    "This server already has the maximum of `25` colour roles!\n"
                    "Please remove some before adding or creating more."
                ))
            )
        # Also check the role isn't currently in the role list
        if role.id in [item.roleid for item in current]:
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_colours_add|error:role_exists',
                    "The role {mention} is already registered as a colour role!"
                )).format(mention=role.mention)
            )

        # Check that I have permission and ability to manage this role
        if not (ctx.guild.me.guild_permissions.manage_roles and role.is_assignable()):
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_colours_add|error:role_perms',
                    "I do not have enough permissions to assign the role {mention}! "
                    "Please ensure I have the `MANAGE_ROLES` permission, and that "
                    "my top role is above this role."
                )).format(mention=role.mention)
            )

        # Check that the author has permission to manage this role
        if not (ctx.author.guild_permissions.manage_roles and ctx.author.top_role > role):
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_colours_add|error:caller_perms',
                    "You do not have sufficient server permissions to assign {mention} to the shop! "
                    "You must have `MANAGE_ROLES`, and your top role must be above this role."
                )).format(mention=role.mention)
            )

        if role.permissions.administrator:
            raise SafeCancellation(
                t(_p(
                    'cmd:editshop_colours_add|error:role_has_admin',
                    "I refuse to add an administrator role to the LionCoin shop. "
                    "That is a really bad idea."
                ))
            )

        # Add the role to data
        item = await self.data.ShopItem.create(
            guildid=ctx.guild.id,
            item_type=self._shop_cls_._item_type_,
            price=price,
            purchasable=True
        )
        await self.data.ColourRole.create(
            itemid=item.itemid,
            roleid=role.id
        )

        # And finally ack the request
        embed = discord.Embed(
            colour=role.colour,
        )
        embed.title = t(_p('cmd:editshop_colours_add|resp:done|embed:title', "Colour Role Created"))
        embed.description = t(_p(
            'cmd:editshop_colours_add|resp:done|embed:desc',
            "You have added {mention} to the colour shop for {coin}**{price}**!"
        )).format(mention=role.mention, coin=self.bot.config.emojis.getemoji('coin'), price=price)

        await ctx.reply(
            embed=embed,
        )

    @editshop_colours_group.command(
        name=_p('cmd:editshop_colours_clear', 'clear'),
        description=_p(
            'cmd:editshop_colours_clear|desc',
            "Remove all the colour roles from the shop, and optionally delete the roles."
        )
    )
    @appcmds.rename(
        delete=_p('cmd:editshop_colours_clear|param:delete', "delete_roles")
    )
    @appcmds.rename(
        delete=_p(
            'cmd:editshop_colours_clear|param:delete|desc',
            "Also delete the associated roles."
        )
    )
    async def editshop_colours_clear_cmd(self, ctx: LionContext, delete: Optional[bool]):
        """
        Remove all of the colour roles.

        Optionally refund and/or delete the roles themselves.
        """
        t = self.bot.translator.t
        if not ctx.guild:
            return

        if not ctx.interaction:
            return

        # TODO: Implement refund
        refund = False

        # Fetch our current colour roles
        current = await self.data.ShopItemInfo.fetch_where(
            guildid=ctx.guild.id,
            item_type=self._shop_cls_._item_type_,
            deleted=False
        )
        itemids = [item.itemid for item in current]
        roles = (ctx.guild.get_role(item.roleid) for item in current)
        roles = [role for role in roles if role is not None]
        if refund:
            inventory_items = await self.data.MemberInventory.fetch_where(
                guildid=ctx.guild.id,
                itemid=itemids
            )
        else:
            inventory_items = None

        # If we don't have any, error out gracefully
        if not current:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:editshop_colours_clear|error:no_colours',
                        "There are no coloured roles to remove!"
                    ))
                ),
                ephemeral=True
            )
            return

        deleted = []
        delete_failed = []
        refunded = []

        async def delete_roles():
            for role in roles:
                try:
                    await role.delete(reason="Clearing colour role shop")
                    deleted.append(role)
                except discord.HTTPException:
                    delete_failed.append(role)
                await asyncio.sleep(0.2)

        async def refund_members():
            """
            Refunds the members with the colour roles.
            """
            ...

        async def status_loop():
            while True:
                try:
                    done = await status_update()
                    if done:
                        break
                    else:
                        await asyncio.sleep(2)
                except asyncio.CancelledError:
                    return

        async def status_update():
            tick = self.bot.config.emojis.getemoji('tick')
            loading = self.bot.config.emojis.getemoji('loading')
            lines = []

            cleared_line = t(_p(
                'cmd:editshop_colours_clear|resp:done|line:clear',
                "{tick} Colour shop cleared."
            )).format(tick=tick)
            lines.append(cleared_line)
            done = True

            if refund:
                count = len(refunded)
                total = len(inventory_items)
                if count < total:
                    refund_line = t(_p(
                        'cmd:editshop_colours_clear|resp:done|line:refunding',
                        "{loading} Refunded **{count}/{total}** members."
                    ))
                    done = False
                else:
                    refund_line = t(_p(
                        'cmd:editshop_colours_clear|resp:done|line:refunded',
                        "{tick} Refunded **{total}/{total}** members."
                    ))
                lines.append(
                    refund_line.format(tick=tick, loading=loading, count=count, total=total)
                )

            if delete:
                count = len(deleted)
                failed = len(delete_failed)
                total = len(roles)
                if failed:
                    delete_line = t(_p(
                        'cmd:editshop_colours_clear|resp:done|line:deleted_failed',
                        "{emoji} Deleted **{count}/{total}** colour roles. (**{failed}** failed!)"
                    ))
                else:
                    delete_line = t(_p(
                        'cmd:editshop_colours_clear|resp:done|line:deleted',
                        "{emoji} Deleted **{count}/{total}** colour roles."
                    ))

                if count + failed < total:
                    done = False

                lines.append(
                    delete_line.format(
                        emoji=loading if count + failed < total else tick,
                        count=count, total=total, failed=failed
                    )
                )
            description = '\n'.join(lines)
            embed = discord.Embed(
                colour=discord.Colour.light_grey() if not done else discord.Colour.brand_green(),
                description=description
            )
            await ctx.interaction.edit_original_response(embed=embed)
            return done

        await ctx.interaction.response.defer(thinking=True)

        # Run the clear
        await self.data.ShopItem.table.update_where(itemid=itemids).set(deleted=True)

        tasks = []

        # Refund the members (slowly)
        if refund:
            tasks.append(asyncio.create_task(refund_members()))

        # Delete the roles (slowly)
        if delete:
            tasks.append(asyncio.create_task(delete_roles()))

        loop_task = None
        try:
            if tasks:
                loop_task = asyncio.create_task(status_loop())
                tasks.append(loop_task)
                await asyncio.gather(*tasks)
            else:
                await status_update()
        finally:
            if loop_task is not None and not loop_task.done() and not loop_task.cancelled():
                loop_task.cancel()
                await status_update()

    @editshop_colours_group.command(
        name=_p('cmd:editshop_colours_remove', 'remove'),
        description=_p(
            'cmd:editshop_colours_remove|desc',
            "Remove a specific colour role from the shop."
        )
    )
    @appcmds.rename(
        role=_p('cmd:editshop_colours_remove|param:role', "role"),
        delete_role=_p('cmd:editshop_colours_remove', "delete_role")
    )
    @appcmds.describe(
        role=_p(
            'cmd:editshop_colours_remove|param:role|desc',
            "Select the colour role to remove."
        ),
        delete_role=_p(
            'cmd:editshop_colours_remove|param:delete_role|desc',
            "Whether to delete the associated role."
        )
    )
    async def editshop_colours_remove_cmd(self, ctx: LionContext, role: discord.Role, delete_role: Optional[bool]):
        """
        Remove a specific colour role.
        """
        t = self.bot.translator.t
        if not ctx.guild:
            return
        if not ctx.interaction:
            return

        # First check the provided role is actually a colour role
        items = await self.data.ShopItemInfo.fetch_where(
            guildid=ctx.guild.id,
            deleted=False,
            item_type=self._shop_cls_._item_type_,
            roleid=role.id
        )
        if not items:
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:editshop_colours_remove|error:not_colour',
                        "{mention} is not in the colour role shop!"
                    )).format(mention=role.mention)
                ),
                ephemeral=True
            )
            return
        item = items[0]

        # Delete the item, respecting the delete setting.
        await self.data.ShopItem.table.update_where(itemid=item.itemid, deleted=True)

        if delete_role:
            role = ctx.guild.get_role(item.roleid)
            if role:
                try:
                    await role.delete()
                    role_msg = t(_p(
                        'cmd:editshop_colours_remove|resp:done|line:delete',
                        "Successfully deleted the role."
                    ))
                except discord.Forbidden:
                    role_msg = t(_p(
                        'cmd:editshop_colours_remove|resp:done|line:delete',
                        "I do not have sufficient permissions to delete the role."
                    ))
                except discord.HTTPException:
                    role_msg = t(_p(
                        'cmd:editshop_colours_remove|resp:done|line:delete',
                        "Failed to delete the role for an unknown reason."
                    ))
            else:
                role_msg = t(_p(
                    'cmd:editshop_colours_remove|resp:done|line:delete',
                    "Could not find the role in order to delete it."
                ))
        else:
            role_msg = ""

        # Ack the action
        await ctx.reply(
            embed=discord.Embed(
                colour=discord.Colour.brand_green(),
                description=t(_p(
                    'cmd:editshop_colours_remove|resp:done|embed:desc',
                    "Removed {mention} from the colour shop.\n{delete_line}"
                )).format(mention=role.mention, delete_line=role_msg)
            )
        )

    async def editshop_colours_remove_acmpl_item(self, interaction: discord.Interaction, partial: str):
        """
        This is not currently in use.
        Intended to be transferred to `/shop buy` autocomplete.
        """
        items = await self.data.ShopItemInfo.fetch_where(
            guildid=interaction.guild.id,
            deleted=False,
            item_type=self._shop_cls_._item_type_
        ).order_by('itemid')
        if not items:
            return [
                appcmds.Choice(
                    name="The colour role shop is empty!",
                    value=partial
                )
            ]
        else:
            options = [
                (str(i), "[{itemid:02}] | {price} LC | {colour} | @{name}".format(
                    itemid=i,
                    price=item.price,
                    colour=role.colour if (role := interaction.guild.get_role(item.roleid)) is not None else "#??????",
                    name=role.name if role is not None else "deleted-role"
                ))
                for i, item in enumerate(items, start=1)
            ]
            options = [option for option in options if partial.lower() in option[1].lower()]
            return [appcmds.Choice(name=option[1], value=option[0]) for option in options]


class ColourStore(Store):
    """
    Ephemeral UI providing access to the colour store.
    """
    shop: ColourShop

    @select(placeholder="SELECT_PLACEHOLDER")
    async def select_colour(self, interaction: discord.Interaction, selection: Select):
        t = self.shop.bot.translator.t

        # User selected a colour from the list
        # Run purchase pathway for that item
        # The selection value should be the global itemid
        # However, if the selection is currently owned, do absolutely nothing.
        itemid = int(selection.values[0])
        if (owned := self.shop.owned()) and owned.itemid == itemid:
            await interaction.response.defer()
        else:
            # Run purchase pathway
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                item = await self.shop.purchase(itemid)
            except SafeCancellation as exc:
                embed = discord.Embed(
                    title=t(_p('ui:colourstore|menu:buycolours|embed:error|title', "Purchase Failed!")),
                    colour=discord.Colour.brand_red(),
                    description=exc.msg
                )
                await interaction.edit_original_response(embed=embed)
            else:
                # Ack purchase
                embed = discord.Embed(
                    colour=discord.Colour.brand_green(),
                    description=t(_p(
                        'ui:colourstore|menu:buycolours|resp:done|desc',
                        "{tick} You have purchased {mention}"
                    )).format(
                        mention=item.mention,
                        tick=self.shop.bot.config.emojis.getemoji('tick')
                    )
                )
                await interaction.edit_original_response(embed=embed)
                await self.refresh()
                await self.redraw()

    async def select_colour_refresh(self):
        """
        Refresh the select colour menu.

        For an item to be purchasable,
        it needs to be affordable and not currently owned by the member.
        """
        t = self.shop.bot.translator.t
        selector = self.select_colour

        # Get the list of ColourRoleItems that may be purchased
        purchasable = self.shop.purchasable()
        owned = self.shop.owned()

        option_map: dict[int, SelectOption] = {}

        for item in purchasable:
            option_map[item.itemid] = item.select_option_for(self.shop.customer)

        if owned is not None and owned.role is not None:
            option_map[owned.itemid] = owned.select_option_for(self.shop.customer, owned=True)

        if not option_map:
            selector.placeholder = t(_p(
                'ui:colourstore|menu:buycolours|placeholder',
                "There are no colour roles available to purchase!"
            ))
            selector.disabled = True
        else:
            selector.placeholder = t(_p(
                'ui:colourstore|menu:buycolours|placeholder',
                "Select a colour role to purchase!"
            ))
            selector.disabled = False
            selector.options = list(option_map.values())

    async def refresh(self):
        """
        Refresh the UI elements
        """
        await self.select_colour_refresh()
        if not self.select_colour.options:
            self._layout = [self.store_row]
        else:
            self._layout = [(self.select_colour,), self.store_row]

        self.embed = self.make_embed()

    def make_embed(self):
        """
        Embed for this shop.
        """
        t = self.shop.bot.translator.t
        if self.shop.items:
            owned = self.shop.owned()
            lines = []
            for i, item in enumerate(self.shop.items):
                if owned is not None and item.itemid == owned.itemid:
                    line = t(_p(
                        'ui:colourstore|embed|line:owned_item',
                        "`[{j:02}]` | `{price} LC` | {mention} (You own this!)"
                    )).format(j=i+1, price=item.price, mention=item.mention)
                else:
                    line = t(_p(
                        'ui:colourstore|embed|line:item',
                        "`[{j:02}]` | `{price} LC` | {mention}"
                    )).format(j=i+1, price=item.price, mention=item.mention)
                lines.append(line)
            description = '\n'.join(lines)
        else:
            description = t(_p(
                'ui:colourstore|embed|desc',
                "No colour roles available for purchase!"
            ))
        embed = discord.Embed(
            title=t(_p('ui:colourstore|embed|title', "Colour Role Shop")),
            description=description
        )
        return embed

from typing import List
import datetime
import discord

from cmdClient.lib import SafeCancellation
from meta import client

from .ShopItem import ShopItem, ShopItemType
from .data import shop_items, shop_item_info, colour_roles


@ShopItem.register_item_class
class ColourRole(ShopItem):
    item_type = ShopItemType.COLOUR_ROLE

    allow_multi_select = False
    buy_hint = (
        "Buy a colour by typing, e.g.,`{prefix}buy 0`.\n"
        "**Note: You may only own one colour at a time!**"
    ).format(prefix=client.prefix)

    @property
    def display_name(self):
        return "<@&{}>".format(self.data.roleid)

    @property
    def roleid(self) -> int:
        return self.data.roleid

    @classmethod
    async def create(cls, guildid, price, roleid, **kwargs):
        """
        Create a new ColourRole item.
        """
        shop_row = shop_items.insert(
            guildid=guildid,
            item_type=cls.item_type,
            price=price
        )
        colour_roles.insert(
            itemid=shop_row['itemid'],
            roleid=roleid
        )
        return cls(shop_row['itemid'])

    # Shop interface
    @classmethod
    def _cat_shop_embed_items(cls, items: List['ColourRole'], **kwargs) -> List[discord.Embed]:
        """
        Embed a list of items specifically for displaying in the shop.
        Subclasses will usually extend or override this, if only to add metadata.
        """
        if items:
            # TODO: prefix = items[0].guild_settings.prefix.value

            embeds = cls._cat_embed_items(items, **kwargs)
            for embed in embeds:
                embed.title = "{} shop!".format(cls.item_type.desc)
                embed.description += "\n\n" + cls.buy_hint
        else:
            embed = discord.Embed(
                title="{} shop!".format(cls.item_type.desc),
                description="No colours available at the moment! Please come back later."
            )
            embeds = [embed]
        return embeds

    async def buy(self, ctx):
        """
        Action when a member buys a color role.

        Uses Discord as the source of truth (rather than the future inventory).
        Removes any existing colour roles, and adds the purchased role.
        Also notifies the user and logs the transaction.
        """
        # TODO: Exclusivity should be handled at a higher level
        # TODO: All sorts of error handling
        member = ctx.author

        # Fetch the set colour roles
        colour_rows = shop_item_info.fetch_rows_where(
            guildid=self.guildid,
            item_type=self.item_type
        )
        roleids = (row.roleid for row in colour_rows)
        roles = (self.guild.get_role(roleid) for roleid in roleids)
        roles = set(role for role in roles if role)

        # Compute the roles to add and remove
        to_add = self.guild.get_role(self.roleid)
        member_has = roles.intersection(member.roles)
        if to_add in member_has:
            await ctx.error_reply("You already have this colour!")
            return False

        to_remove = list(member_has)

        # Role operations
        if to_add:
            try:
                await member.add_roles(to_add, reason="Updating purchased colour role")
            except discord.HTTPException:
                # TODO: Add to log
                to_add = None
                pass

            if to_remove:
                try:
                    await member.remove_roles(*to_remove, reason="Updating purchased colour role")
                except discord.HTTPException:
                    # TODO: Add to log
                    pass

        # Only charge the member if everything went well
        if to_add:
            ctx.alion.addCoins(-self.price)

        # Build strings for logging and response
        desc = None  # Description of reply message to the member
        log_str = None  # Description of event log message
        log_error = False  # Whether to log an error

        if to_add:
            if to_remove:
                if len(to_remove) > 1:
                    rem_str = ', '.join(role.mention for role in to_remove[:-1]) + 'and' + to_remove[-1].mention
                else:
                    rem_str = to_remove[0].mention
                desc = "You have exchanged {} for {}. Enjoy!".format(rem_str, to_add.mention)
                log_str = "{} exchanged {} for {}.".format(
                    member.mention,
                    rem_str,
                    to_add.mention
                )
            else:
                desc = "You have bought {}. Enjoy!".format(to_add.mention)
                log_str = "{} bought {}.".format(member.mention, to_add.mention)
        else:
            desc = "Something went wrong! Please try again later."
            log_str = "{} bought `{}`, but I couldn't add the role!".format(member.mention, self.roleid)
            log_error = True

        # Build and send embeds
        reply_embed = discord.Embed(
            colour=to_add.colour if to_add else discord.Colour.red(),
            description=desc,
            timestamp=datetime.datetime.utcnow()
        )
        if to_add:
            reply_embed.set_footer(
                text="New Balance: {} LC".format(ctx.alion.coins)
            )
        log_embed = discord.Embed(
            title="Colour Role Purchased" if not log_error else "Error purchasing colour role.",
            colour=discord.Colour.red() if log_error else discord.Colour.orange(),
            description=log_str
        )
        try:
            await ctx.reply(embed=reply_embed)
        except discord.HTTPException:
            pass

        event_log = ctx.guild_settings.event_log.value
        if event_log:
            try:
                await event_log.send(embed=log_embed)
            except discord.HTTPException:
                pass

        if not to_add:
            return False

        return True

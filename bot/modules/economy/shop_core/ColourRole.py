import re
import asyncio
from typing import List
import datetime
import discord

from cmdClient.lib import SafeCancellation
from meta import client
from utils.lib import multiselect_regex, parse_ranges

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

    @property
    def role(self) -> discord.Role:
        return self.guild.get_role(self.roleid)

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
    def _cat_shop_embed_items(cls, items: List['ColourRole'], hint: str = buy_hint, **kwargs) -> List[discord.Embed]:
        """
        Embed a list of items specifically for displaying in the shop.
        Subclasses will usually extend or override this, if only to add metadata.
        """
        if items:
            # TODO: prefix = items[0].guild_settings.prefix.value

            embeds = cls._cat_embed_items(items, **kwargs)
            for embed in embeds:
                embed.title = "{} shop!".format(cls.item_type.desc)
                embed.description += "\n\n" + hint
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

    # Shop admin interface
    @classmethod
    async def parse_add(cls, ctx, args):
        """
        Parse a request to add colour roles.
        Syntax: `<price>, <role>`, with different lines treated as different entries.

        Assumes the author is an admin.
        """
        if not args:
            raise SafeCancellation("No arguments given, nothing to do!")

        lines = args.splitlines()
        to_add = []  # List of (price, role) tuples to add
        for line in lines:
            # Syntax: <price>, <role>
            splits = line.split(',')
            splits = [split.strip() for split in splits]
            if len(splits) < 2 or not splits[0].isdigit():
                raise SafeCancellation("**Syntax:** `--add <price>, <role>`")
            price = int(splits[0])
            role = await ctx.find_role(splits[1], create=True, interactive=True, allow_notfound=False)
            to_add.append((price, role))

        # Add the roles to data
        for price, role in to_add:
            # TODO: Batch update would be best
            await cls.create(ctx.guild.id, price, role.id)

        # Report back
        if len(to_add) > 1:
            await ctx.reply(
                embed=discord.Embed(
                    title="Shop Updated",
                    description="Added `{}` new colours to the shop!".format(len(to_add))
                )
            )
        else:
            await ctx.reply(
                embed=discord.Embed(
                    title="Shop Updated",
                    description="Added {} to the shop for `{}` coins.".format(to_add[0][1].mention, to_add[0][0])
                )
            )

    @classmethod
    async def parse_remove(cls, ctx, args, items):
        """
        Parse a request to remove colour roles.
        Syntax: `<ids>` or `<command separated roles>`

        Assumes the author is an admin.
        """
        if not items:
            raise SafeCancellation("Colour shop is empty, nothing to delete!")

        to_delete = []
        if args:
            if re.search(multiselect_regex, args):
                # ids were selected
                indexes = parse_ranges(args)
                to_delete = [items[index] for index in indexes if index < len(items)]

            if not to_delete:
                # Assume comma separated list of roles
                splits = args.split(',')
                splits = [split.strip() for split in splits]
                available_roles = (item.role for item in items)
                available_roles = [role for role in available_roles if role]
                roles = [
                    await ctx.find_role(rolestr, collection=available_roles, interactive=True, allow_notfound=False)
                    for rolestr in splits
                ]
                roleids = set(role.id for role in roles)
                to_delete = [item for item in items if item.roleid in roleids]
        else:
            # Interactive multi-selector
            itemids = [item.itemid for item in items]
            embeds = cls.cat_shop_embeds(
                ctx.guild.id,
                itemids,
                hint=("Please select colour(s) to remove, or `c` to cancel.\n"
                      "(Respond with e.g. `1, 2, 3` or `1-3`.)")
            )
            out_msg = await ctx.pager(embeds)

            def check(msg):
                valid = msg.channel == ctx.ch and msg.author == ctx.author
                valid = valid and (re.search(multiselect_regex, msg.content) or msg.content.lower() == 'c')
                return valid

            try:
                message = await ctx.client.wait_for('message', check=check, timeout=60)
            except asyncio.TimeoutError:
                await out_msg.delete()
                await ctx.error_reply("Session timed out. No colour roles were removed.")
                return

            try:
                await out_msg.delete()
                await message.delete()
            except discord.HTTPException:
                pass

            if message.content.lower() == 'c':
                return

            to_delete = [
                items[index]
                for index in parse_ranges(message.content) if index < len(items)
            ]
            if not to_delete:
                raise SafeCancellation("Nothing to delete!")

        # Build an ack string before we delete
        rolestr = to_delete[0].role.mention if to_delete[0].role else "`{}`".format(to_delete[0].roleid)

        # Delete the items
        shop_items.delete_where(itemid=[item.itemid for item in to_delete])

        # Update the info cache
        [shop_item_info.row_cache.pop(item.itemid, None) for item in to_delete]

        # Ack and log
        if len(to_delete) > 1:
            try:
                await ctx.reply(
                    embed=discord.Embed(
                        title="Colour Roles removed",
                        description="You have removed `{}` colour roles.".format(len(to_delete)),
                        colour=discord.Colour.orange()
                    )
                )
            except discord.HTTPException:
                pass
            event_log = ctx.guild_settings.event_log.value
            if event_log:
                try:
                    await event_log.send(
                        embed=discord.Embed(
                            title="Colour Roles deleted",
                            description="{} removed `{}` colour roles from the shop.".format(
                                ctx.author.mention,
                                len(to_delete)
                            ),
                            timestamp=datetime.datetime.utcnow()
                        )
                    )
                except discord.HTTPException:
                    pass
        else:
            try:
                await ctx.reply(
                    embed=discord.Embed(
                        title="Colour Role removed",
                        description="You have removed the colour role {}.".format(rolestr),
                        colour=discord.Colour.orange()
                    )
                )
            except discord.HTTPException:
                pass
            event_log = ctx.guild_settings.event_log.value
            if event_log:
                try:
                    await event_log.send(
                        embed=discord.Embed(
                            title="Colour Role deleted",
                            description="{} removed the colour role {} from the shop.".format(
                                ctx.author.mention,
                                rolestr
                            ),
                            timestamp=datetime.datetime.utcnow()
                        )
                    )
                except discord.HTTPException:
                    pass

    @classmethod
    async def parse_clear(cls, ctx):
        """
        Parse a request to clear colour roles.

        Assumes the author is an admin.
        """
        if await ctx.ask("Are you sure you want to remove all colour roles from the shop?"):
            shop_items.delete_where(guildid=ctx.guild.id, item_type=cls.item_type)
            await ctx.reply("All colour roles deleted.")
            await ctx.guild_settings.event_log.log("{} cleared the colour role shop.".format(ctx.author.mention))

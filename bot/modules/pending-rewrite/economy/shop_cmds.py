import asyncio
import discord
from collections import defaultdict

from cmdClient.checks import in_guild

from .module import module
from .shop_core import ShopItem, ShopItemType, ColourRole
from wards import is_guild_admin


class ShopSession:
    __slots__ = (
        'key', 'response',
        '_event', '_task'
    )
    _sessions = {}

    def __init__(self, userid, channelid):
        # Build unique context key for shop session
        self.key = (userid, channelid)
        self.response = None

        # Cancel any existing sessions
        if self.key in self._sessions:
            self._sessions[self.key].cancel()

        self._event = asyncio.Event()
        self._task = None

        # Add self to the session list
        self._sessions[self.key] = self

    @classmethod
    def get(cls, userid, channelid) -> 'ShopSession':
        """
        Get a ShopSession matching the given key, if it exists.
        Otherwise, returns None.
        """
        return cls._sessions.get((userid, channelid), None)

    async def wait(self, timeout=None):
        """
        Wait for a buy response. Return the set response or raise an appropriate exception.
        """
        self._task = asyncio.create_task(self._event.wait())
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.CancelledError:
            # Session was cancelled, likely due to creation of a new session
            raise
        except asyncio.TimeoutError:
            # Session timed out, likely due to reaching the timeout
            raise
        finally:
            if self._sessions.get(self.key, None) == self:
                self._sessions.pop(self.key, None)

        return self.response

    def set(self, response):
        """
        Set response.
        """
        self.response = response
        self._event.set()

    def cancel(self):
        """
        Cancel a session.
        """
        if self._task:
            if self._sessions.get(self.key, None) == self:
                self._sessions.pop(self.key, None)
            self._task.cancel()
        else:
            raise ValueError("Cancelling a ShopSession that is already completed!")


@module.cmd(
    'shop',
    group="Economy",
    desc="Open the guild shop.",
    flags=('add==', 'remove==', 'clear')
)
@in_guild()
async def cmd_shop(ctx, flags):
    """
    Usage``:
        {prefix}shop
        {prefix}shop --add <price>, <item>
        {prefix}shop --remove
        {prefix}shop --remove itemid, itemid, ...
        {prefix}shop --remove itemname, itemname, ...
        {prefix}shop --clear
    Description:
        Opens the guild shop. Visible items may be bought using `{prefix}buy`.

        *Modifying the guild shop requires administrator permissions.*
    """
    # TODO: (FUTURE) Register session (and cancel previous sessions) so we can track for buy

    # Whether we are modifying the shop
    modifying = any(value is not False for value in flags.values())
    if modifying and not is_guild_admin(ctx.author):
        return await ctx.error_reply(
            "You need to be a guild admin to modify the shop!"
        )

    # Fetch all purchasable elements, this also populates the cache
    shop_items = ShopItem.fetch_where(guildid=ctx.guild.id, deleted=False, purchasable=True)

    if not shop_items and not modifying:
        # TODO: (FUTURE) Add tip for guild admins about setting up
        return await ctx.error_reply(
            "Nothing to buy! Please come back later."
        )

    # Categorise items
    item_cats = defaultdict(list)
    for item in shop_items:
        item_cats[item.item_type].append(item)

    # If there is more than one category, ask for which category they want
    # All FUTURE TODO stuff, to be refactored into a shop widget
    # item_type = None
    # if ctx.args:
    #     # Assume category has been entered
    #     ...
    # elif len(item_cats) > 1:
    #     # TODO: Show selection menu
    #     item_type = ...
    #     ...
    # else:
    #     # Pick the next one automatically
    #     item_type = next(iter(item_cats))

    item_type = ShopItemType.COLOUR_ROLE
    item_class = ColourRole

    if item_type is not None:
        items = [item for item in item_cats[item_type]]
        embeds = item_class.cat_shop_embeds(
            ctx.guild.id,
            [item.itemid for item in items]
        )

        if modifying:
            if flags['add']:
                await item_class.parse_add(ctx, flags['add'])
            elif flags['remove'] is not False:
                await item_class.parse_remove(ctx, flags['remove'], items)
            elif flags['clear']:
                await item_class.parse_clear(ctx)
            return

        # Present shop pages
        out_msg = await ctx.pager(embeds, add_cancel=True)
        await ctx.cancellable(out_msg, add_reaction=False)
        while True:
            try:
                response = await ShopSession(ctx.author.id, ctx.ch.id).wait(timeout=300)
            except asyncio.CancelledError:
                # User opened a new session
                break
            except asyncio.TimeoutError:
                # Session timed out. Close the shop.
                # TODO: (FUTURE) time out shop session by removing hint.
                try:
                    embed = discord.Embed(
                        colour=discord.Colour.red(),
                        description="Shop closed! (Session timed out.)"
                    )
                    await out_msg.edit(
                        embed=embed
                    )
                except discord.HTTPException:
                    pass
                break

            # Selection was made

            # Sanity checks
            # TODO: (FUTURE) Handle more flexible ways of selecting items
            if int(response.args) >= len(items):
                await response.error_reply(
                    "No item with this number exists! Please try again."
                )
                continue

            item = items[int(response.args)]
            if item.price > ctx.alion.coins:
                await response.error_reply(
                    "Sorry, {} costs `{}` LionCoins, but you only have `{}`!".format(
                        item.display_name,
                        item.price,
                        ctx.alion.coins
                    )
                )
                continue

            # Run the selection and keep the shop open in case they want to buy more.
            # TODO: (FUTURE) The item may no longer exist
            success = await item.buy(response)
            if success and not item.allow_multi_select:
                try:
                    await out_msg.delete()
                except discord.HTTPException:
                    pass
                break


@module.cmd(
    'buy',
    group="Hidden",
    desc="Buy an item from the guild shop."
)
@in_guild()
async def cmd_buy(ctx):
    """
    Usage``:
        {prefix}buy <number>
    Description:
        Only usable while you have a shop open (see `{prefix}shop`).

        Buys the selected item from the shop.
    """
    # Check relevant session exists
    session = ShopSession.get(ctx.author.id, ctx.ch.id)
    if session is None:
        return await ctx.error_reply(
            "No shop open, nothing to buy!\n"
            "Please open a shop with `{prefix}shop` first.".format(prefix=ctx.best_prefix)
        )
    # Check input is an integer
    if not ctx.args.isdigit():
        return await ctx.error_reply(
            "**Usage:** `{prefix}buy <number>`, for example `{prefix}buy 1`.".format(prefix=ctx.best_prefix)
        )

    # Pass context back to session
    session.set(ctx)


# TODO: (FUTURE) Buy command short-circuiting the shop command and acting on shop sessions
# TODO: (FUTURE) Inventory command showing the user's purchases

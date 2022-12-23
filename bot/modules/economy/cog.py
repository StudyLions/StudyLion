from typing import Optional, Union
from enum import Enum

import discord
from discord.ext import commands as cmds
from discord import app_commands as appcmds

from psycopg import sql
from data import Registry, RowModel, RegisterEnum, ORDER, JOINTYPE, RawExpr
from data.columns import Integer, Bool, String, Column, Timestamp

from meta import LionCog, LionBot, LionContext
from meta.errors import ResponseTimedOut
from babel import LocalBabel

from core.data import CoreData

from utils.ui import LeoUI, LeoModal, Confirm, Pager
from utils.lib import error_embed, MessageArgs, utc_now

babel = LocalBabel('economy')
_, _p, _np = babel._, babel._p, babel._np


MAX_COINS = 2**16


class TransactionType(Enum):
    """
    Schema
    ------
    CREATE TYPE CoinTransactionType AS ENUM(
        'REFUND',
        'TRANSFER',
        'SHOP_PURCHASE',
        'STUDY_SESSION',
        'ADMIN',
        'TASKS'
    );
    """
    REFUND = 'REFUND',
    TRANSFER = 'TRANSFER',
    PURCHASE = 'SHOP_PURCHASE',
    SESSION = 'STUDY_SESSION',
    ADMIN = 'ADMIN',
    TASKS = 'TASKS',


class AdminActionTarget(Enum):
    """
    Schema
    ------
    CREATE TYPE EconAdminTarget AS ENUM(
        'ROLE',
        'USER',
        'GUILD'
    );
    """
    ROLE = 'ROLE',
    USER = 'USER',
    GUILD = 'GUILD',


class AdminActionType(Enum):
    """
    Schema
    ------
    CREATE TYPE EconAdminAction AS ENUM(
        'SET',
        'ADD'
    );
    """
    SET = 'SET',
    ADD = 'ADD',


class EconomyData(Registry, name='economy'):
    _TransactionType = RegisterEnum(TransactionType, 'CoinTransactionType')
    _AdminActionTarget = RegisterEnum(AdminActionTarget, 'EconAdminTarget')
    _AdminActionType = RegisterEnum(AdminActionType, 'EconAdminAction')

    class Transaction(RowModel):
        """
        Schema
        ------
        CREATE TABLE coin_transactions(
            transactionid SERIAL PRIMARY KEY,
            transactiontype CoinTransactionType NOT NULL,
            guildid BIGINT NOT NULL REFERENCES guild_config (guildid) ON DELETE CASCADE,
            actorid BIGINT NOT NULL,
            amount INTEGER NOT NULL,
            bonus INTEGER NOT NULL,
            from_account BIGINT,
            to_account BIGINT,
            refunds INTEGER REFERENCES coin_transactions (transactionid) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT (now() at time zone 'utc')
        );
        CREATE INDEX coin_transaction_guilds ON coin_transactions (guildid);
        """
        _tablename_ = 'coin_transactions'

        transactionid = Integer(primary=True)
        transactiontype: Column[TransactionType] = Column()
        guildid = Integer()
        actorid = Integer()
        amount = Integer()
        bonus = Integer()
        from_account = Integer()
        to_account = Integer()
        refunds = Integer()
        created_at = Timestamp()

        @classmethod
        async def execute_transaction(
            cls,
            transaction_type: TransactionType,
            guildid: int, actorid: int,
            from_account: int, to_account: int, amount: int, bonus: int = 0,
            refunds: int = None
        ):
            transaction = await cls.create(
                transactiontype=transaction_type,
                guildid=guildid, actorid=actorid, amount=amount, bonus=bonus,
                from_account=from_account, to_account=to_account,
                refunds=refunds
            )
            if from_account is not None:
                await CoreData.Member.table.update_where(
                    guildid=guildid, userid=from_account
                ).set(coins=(CoreData.Member.coins - (amount + bonus)))
            if to_account is not None:
                await CoreData.Member.table.update_where(
                    guildid=guildid, userid=to_account
                ).set(coins=(CoreData.Member.coins + (amount + bonus)))
            return transaction

    class ShopTransaction(RowModel):
        """
        Schema
        ------
        CREATE TABLE coin_transactions_shop(
            transactionid INTEGER PRIMARY KEY REFERENCES coin_transactions (transactionid) ON DELETE CASCADE,
            itemid INTEGER NOT NULL REFERENCES shop_items (itemid) ON DELETE CASCADE
        );
        """
        _tablename_ = 'coin_transactions_shop'

        transactionid = Integer(primary=True)
        itemid = Integer()

        @classmethod
        async def purchase_transaction(
            cls,
            guildid: int, actorid: int,
            userid: int, itemid: int, amount: int
        ):
            conn = await cls._connector.get_connection()
            async with conn.transaction():
                row = await EconomyData.Transaction.execute_transaction(
                    TransactionType.PURCHASE,
                    guildid=guildid, actorid=actorid, from_account=userid, to_account=None,
                    amount=amount
                )
                return await cls.create(transactionid=row.transactionid, itemid=itemid)

    class TaskTransaction(RowModel):
        """
        Schema
        ------
        CREATE TABLE coin_transactions_tasks(
            transactionid INTEGER PRIMARY KEY REFERENCES coin_transactions (transactionid) ON DELETE CASCADE,
            count INTEGER NOT NULL
        );
        """
        _tablename_ = 'coin_transactions_tasks'

        transactionid = Integer(primary=True)
        count = Integer()

        @classmethod
        async def count_recent_for(cls, userid, guildid, interval='24h'):
            """
            Retrieve the number of tasks rewarded in the last `interval`.
            """
            T = EconomyData.Transaction
            query = cls.table.select_where().with_no_adapter()
            query.join(T, using=(T.transactionid.name, ), join_type=JOINTYPE.LEFT)
            query.select(recent=sql.SQL("SUM({})").format(cls.count.expr))
            query.where(
                T.to_account == userid,
                T.guildid == guildid,
                T.created_at > RawExpr(sql.SQL("timezone('utc', NOW()) - INTERVAL {}").format(interval), ()),
            )
            result = await query
            return result[0]['recent'] or 0

        @classmethod
        async def reward_completed(cls, userid, guildid, count, amount):
            """
            Reward the specified member `amount` coins for completing `count` tasks.
            """
            # TODO: Bonus logic, perhaps apply_bonus(amount), or put this method in the economy cog?
            conn = await cls._connector.get_connection()
            async with conn.transaction():
                row = await EconomyData.Transaction.execute_transaction(
                    TransactionType.TASKS,
                    guildid=guildid, actorid=userid, from_account=None, to_account=userid,
                    amount=amount
                )
                return await cls.create(transactionid=row.transactionid, count=count)

    class SessionTransaction(RowModel):
        """
        Schema
        ------
        CREATE TABLE coin_transactions_sessions(
            transactionid INTEGER PRIMARY KEY REFERENCES coin_transactions (transactionid) ON DELETE CASCADE,
            sessionid INTEGER NOT NULL REFERENCES session_history (sessionid) ON DELETE CASCADE
        );
        """
        _tablename_ = 'coin_transactions_sessions'

        transactionid = Integer(primary=True)
        sessionid = Integer()

    class AdminActions(RowModel):
        """
        Schema
        ------
        CREATE TABLE economy_admin_actions(
            actionid SERIAL PRIMARY KEY,
            target_type EconAdminTarget NOT NULL,
            action_type EconAdminAction NOT NULL,
            targetid INTEGER NOT NULL,
            amount INTEGER NOT NULL
        );
        """
        _tablename_ = 'economy_admin_actions'

        actionid = Integer(primary=True)
        target_type: Column[AdminActionTarget] = Column()
        action_type: Column[AdminActionType] = Column()
        targetid = Integer()
        amount = Integer()

    class AdminTransactions(RowModel):
        """
        Schema
        ------
        CREATE TABLE coin_transactions_admin_actions(
            actionid INTEGER NOT NULL REFERENCES economy_admin_actions (actionid),
            transactionid INTEGER NOT NULL REFERENCES coin_transactions (transactionid),
            PRIMARY KEY (actionid, transactionid)
        );
        CREATE INDEX coin_transactions_admin_actions_transactionid ON coin_transactions_admin_actions (transactionid);
        """
        _tablename_ = 'coin_transactions_admin_actions'

        actionid = Integer(primary=True)
        transactionid = Integer(primary=True)


class Economy(LionCog):
    """
    Commands
    --------
    /economy balances [target:<mentionable>] [add:<int>] [set:<int>].
        With no arguments, show a summary of current balances in the server.
        With a target user or role, show their balance, and possibly their most recent transactions.
        With a target user or role, and add or set, modify their balance. Confirm if more than 1 user is affected.
        With no target user or role, apply to everyone in the guild. Confirm if more than 1 user affected.

    /economy reset [target:<mentionable>]
        Reset the economy system for the given target, or everyone in the guild.
        Acts as an alias to `/economy balances target:target set:0

    /economy history [target:<mentionable>]
        Display a paged audit trail with the history of the selected member,
        all the users in the selected role, or all users.

    /sendcoins <user:<user>> [note:<str>]
        Send coins to the specified user, with an optional note.
    """
    def __init__(self, bot: LionBot):
        self.bot = bot
        self.data = bot.db.load_registry(EconomyData())

    async def cog_load(self):
        await self.data.init()

    # ----- Economy group commands -----

    @cmds.hybrid_group(name=_p('cmd:economy', "economy"))
    @cmds.guild_only()
    async def economy_group(self, ctx: LionContext):
        pass

    @economy_group.command(
        name=_p('cmd:economy_balance', "balance"),
        description=_p(
            'cmd:economy_balance|desc',
            "Display and modify LionCoin balance for members or roles."
        )
    )
    @appcmds.rename(
        target=_p('cmd:economy_balance|param:target', "target"),
        add=_p('cmd:economy_balance|param:add', "add"),
        set_to=_p('cmd:economy_balance|param:set', "set")
    )
    @appcmds.describe(
        target=_p(
            'cmd:economy_balance|param:target|desc',
            "Target user or role to view or update. Use @everyone to update the entire guild."
        ),
        add=_p(
            'cmd:economy_balance|param:add|desc',
            "Number of LionCoins to add to the target member's balance. May be negative to remove."
        ),
        set_to=_p(
            'cmd:economy_balance|param:set|set',
            "New balance to set the target's balance to."
        )
    )
    async def economy_balance_cmd(
        self,
        ctx: LionContext,
        target: discord.User | discord.Member | discord.Role,
        set_to: Optional[appcmds.Range[int, 0, MAX_COINS]] = None,
        add: Optional[int] = None
    ):
        t = self.bot.translator.t
        cemoji = self.bot.config.emojis.getemoji('coin')
        targets: list[Union[discord.User, discord.Member]]

        if not ctx.guild:
            # Added for the typechecker
            # This is impossible from the guild_only ward
            return
        if not self.bot.core:
            return
        if not ctx.interaction:
            return

        if isinstance(target, discord.Role):
            targets = [mem for mem in target.members if not mem.bot]
            role = target
        else:
            targets = [target]
            role = None

        if role and not targets:
            # Guard against provided target role having no members
            # Possible chunking failed for this guild, want to explicitly inform.
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:economy_balance|error:no_target',
                        "There are no valid members in {role.mention}! It has a total of `0` LC."
                    )).format(role=target)
                ),
                ephemeral=True
            )
        elif not role and target.bot:
            # Guard against reading or modifying a bot account
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:economy_balance|error:target_is_bot',
                        "Bots cannot have coin balances!"
                    ))
                ),
                ephemeral=True
            )
        elif set_to is not None and add is not None:
            # Requested operation doesn't make sense
            await ctx.reply(
                embed=error_embed(
                    t(_p(
                        'cmd:economy_balance|error:args',
                        "You cannot simultaneously `set` and `add` member balances!"
                    ))
                ),
                ephemeral=True
            )
        elif set_to is not None or add is not None:
            # Setting route
            # First ensure all the targets we will be updating already have rows
            # As this is one of the few operations that acts on members not already registered,
            # We may need to do a mass row create operation.
            targetids = set(target.id for target in targets)
            if len(targets) > 1:
                conn = await ctx.bot.db.get_connection()
                async with conn.transaction():
                    # First fetch the members which currently exist
                    query = self.bot.core.data.Member.table.select_where(guildid=ctx.guild.id)
                    query.select('userid').with_no_adapter()
                    if 2 * len(targets) < len(ctx.guild.members):
                        # More efficient to fetch the targets explicitly
                        query.where(userid=list(targetids))
                    existent_rows = await query
                    existentids = set(r['userid'] for r in existent_rows)

                    # Then check if any new userids need adding, and if so create them
                    new_ids = targetids.difference(existentids)
                    if new_ids:
                        # We use ON CONFLICT IGNORE here in case the users already exist.
                        await self.bot.core.data.User.table.insert_many(
                            ('userid',),
                            *((id,) for id in new_ids)
                        ).on_conflict(ignore=True)
                        # TODO: Replace 0 here with the starting_coin value
                        await self.bot.core.data.Member.table.insert_many(
                            ('guildid', 'userid', 'coins'),
                            *((ctx.guild.id, id, 0) for id in new_ids)
                        ).on_conflict(ignore=True)
            else:
                # With only one target, we can take a simpler path, and make better use of local caches.
                await self.bot.core.lions.fetch(ctx.guild.id, target.id)
            # Now we are certain these members have a database row

            # Perform the appropriate action
            if role:
                affected = t(_np(
                    'cmd:economy_balance|embed:success|affected',
                    "One user was affected.",
                    "**{count}** users were affected.",
                    len(targets)
                )).format(count=len(targets))
                conf_affected = t(_np(
                    'cmd:economy_balance|confirm|affected',
                    "One user will be affected.",
                    "**{count}** users will be affected.",
                    len(targets)
                )).format(count=len(targets))
                confirm = Confirm(conf_affected)
                confirm.confirm_button = t(_p(
                    'cmd:economy_balance|confirm|button:confirm',
                    "Yes, adjust balances"
                ))
                confirm.confirm_button = t(_p(
                    'cmd:economy_balance|confirm|button:cancel',
                    "No, cancel"
                ))
            if set_to is not None:
                if role:
                    if role.is_default():
                        description = t(_p(
                            'cmd:economy_balance|embed:success_set|desc',
                            "All members of **{guild_name}** have had their "
                            "balance set to {coin_emoji}**{amount}**."
                        )).format(
                            guild_name=ctx.guild.name,
                            coin_emoji=cemoji,
                            amount=set_to
                        ) + '\n' + affected
                        conf_description = t(_p(
                            'cmd:economy_balance|confirm_set|desc',
                            "Are you sure you want to set everyone's balance to {coin_emoji}**{amount}**?"
                        )).format(
                            coin_emoji=cemoji,
                            amount=set_to
                        ) + '\n' + conf_affected
                    else:
                        description = t(_p(
                            'cmd:economy_balance|embed:success_set|desc',
                            "All members of {role_mention} have had their "
                            "balance set to {coin_emoji}**{amount}**."
                        )).format(
                            role_mention=role.mention,
                            coin_emoji=cemoji,
                            amount=set_to
                        ) + '\n' + affected
                        conf_description = t(_p(
                            'cmd:economy_balance|confirm_set|desc',
                            "Are you sure you want to set the balance of everyone with {role_mention} "
                            "to {coin_emoji}**{amount}**?"
                        )).format(
                            role_mention=role.mention,
                            coin_emoji=cemoji,
                            amount=set_to
                        ) + '\n' + conf_affected
                    confirm.embed.description = conf_description
                    try:
                        result = await confirm.ask(ctx.interaction, ephemeral=True)
                    except ResponseTimedOut:
                        return
                    if not result:
                        return
                else:
                    description = t(_p(
                        'cmd:economy_balance|embed:success_set|desc',
                        "{user_mention} now has a balance of {coin_emoji}**{amount}**."
                    )).format(
                        user_mention=target.mention,
                        coin_emoji=cemoji,
                        amount=set_to
                    )
                await self.bot.core.data.Member.table.update_where(
                    guildid=ctx.guild.id, userid=list(targetids)
                ).set(
                    coins=set_to
                )
            else:
                if role:
                    if role.is_default():
                        description = t(_p(
                            'cmd:economy_balance|embed:success_add|desc',
                            "All members of **{guild_name}** have been given "
                            "{coin_emoji}**{amount}**."
                        )).format(
                            guild_name=ctx.guild.name,
                            coin_emoji=cemoji,
                            amount=add
                        ) + '\n' + affected
                        conf_description = t(_p(
                            'cmd:economy_balance|confirm_add|desc',
                            "Are you sure you want to add **{amount}** to everyone's balance?"
                        )).format(
                            coin_emoji=cemoji,
                            amount=add
                        ) + '\n' + conf_affected
                    else:
                        description = t(_p(
                            'cmd:economy_balance|embed:success_add|desc',
                            "All members of {role_mention} have been given "
                            "{coin_emoji}**{amount}**."
                        )).format(
                            role_mention=role.mention,
                            coin_emoji=cemoji,
                            amount=add
                        ) + '\n' + affected
                        conf_description = t(_p(
                            'cmd:economy_balance|confirm_add|desc',
                            "Are you sure you want to add {coin_emoji}**{amount}** to everyone in {role_mention}?"
                        )).format(
                            coin_emoji=cemoji,
                            amount=add,
                            role_mention=role.mention
                        ) + '\n' + conf_affected
                    confirm.embed.description = conf_description
                    try:
                        result = await confirm.ask(ctx.interaction, ephemeral=True)
                    except ResponseTimedOut:
                        return
                    if not result:
                        return
                results = await self.bot.core.data.Member.table.update_where(
                    guildid=ctx.guild.id, userid=list(targetids)
                ).set(
                    coins=(self.bot.core.data.Member.coins + add)
                )
                # Single member case occurs afterwards so we can pick up the results
                if not role:
                    description = t(_p(
                        'cmd:economy_balance|embed:success_add|desc',
                        "{user_mention} was given {coin_emoji}**{amount}**, and "
                        "now has a balance of {coin_emoji}**{new_amount}**."
                    )).format(
                        user_mention=target.mention,
                        coin_emoji=cemoji,
                        amount=add,
                        new_amount=results[0]['coins']
                    )

            title = t(_np(
                'cmd:economy_balance|embed:success|title',
                "Account successfully updated.",
                "Accounts successfully updated.",
                len(targets)
            ))
            await ctx.reply(
                embed=discord.Embed(
                    colour=discord.Colour.brand_green(),
                    description=description,
                    title=title,
                )
            )
        else:
            # Viewing route
            MemModel = self.bot.core.data.Member
            if role:
                query = MemModel.fetch_where(
                    (MemModel.guildid == role.guild.id) & (MemModel.coins != 0)
                )
                query.order_by('coins', ORDER.DESC)
                if not role.is_default():
                    # Everyone role is handled differently for data efficiency
                    ids = [target.id for target in targets]
                    query = query.where(userid=ids)
                rows = await query

                name = t(_p(
                    'cmd:economy_balance|embed:role_lb|author',
                    "Balance sheet for {name}"
                )).format(name=role.name if not role.is_default() else role.guild.name)
                if rows:
                    if role.is_default():
                        header = t(_p(
                            'cmd:economy_balance|embed:role_lb|header',
                            "This server has a total balance of {coin_emoji}**{total}**."
                        )).format(
                            coin_emoji=cemoji,
                            total=sum(row.coins for row in rows)
                        )
                    else:
                        header = t(_p(
                            'cmd:economy_balance|embed:role_lb|header',
                            "{role_mention} has `{count}` members with non-zero balance, "
                            "with a total balance of {coin_emoji}**{total}**."
                        )).format(
                            count=len(targets),
                            role_mention=role.mention,
                            total=sum(row.coins for row in rows),
                            coin_emoji=cemoji
                        )

                    # Build the leaderboard:
                    lb_format = t(_p(
                        'cmd:economy_balance|embed:role_lb|row_format',
                        "`[{pos:>{numwidth}}]` | `{coins:>{coinwidth}} LC` | {mention}"
                    ))

                    blocklen = 20
                    blocks = [rows[i:i+blocklen] for i in range(0, len(rows), blocklen)]
                    paged = len(blocks) > 1
                    pages = []
                    for i, block in enumerate(blocks):
                        lines = []
                        numwidth = len(str(i + len(block)))
                        coinwidth = len(str(max(row.coins for row in rows)))
                        for j, row in enumerate(block, start=i):
                            lines.append(
                                lb_format.format(
                                    pos=j, numwidth=numwidth,
                                    coins=row.coins, coinwidth=coinwidth,
                                    mention=f"<@{row.userid}>"
                                )
                            )
                        lb_block = '\n'.join(lines)
                        embed = discord.Embed(
                            description=f"{header}\n{lb_block}"
                        )
                        embed.set_author(name=name)
                        if paged:
                            embed.set_footer(
                                text=t(_p(
                                    'cmd:economy_balance|embed:role_lb|footer',
                                    "Page {page}/{total}"
                                )).format(page=i+1, total=len(blocks))
                            )
                        pages.append(MessageArgs(embed=embed))
                    pager = Pager(pages, show_cancel=True)
                    await pager.run(ctx.interaction)
                else:
                    if role.is_default():
                        header = t(_p(
                            'cmd:economy_balance|embed:role_lb|header',
                            "This server has a total balance of {coin_emoji}**0**."
                        )).format(
                            coin_emoji=cemoji,
                        )
                    else:
                        header = t(_p(
                            'cmd:economy_balance|embed:role_lb|header',
                            "The role {role_mention} has a total balance of {coin_emoji}**0**."
                        )).format(
                            role_mention=role.mention,
                            coin_emoji=cemoji
                        )
                    embed = discord.Embed(
                        colour=discord.Colour.orange(),
                        description=header
                    )
                    embed.set_author(name=name)
                    await ctx.reply(embed=embed)
            else:
                # If we have a single target, show their current balance, with a short transaction history.
                user = targets[0]
                row = await self.bot.core.data.Member.fetch(ctx.guild.id, user.id)

                embed = discord.Embed(
                    colour=discord.Colour.orange(),
                    description=t(_p(
                        'cmd:economy_balance|embed:single|desc',
                        "{mention} currently owns {coin_emoji} {coins}."
                    )).format(
                        mention=user.mention,
                        coin_emoji=self.bot.config.emojis.getemoji('coin'),
                        coins=row.coins
                    )
                ).set_author(
                    icon_url=user.avatar,
                    name=t(_p(
                        'cmd:economy_balance|embed:single|author',
                        "Balance statement for {user}"
                    )).format(user=str(user))
                )
                await ctx.reply(
                    embed=embed
                )
                # TODO: Add small transaction history block when we have transaction formatter

    @economy_group.command(
        name=_p('cmd:economy_reset', "reset"),
        description=_p(
            'cmd:economy_reset|desc',
            "Reset the coin balance for a target user or role. (See also \"economy balance\".)"
        )
    )
    @appcmds.rename(
        target=_p('cmd:economy_reset|param:target', "target"),
    )
    @appcmds.describe(
        target=_p(
            'cmd:economy_reset|param:target|desc',
            "Target user or role to view or update. Use @everyone to reset the entire guild."
        ),
    )
    async def economy_reset_cmd(
        self,
        ctx: LionContext,
        target: discord.User | discord.Member | discord.Role,
    ):
        # TODO: Permission check
        t = self.bot.translator.t
        starting_balance = 0
        coin_emoji = self.bot.config.emojis.getemoji('coin')

        # Typechecker guards
        if not ctx.guild:
            return
        if not ctx.bot.core:
            return
        if not ctx.interaction:
            return

        if isinstance(target, discord.Role):
            if target.is_default():
                # Confirm: Reset Guild
                confirm_msg = t(_p(
                    'cmd:economy_reset|confirm:reset_guild|desc',
                    "Are you sure you want to reset the coin balance for everyone in **{guild_name}**?\n"
                    "*This is not reversible!*"
                )).format(
                    guild_name=ctx.guild.name
                )
                confirm = Confirm(confirm_msg)
                confirm.confirm_button.label = t(_p(
                    'cmd:economy_reset|confirm:reset_guild|button:confirm',
                    "Yes, reset the economy"
                ))
                confirm.cancel_button.label = t(_p(
                    'cmd:economy_reset|confirm:reset_guild|button:cancel',
                    "Cancel reset"
                ))
                try:
                    result = await confirm.ask(ctx.interaction, ephemeral=True)
                except ResponseTimedOut:
                    return

                if result:
                    # Complete reset
                    await ctx.bot.core.data.Member.table.update_where(
                        guildid=ctx.guild.id,
                    ).set(coins=starting_balance)
                    await ctx.reply(
                        embed=discord.Embed(
                            description=t(_p(
                                'cmd:economy_reset|embed:success_guild|desc',
                                "Everyone in **{guild_name}** has had their balance reset to {coin_emoji}**{amount}**."
                            )).format(
                                guild_name=ctx.guild.name,
                                coin_emoji=coin_emoji,
                                amount=starting_balance
                            )
                        )
                    )
            else:
                # Provided a role to reset
                targets = [member for member in target.members if not member.bot]
                if not targets:
                    # Error: No targets
                    await ctx.reply(
                        embed=error_embed(
                            t(_p(
                                'cmd:economy_reset|error:no_target|desc',
                                "The role {mention} has no members to reset!"
                            )).format(mention=target.mention)
                        ),
                        ephemeral=True
                    )
                else:
                    # Confirm: Reset Role
                    # Include number of people affected
                    confirm_msg = t(_p(
                        'cmd:economy_reset|confirm:reset_role|desc',
                        "Are you sure you want to reset the balance for everyone in {mention}?\n"
                        "**{count}** members will be affected."
                    )).format(
                        mention=target.mention,
                        count=len(targets)
                    )
                    confirm = Confirm(confirm_msg)
                    confirm.confirm_button.label = t(_p(
                        'cmd:economy_reset|confirm:reset_role|button:confirm',
                        "Yes, complete economy reset"
                    ))
                    confirm.cancel_button.label = t(_p(
                        'cmd:economy_reset|confirm:reset_role|button:cancel',
                        "Cancel"
                    ))
                    try:
                        result = await confirm.ask(ctx.interaction, ephemeral=True)
                    except ResponseTimedOut:
                        return

                    if result:
                        # Complete reset
                        await ctx.bot.core.data.Member.table.update_where(
                            guildid=ctx.guild.id,
                            userid=[t.id for t in targets],
                        ).set(coins=starting_balance)
                        await ctx.reply(
                            embed=discord.Embed(
                                description=t(_p(
                                    'cmd:economy_reset|embed:success_role|desc',
                                    "Everyone in {role_mention} has had their "
                                    "coin balance reset to {coin_emoji}**{amount}**."
                                )).format(
                                    mention=target.mention,
                                    coin_emoji=coin_emoji,
                                    amount=starting_balance
                                )
                            )
                        )
        else:
            # Provided an individual user.
            # Reset their balance
            # Do not create the member row if it does not already exist.
            # TODO: Audit logging trail
            await ctx.bot.core.data.Member.table.update_where(
                guuildid=ctx.guild.id,
                userid=target.id,
            ).set(coins=starting_balance)
            await ctx.reply(
                embed=discord.Embed(
                    description=t(_p(
                        'cmd:economy_reset|embed:success_user|desc',
                        "{mention}'s balance has been reset to {coin_emoji}**{amount}**."
                    )).format(
                        mention=target.mention,
                        coin_emoji=coin_emoji,
                        amount=starting_balance
                    )
                )
            )

    @cmds.hybrid_command(
        name=_p('cmd:send', "send"),
        description=_p(
            'cmd:send|desc',
            "Gift the target user a certain number of LionCoins."
        )
    )
    @appcmds.rename(
        target=_p('cmd:send|param:target', "target"),
        amount=_p('cmd:send|param:amount', "amount"),
        note=_p('cmd:send|param:note', "note")
    )
    @appcmds.describe(
        target=_p('cmd:send|param:target|desc', "User to send the gift to"),
        amount=_p('cmd:send|param:amount|desc', "Number of coins to send"),
        note=_p('cmd:send|param:note|desc', "Optional note to add to the gift.")
    )
    @appcmds.guild_only()
    async def send_cmd(self, ctx: LionContext,
                       target: discord.User | discord.Member,
                       amount: appcmds.Range[int, 1, MAX_COINS],
                       note: Optional[str] = None):
        """
        Send `amount` lioncoins to the provided `target`, with the optional `note` attached.
        """
        if not ctx.interaction:
            return
        if not ctx.guild:
            return
        if not self.bot.core:
            return

        t = self.bot.translator.t
        Member = self.bot.core.data.Member
        target_lion = await self.bot.core.lions.fetch(ctx.guild.id, target.id)

        # TODO: Add a "Send thanks" button to the DM?
        # Alternative flow could be waiting until the target user presses accept
        await ctx.interaction.response.defer(thinking=True, ephemeral=True)

        conn = await self.bot.db.get_connection()
        async with conn.transaction():
            # We do this in a transaction so that if something goes wrong,
            # the coins deduction is rolled back atomicly
            balance = ctx.alion.data.coins
            if amount > balance:
                await ctx.interaction.edit_original_response(
                    embed=error_embed(
                        t(_p(
                            'cmd:send|error:insufficient',
                            "You do not have enough lioncoins to do this!\n"
                            "`Current Balance:` {coin_emoji}{balance}"
                        )).format(
                            coin_emoji=self.bot.config.emojis.getemoji('coin'),
                            balance=balance
                        )
                    ),
                )
                return

            # Transfer the coins
            await ctx.alion.data.update(coins=(Member.coins - amount))
            await target_lion.data.update(coins=(Member.coins + amount))

            # TODO: Audit trail

        # Message target
        embed = discord.Embed(
            title=t(_p(
                'cmd:send|embed:gift|title',
                "{user} sent you a gift!"
            )).format(user=ctx.author.name),
            description=t(_p(
                'cmd:send|embed:gift|desc',
                "{mention} sent you {coin_emoji}**{amount}**."
            )).format(
                coin_emoji=self.bot.config.emojis.getemoji('coin'),
                amount=amount,
                mention=ctx.author.mention
            ),
            timestamp=utc_now()
        )
        if note:
            embed.add_field(
                name="Note Attached",
                value=note
            )
        try:
            await target.send(embed=embed)
            failed = False
        except discord.HTTPException:
            failed = True
            pass

        # Ack transfer
        embed = discord.Embed(
            colour=discord.Colour.brand_green(),
            description=t(_p(
                'cmd:send|embed:ack|desc',
                "**{coin_emoji}{amount}** has been deducted from your balance and sent to {mention}!"
            )).format(
                coin_emoji=self.bot.config.emojis.getemoji('coin'),
                amount=amount,
                mention=target.mention
            )
        )
        if failed:
            embed.description = t(_p(
                'cmd:send|embed:ack|desc|error:unreachable',
                "Unfortunately, I was not able to message the recipient. Perhaps they have me blocked?"
            ))
        await ctx.interaction.edit_original_response(embed=embed)

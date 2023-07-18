from enum import Enum

from psycopg import sql
from data import Registry, RowModel, RegisterEnum, JOINTYPE, RawExpr
from data.columns import Integer, Bool, Column, Timestamp
from core.data import CoreData
from utils.data import TemporaryTable, SAFECOINS


class TransactionType(Enum):
    """
    Schema
    ------
    CREATE TYPE CoinTransactionType AS ENUM(
      'REFUND',
      'TRANSFER',
      'SHOP_PURCHASE',
      'VOICE_SESSION',
      'TEXT_SESSION',
      'ADMIN',
      'TASKS',
      'SCHEDULE_BOOK',
      'SCHEDULE_REWARD',
      'OTHER'
    );
    """
    REFUND = 'REFUND',
    TRANSFER = 'TRANSFER',
    SHOP_PURCHASE = 'SHOP_PURCHASE',
    VOICE_SESSION = 'VOICE_SESSION',
    TEXT_SESSION = 'TEXT_SESSION',
    ADMIN = 'ADMIN',
    TASKS = 'TASKS',
    SCHEDULE_BOOK = 'SCHEDULE_BOOK',
    SCHEDULE_REWARD = 'SCHEDULE_REWARD',
    OTHER = 'OTHER',


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
            conn = await cls._connector.get_connection()
            async with conn.transaction():
                transaction = await cls.create(
                    transactiontype=transaction_type,
                    guildid=guildid, actorid=actorid, amount=amount, bonus=bonus,
                    from_account=from_account, to_account=to_account,
                    refunds=refunds
                )
                if from_account is not None:
                    await CoreData.Member.table.update_where(
                        guildid=guildid, userid=from_account
                    ).set(coins=SAFECOINS(CoreData.Member.coins - (amount + bonus)))
                if to_account is not None:
                    await CoreData.Member.table.update_where(
                        guildid=guildid, userid=to_account
                    ).set(coins=SAFECOINS(CoreData.Member.coins + (amount + bonus)))
                return transaction

        @classmethod
        async def execute_transactions(cls, *transactions):
            """
            Execute multiple transactions in one data transaction.

            Writes the transaction and updates the affected member accounts.
            Returns the created Transactions.

            Arguments
            ---------
            transactions: tuple[TransactionType, int, int, int, int, int, int, int]
                (transaction_type, guildid, actorid, from_account, to_account, amount, bonus, refunds)
            """
            if not transactions:
                return []

            conn = await cls._connector.get_connection()
            async with conn.transaction():
                # Create the transactions
                rows = await cls.table.insert_many(
                    (
                        'transactiontype',
                        'guildid', 'actorid',
                        'from_account', 'to_account',
                        'amount', 'bonus',
                        'refunds'
                    ),
                    *transactions
                ).with_adapter(cls._make_rows)

                # Update the members
                transtable = TemporaryTable(
                    '_guildid', '_userid', '_amount',
                    types=('BIGINT', 'BIGINT', 'INTEGER')
                )
                values = transtable.values
                for transaction in transactions:
                    _, guildid, _, from_acc, to_acc, amount, bonus, _ = transaction
                    coins = amount + bonus
                    if coins:
                        if from_acc:
                            values.append((guildid, from_acc, -1 * coins))
                        if to_acc:
                            values.append((guildid, to_acc, coins))
                if values:
                    Member = CoreData.Member
                    await Member.table.update_where(
                        guildid=transtable['_guildid'], userid=transtable['_userid']
                    ).set(
                        coins=SAFECOINS(Member.coins + transtable['_amount'])
                    ).from_expr(transtable)
            return rows

        @classmethod
        async def refund_transactions(cls, *transactionids, actorid=0):
            if not transactionids:
                return []
            conn = await cls._connector.get_connection()
            async with conn.transaction():
                # First fetch the transaction rows to refund
                data = await cls.table.select_where(transactionid=transactionids)
                if data:
                    # Build the transaction refund data
                    records = [
                        (
                            TransactionType.REFUND,
                            tr['guildid'], actorid,
                            tr['to_account'], tr['from_account'],
                            tr['amount'] + tr['bonus'], 0,
                            tr['transactionid']
                        )
                        for tr in data
                    ]
                    # Execute refund transactions
                    return await cls.execute_transactions(*records)

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
                    TransactionType.SHOP_PURCHASE,
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

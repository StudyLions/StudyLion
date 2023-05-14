from enum import Enum

from psycopg import sql
from data import Registry, RowModel, RegisterEnum, JOINTYPE, RawExpr
from data.columns import Integer, Bool, Column, Timestamp

from core.data import CoreData


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

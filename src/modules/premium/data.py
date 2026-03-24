from enum import Enum

from psycopg import sql
from meta.logger import log_wrap
from data import Registry, RowModel, RegisterEnum, Table
from data.columns import Integer, Bool, Column, Timestamp, String


class GemTransactionType(Enum):
    """
    Schema
    ------
    CREATE TYPE GemTransactionType AS ENUM (
      'ADMIN',
      'GIFT',
      'PURCHASE',
      'AUTOMATIC'
    );
    """
    ADMIN = 'ADMIN',
    GIFT = 'GIFT',
    PURCHASE = 'PURCHASE',
    AUTOMATIC = 'AUTOMATIC',


class PremiumData(Registry):
    GemTransactionType = RegisterEnum(GemTransactionType, 'GemTransactionType')

    class GemTransaction(RowModel):
        """
        Schema
        ------

        CREATE TABLE gem_transactions(
          transactionid SERIAL PRIMARY KEY,
          transaction_type GemTransactionType NOT NULL,
          actorid BIGINT NOT NULL,
          from_account BIGINT,
          to_account BIGINT,
          amount INTEGER NOT NULL,
          description TEXT NOT NULL,
          note TEXT,
          reference TEXT,
          _timestamp TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX gem_transactions_from ON gem_transactions (from_account);
        """
        _tablename_ = 'gem_transactions'

        transactionid = Integer(primary=True)
        transaction_type: Column[GemTransactionType] = Column()
        actorid = Integer()
        from_account = Integer()
        to_account = Integer()
        amount = Integer()
        description = String()
        note = String()
        reference = String()

        _timestamp = Timestamp()

    class PremiumGuild(RowModel):
        """
        Schema
        ------
        CREATE TABLE premium_guilds(
          guildid BIGINT PRIMARY KEY REFERENCES guild_config,
          premium_since TIMESTAMPTZ NOT NULL DEFAULT now(),
          premium_until TIMESTAMPTZ NOT NULL DEFAULT now(),
          custom_skin_id INTEGER REFERENCES customised_skins
        );
        """
        _tablename_ = "premium_guilds"
        _cache_ = {}

        guildid = Integer(primary=True)
        premium_since = Timestamp()
        premium_until = Timestamp()
        custom_skin_id = Integer()

    # --- AI-MODIFIED (2026-03-16) ---
    # Purpose: LionHeart subscription tier tracking model
    class UserSubscription(RowModel):
        _tablename_ = 'user_subscriptions'
        _cache_ = {}
        userid = Integer(primary=True)
        stripe_customer_id = String()
        stripe_subscription_id = String()
        tier = String()
        status = String()
        current_period_start = Timestamp()
        current_period_end = Timestamp()
        created_at = Timestamp()
        updated_at = Timestamp()
    # --- END AI-MODIFIED ---

    """
    CREATE TABLE premium_guild_contributions(
      contributionid SERIAL PRIMARY KEY,
      userid BIGINT NOT NULL REFERENCES user_config,
      guildid BIGINT NOT NULL REFERENCES premium_guilds,
      transactionid INTEGER REFERENCES gem_transactions,
      duration INTEGER NOT NULL,
      _timestamp TIMESTAMPTZ DEFAULT now()
    );
    """
    premium_guild_contributions = Table('premium_guild_contributions')


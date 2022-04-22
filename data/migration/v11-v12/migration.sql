-- Add gem support
ALTER TABLE user_config ADD COLUMN gems INTEGER DEFAULT 0;

-- LionGem audit log {{{
CREATE TYPE GemTransactionType AS ENUM (
  'ADMIN',
  'GIFT',
  'PURCHASE',
  'AUTOMATIC'
);

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
-- }}}

INSERT INTO VersionHistory (version, author) VALUES (12, 'v11-v12 migration');

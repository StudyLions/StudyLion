-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-16
-- Purpose: Migration v15 -> v16
--          Add user_subscriptions table for LionHeart
--          Stripe subscription tiers
-- ============================================================

-- User Subscriptions (LionHeart tiers via Stripe)
CREATE TABLE IF NOT EXISTS user_subscriptions(
  userid BIGINT PRIMARY KEY,
  stripe_customer_id TEXT NOT NULL,
  stripe_subscription_id TEXT,
  tier TEXT NOT NULL DEFAULT 'NONE',
  status TEXT NOT NULL DEFAULT 'INACTIVE',
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_subscriptions_stripe_customer ON user_subscriptions (stripe_customer_id);

-- Note: data_version is tracked in app config, not in this SQL file

-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Marketplace tables for LionGotchi trading system
-- ============================================================

-- Add new transaction types for marketplace
ALTER TYPE lggoldtransactiontype ADD VALUE IF NOT EXISTS 'MARKETPLACE_SALE';
ALTER TYPE lggoldtransactiontype ADD VALUE IF NOT EXISTS 'MARKETPLACE_PURCHASE';

-- Marketplace listings
CREATE TABLE IF NOT EXISTS lg_marketplace_listings (
  listingid         SERIAL PRIMARY KEY,
  seller_userid     BIGINT NOT NULL,
  itemid            INTEGER NOT NULL REFERENCES lg_items(itemid),
  enhancement_level INTEGER NOT NULL DEFAULT 0,
  quantity_listed   INTEGER NOT NULL,
  quantity_remaining INTEGER NOT NULL,
  price_per_unit    INTEGER NOT NULL,
  currency          TEXT NOT NULL DEFAULT 'GOLD',
  status            TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at        TIMESTAMPTZ NOT NULL,
  CONSTRAINT chk_mp_currency CHECK (currency IN ('GOLD', 'GEMS')),
  CONSTRAINT chk_mp_status CHECK (status IN ('ACTIVE', 'SOLD', 'CANCELLED', 'EXPIRED'))
);

CREATE INDEX IF NOT EXISTS idx_mp_listings_status ON lg_marketplace_listings(status);
CREATE INDEX IF NOT EXISTS idx_mp_listings_itemid ON lg_marketplace_listings(itemid);
CREATE INDEX IF NOT EXISTS idx_mp_listings_seller ON lg_marketplace_listings(seller_userid);
CREATE INDEX IF NOT EXISTS idx_mp_listings_expires ON lg_marketplace_listings(expires_at);

-- Marketplace sales history
CREATE TABLE IF NOT EXISTS lg_marketplace_sales (
  saleid            SERIAL PRIMARY KEY,
  listingid         INTEGER NOT NULL REFERENCES lg_marketplace_listings(listingid),
  buyer_userid      BIGINT NOT NULL,
  seller_userid     BIGINT NOT NULL,
  itemid            INTEGER NOT NULL REFERENCES lg_items(itemid),
  enhancement_level INTEGER NOT NULL DEFAULT 0,
  quantity          INTEGER NOT NULL,
  price_per_unit    INTEGER NOT NULL,
  total_price       INTEGER NOT NULL,
  currency          TEXT NOT NULL,
  sold_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mp_sales_itemid ON lg_marketplace_sales(itemid);
CREATE INDEX IF NOT EXISTS idx_mp_sales_buyer ON lg_marketplace_sales(buyer_userid);
CREATE INDEX IF NOT EXISTS idx_mp_sales_seller ON lg_marketplace_sales(seller_userid);
CREATE INDEX IF NOT EXISTS idx_mp_sales_sold_at ON lg_marketplace_sales(sold_at);

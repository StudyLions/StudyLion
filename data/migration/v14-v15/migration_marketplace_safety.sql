-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-20
-- Purpose: Add CHECK constraints to prevent negative balances
--          and quantities. Acts as a database-level safety net
--          against race conditions in the application layer.
-- ============================================================

-- Prevent negative gold balance
ALTER TABLE user_config
  ADD CONSTRAINT chk_gold_nonneg CHECK (gold >= 0);

-- Prevent negative gem balance
ALTER TABLE user_config
  ADD CONSTRAINT chk_gems_nonneg CHECK (gems >= 0 OR gems IS NULL);

-- Prevent negative remaining quantity on listings
ALTER TABLE lg_marketplace_listings
  ADD CONSTRAINT chk_mp_qty_remaining_nonneg CHECK (quantity_remaining >= 0);

-- Prevent negative quantity in inventory
ALTER TABLE lg_user_inventory
  ADD CONSTRAINT chk_inv_qty_nonneg CHECK (quantity >= 0);

-- Prevent negative quantity in sales
ALTER TABLE lg_marketplace_sales
  ADD CONSTRAINT chk_sales_qty_pos CHECK (quantity > 0);

-- Prevent negative or zero price
ALTER TABLE lg_marketplace_listings
  ADD CONSTRAINT chk_mp_price_pos CHECK (price_per_unit > 0);

ALTER TABLE lg_marketplace_sales
  ADD CONSTRAINT chk_sales_price_pos CHECK (price_per_unit > 0);

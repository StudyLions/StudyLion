-- ============================================================
-- AI-GENERATED FILE
-- Created: 2026-03-15
-- Purpose: Simplify lg_user_furniture to use text slot + asset_path
--          for composable room customization
-- ============================================================

DROP TABLE IF EXISTS lg_user_furniture;

CREATE TABLE lg_user_furniture (
  userid BIGINT NOT NULL REFERENCES user_config (userid),
  slot TEXT NOT NULL,
  asset_path TEXT NOT NULL,
  PRIMARY KEY (userid, slot)
);

GRANT ALL ON lg_user_furniture TO leo;

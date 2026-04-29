# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-29
# Purpose: Marketplace 2.0 Phase 1 -- shared mirror of the LionHeart
#          tier ladder used by the website's marketplace fee /
#          listing-duration / max-active-listings logic.
#
#          The website is the source of truth (it owns the only
#          buy/list/cancel implementations), but if the bot ever
#          gains marketplace write commands it MUST agree with
#          these numbers so a buy through Discord and a buy through
#          the website charge the same fee on the same listing.
#
#          Mirrors:
#            Lionbot-Website/utils/subscription.ts
#              - getMarketplaceFeePercent
#              - getListingDurationDays
#              - getMaxActiveListings
#
#          If you change a number in this file, change it in the
#          website too. If you change a number in the website,
#          change it here too.
# ============================================================

# Tier strings exactly match user_subscriptions.tier values
# (NONE / LIONHEART / LIONHEART_PLUS / LIONHEART_PLUS_PLUS) plus the
# website's "FREE" alias for users without an ACTIVE subscription.
TIER_FREE = "FREE"
TIER_LIONHEART = "LIONHEART"
TIER_LIONHEART_PLUS = "LIONHEART_PLUS"
TIER_LIONHEART_PLUS_PLUS = "LIONHEART_PLUS_PLUS"

ALL_TIERS = (
    TIER_FREE,
    TIER_LIONHEART,
    TIER_LIONHEART_PLUS,
    TIER_LIONHEART_PLUS_PLUS,
)

# Fee charged on the seller side at sale time (% of total price).
# FREE = 5 keeps existing listings byte-identical to the legacy world,
# so we never need a fee-snapshot column on lg_marketplace_listings.
MARKETPLACE_FEE_PERCENT_BY_TIER = {
    TIER_FREE: 5,
    TIER_LIONHEART: 4,
    TIER_LIONHEART_PLUS: 3,
    TIER_LIONHEART_PLUS_PLUS: 2,
}

# Listing window in days. Baked into lg_marketplace_listings.expires_at
# at create time, so existing listings keep whatever duration they were
# given when they were created.
LISTING_DURATION_DAYS_BY_TIER = {
    TIER_FREE: 7,
    TIER_LIONHEART: 14,
    TIER_LIONHEART_PLUS: 21,
    TIER_LIONHEART_PLUS_PLUS: 30,
}

# Max ACTIVE listings a user can have open at once. Cap is checked at
# CREATE time only -- existing listings above the cap are NEVER touched
# (grandfather rule). Free sellers above the cap simply can't add new
# listings until enough sell or expire to put them back under it.
MAX_ACTIVE_LISTINGS_BY_TIER = {
    TIER_FREE: 30,
    TIER_LIONHEART: 50,
    TIER_LIONHEART_PLUS: 75,
    TIER_LIONHEART_PLUS_PLUS: 100,
}

# --- AI-MODIFIED (2026-04-29) ---
# Purpose: Marketplace 2.0 Phase 3 -- featured listing slot caps.
# Free sellers cannot feature any listing; the feature itself is a
# LionHeart perk. The website's POST /api/pet/marketplace/feature is
# the only writer of is_featured / featured_at on lg_marketplace_listings.
#
# The bot today does NOT implement its own marketplace browse command
# -- /pet sends users to lionbot.org/pet/marketplace, where the website
# already orders by is_featured DESC, featured_at DESC, then the user's
# chosen sort.
#
# If we ever add a Discord-side browse, this MUST be the leading ORDER
# BY clause so a buyer scrolling Discord sees the same top-of-page items
# they'd see on lionbot.org. Reference query for that future implementation:
#
#     SELECT *
#       FROM lg_marketplace_listings
#      WHERE status = 'ACTIVE'
#      ORDER BY is_featured DESC,
#               featured_at DESC,
#               <user_sort>
#      LIMIT $page_size OFFSET $offset
FEATURED_LISTING_SLOTS_BY_TIER = {
    TIER_FREE: 0,
    TIER_LIONHEART: 1,
    TIER_LIONHEART_PLUS: 3,
    TIER_LIONHEART_PLUS_PLUS: 10,
}
# --- END AI-MODIFIED ---


def normalize_tier(tier):
    """Map any DB-side tier value (or None) to one of the ALL_TIERS strings.

    Any unknown value (or None / NONE / inactive) falls back to FREE so the
    caller can always trust the result.
    """
    if not tier or tier == "NONE":
        return TIER_FREE
    if tier in ALL_TIERS:
        return tier
    return TIER_FREE


def get_marketplace_fee_percent(tier):
    return MARKETPLACE_FEE_PERCENT_BY_TIER.get(normalize_tier(tier), MARKETPLACE_FEE_PERCENT_BY_TIER[TIER_FREE])


def get_listing_duration_days(tier):
    return LISTING_DURATION_DAYS_BY_TIER.get(normalize_tier(tier), LISTING_DURATION_DAYS_BY_TIER[TIER_FREE])


def get_max_active_listings(tier):
    return MAX_ACTIVE_LISTINGS_BY_TIER.get(normalize_tier(tier), MAX_ACTIVE_LISTINGS_BY_TIER[TIER_FREE])


# --- AI-MODIFIED (2026-04-29) ---
# Purpose: Marketplace 2.0 Phase 3 -- featured slot lookup mirror.
def get_featured_listing_slots(tier):
    return FEATURED_LISTING_SLOTS_BY_TIER.get(normalize_tier(tier), FEATURED_LISTING_SLOTS_BY_TIER[TIER_FREE])
# --- END AI-MODIFIED ---

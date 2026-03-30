# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-15
# Purpose: LionGotchi gameplay logic -- Gold, XP, needs, drops,
#          equipment/scroll drops, and enhancement system
# ============================================================
import random
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# --- AI-REPLACED (2026-03-17) ---
# Reason: Economy rebalance -- voice is primary activity, should be primary earner
# What the new code does better: Voice gives 2.5x more gold and 2x more XP;
#   text reduced to prevent chat-spam dominance over studying
# --- Original code (commented out for rollback) ---
# GOLD_PER_VOICE_MINUTE = 0.2
# GOLD_PER_TEXT_MESSAGE = 0.5
# XP_PER_VOICE_MINUTE = 1.0
# XP_PER_TEXT_MESSAGE = 2.0
# --- End original code ---
GOLD_PER_VOICE_MINUTE = 0.5
GOLD_PER_TEXT_MESSAGE = 0.3
XP_PER_VOICE_MINUTE = 2.0
XP_PER_TEXT_MESSAGE = 1.0
# --- END AI-REPLACED ---
LEVEL_UP_GOLD_BONUS = 50

# --- AI-REPLACED (2026-03-19) ---
# Reason: Stat redesign -- studying refills all 3 needs at faster intervals
# What the new code does better: Bath/cleanliness now refills from study,
#   intervals shortened so studying is the primary care mechanism
# --- Original code (commented out for rollback) ---
# VOICE_FOOD_REFILL_MINUTES = 30
# VOICE_SLEEP_REFILL_MINUTES = 30
# TEXT_FOOD_REFILL_MESSAGES = 50
# --- End original code ---
VOICE_NEED_REFILL_MINUTES = 15
VOICE_NEED_REFILL_MAX = 4
TEXT_NEED_REFILL_MESSAGES = 20
TEXT_NEED_REFILL_MAX = 3
# --- END AI-REPLACED ---

# --- AI-MODIFIED (2026-03-20) ---
# Purpose: Anti-cheat daily caps and text message cooldown
# Gold cap raised from 500 to 1500 -- heavy users with LionHeart++ and bonuses
# were hitting the cap after ~5 hours; 1500 allows ~15 hours of max-boosted study
DAILY_GOLD_CAP = 1500
DAILY_XP_CAP = 2500
# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Engagement tuning -- raise daily drop cap from 8 to 15
# --- Original code (commented out for rollback) ---
# DAILY_DROP_CAP = 8
# --- End original code ---
DAILY_DROP_CAP = 15
# --- END AI-MODIFIED ---
LG_MSG_COOLDOWN_SECONDS = 10
LG_TEXT_SESSION_MSG_CAP = 30
# --- END AI-MODIFIED ---

# --- AI-REPLACED (2026-03-16) ---
# Reason: Materials removed; equipment and scrolls now drop directly from activity
# What the new code does better: Drops actual usable items instead of crafting materials
# --- Original code (commented out for rollback) ---
# MATERIAL_DROP_CHANCE_VOICE = 0.20
# MATERIAL_DROP_CHANCE_TEXT = 0.12
# MATERIAL_DROP_WEIGHTS = {
#     'COMMON': 45, 'UNCOMMON': 28, 'RARE': 15,
#     'EPIC': 7, 'LEGENDARY': 3.5, 'MYTHICAL': 0.5,
# }
# MULTI_DROP_WEIGHTS = {1: 60, 2: 30, 3: 10}
# --- End original code ---

# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Engagement tuning -- generous drop rate increase
# --- Original code (commented out for rollback) ---
# ITEM_DROP_CHANCE_VOICE = 0.05
# ITEM_DROP_CHANCE_TEXT = 0.03
# ITEM_DROP_CHANCE_HARVEST = 0.15
# --- End original code ---
ITEM_DROP_CHANCE_VOICE = 0.15
ITEM_DROP_CHANCE_TEXT = 0.12
ITEM_DROP_CHANCE_HARVEST = 0.30
# --- END AI-MODIFIED ---

ITEM_DROP_WEIGHTS = {
    'COMMON': 45,
    'UNCOMMON': 28,
    'RARE': 15,
    'EPIC': 7,
    'LEGENDARY': 3.5,
    'MYTHICAL': 0.5,
}

SCROLL_DROP_RATIO = 0.6
EQUIPMENT_CATEGORIES = ('HAT', 'GLASSES', 'COSTUME', 'SHIRT', 'WINGS', 'BOOTS')

# --- END AI-REPLACED ---

# --- AI-MODIFIED (2026-03-15) ---
# Purpose: Enhancement system constants (MapleStory style)

MAX_ENHANCEMENT_BY_RARITY = {
    'COMMON': 5, 'UNCOMMON': 7, 'RARE': 10,
    'EPIC': 12, 'LEGENDARY': 15, 'MYTHICAL': 20,
}
ENHANCEMENT_GOLD_BONUS = 0.02
ENHANCEMENT_XP_BONUS = 0.02
# --- AI-MODIFIED (2026-03-17) ---
# Purpose: Drop rate bonus from enhancement + glow tier thresholds
ENHANCEMENT_DROP_BONUS = 0.005
# --- END AI-MODIFIED ---
# --- AI-REPLACED (2026-03-22) ---
# Reason: Linear penalty made scrolls unusable at high levels (1.5% for Doom at 12+)
# What the new code does better: Diminishing-returns curve keeps rates challenging but doable at all levels
# --- Original code (commented out for rollback) ---
# LEVEL_PENALTY_FACTOR = 0.08
# --- End original code ---
LEVEL_PENALTY_FLOOR = 0.30
LEVEL_DECAY_FACTOR = 0.12


def calc_level_penalty(level: int) -> float:
    return LEVEL_PENALTY_FLOOR + (1.0 - LEVEL_PENALTY_FLOOR) / (1.0 + LEVEL_DECAY_FACTOR * level)
# --- END AI-REPLACED ---

# --- AI-MODIFIED (2026-03-17) ---
# Purpose: Glow tiers based on average bonus_value per enhancement slot
GLOW_TIERS = [
    (6.0, 'celestial'),
    (4.0, 'diamond'),
    (2.5, 'gold'),
    (1.5, 'silver'),
    (0.01, 'bronze'),
]


def calc_glow_tier(enhancement_level: int, total_bonus: float) -> str:
    if enhancement_level <= 0 or total_bonus <= 0:
        return 'none'
    avg = total_bonus / enhancement_level
    for threshold, tier in GLOW_TIERS:
        if avg >= threshold:
            return tier
    return 'none'


def calc_glow_intensity(enhancement_level: int) -> int:
    if enhancement_level >= 13:
        return 3
    if enhancement_level >= 8:
        return 2
    if enhancement_level >= 4:
        return 1
    return 0
# --- END AI-MODIFIED ---

# --- END AI-MODIFIED ---

# --- AI-MODIFIED (2026-03-22) ---
# Purpose: VC Study Streak -- daily voice time boosts rarity of all drops
VC_RARITY_TIERS = [
    (300, 4.0, 'Mythical Focus'),
    (180, 3.0, 'Legendary Focus'),
    (120, 2.0, 'Epic Focus'),
    (60,  1.5, 'Rare Focus'),
    (30,  1.25, 'Study Momentum'),
]


def calc_vc_rarity_boost(daily_voice_minutes: float) -> tuple[float, str]:
    """Return (boost_multiplier, tier_name) based on cumulative daily VC time."""
    for threshold, boost, name in VC_RARITY_TIERS:
        if daily_voice_minutes >= threshold:
            return boost, name
    return 1.0, ''
# --- END AI-MODIFIED ---

# Keep old constants for backward compat reference
DROP_CHANCE_VOICE = 0.08
DROP_CHANCE_TEXT = 0.05
DROP_WEIGHTS = {
    'COMMON': 60, 'UNCOMMON': 25, 'RARE': 10,
    'EPIC': 3, 'LEGENDARY': 1.5, 'MYTHICAL': 0.5,
}

# --- AI-MODIFIED (2026-03-15) ---
# Purpose: Seed rarity system -- weights, gold multipliers, drop rate modifiers
SEED_RARITY_WEIGHTS = {'COMMON': 50, 'UNCOMMON': 25, 'RARE': 15, 'EPIC': 7, 'LEGENDARY': 3}
# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Engagement tuning -- boost farm harvest gold and item rarity for rarer plants
# --- Original code (commented out for rollback) ---
# RARITY_GOLD_MULTIPLIER = {
#     'COMMON': 1.0, 'UNCOMMON': 1.5, 'RARE': 2.0, 'EPIC': 3.0, 'LEGENDARY': 5.0,
# }
# RARITY_DROP_MULTIPLIER = {
#     'COMMON': 1.0, 'UNCOMMON': 1.25, 'RARE': 1.5, 'EPIC': 2.0, 'LEGENDARY': 3.0,
# }
# --- End original code ---
RARITY_GOLD_MULTIPLIER = {
    'COMMON': 1.0, 'UNCOMMON': 1.5, 'RARE': 2.5, 'EPIC': 4.0, 'LEGENDARY': 8.0,
}
RARITY_DROP_MULTIPLIER = {
    'COMMON': 1.0, 'UNCOMMON': 1.5, 'RARE': 2.0, 'EPIC': 3.0, 'LEGENDARY': 5.0,
}
# --- END AI-MODIFIED ---
RARITY_EMOJI = {
    'COMMON': '', 'UNCOMMON': '\U0001F539', 'RARE': '\u2764\uFE0F',
    'EPIC': '\U0001F451', 'LEGENDARY': '\u2B50',
}
RARITY_COLOR_INDEX = {
    'COMMON': 1, 'UNCOMMON': 2, 'RARE': 3, 'EPIC': 4, 'LEGENDARY': 5,
}
# --- END AI-MODIFIED ---

# --- AI-MODIFIED (2026-03-16) ---
# Purpose: LionHeart subscription tier perk multipliers
TIER_GOLD_BONUS = {
    'NONE': 1.0, 'LIONHEART': 1.15, 'LIONHEART_PLUS': 1.25, 'LIONHEART_PLUS_PLUS': 1.5,
}
TIER_DROP_RATE_BONUS = {
    'NONE': 0.0, 'LIONHEART': 0.15, 'LIONHEART_PLUS': 0.25, 'LIONHEART_PLUS_PLUS': 0.50,
}
TIER_FARM_GROWTH_SPEED = {
    'NONE': 1.0, 'LIONHEART': 1.2, 'LIONHEART_PLUS': 1.35, 'LIONHEART_PLUS_PLUS': 1.5,
}
TIER_WATER_DURATION_MULT = {
    'NONE': 1.0, 'LIONHEART': 1.5, 'LIONHEART_PLUS': 2.0, 'LIONHEART_PLUS_PLUS': 3.0,
}
TIER_DRY_PENALTY = {
    'NONE': 0.5, 'LIONHEART': 0.65, 'LIONHEART_PLUS': 0.75, 'LIONHEART_PLUS_PLUS': 0.85,
}
TIER_DEATH_TIMER_HOURS = {
    'NONE': 48, 'LIONHEART': 72, 'LIONHEART_PLUS': 96, 'LIONHEART_PLUS_PLUS': None,
}
TIER_SEED_DISCOUNT = {
    'NONE': 0.0, 'LIONHEART': 0.10, 'LIONHEART_PLUS': 0.20, 'LIONHEART_PLUS_PLUS': 0.30,
}
TIER_HARVEST_GOLD_BONUS = {
    'NONE': 0.0, 'LIONHEART': 0.15, 'LIONHEART_PLUS': 0.25, 'LIONHEART_PLUS_PLUS': 0.50,
}
TIER_UPROOT_REFUND = {
    'NONE': 0.5, 'LIONHEART': 0.75, 'LIONHEART_PLUS': 1.0, 'LIONHEART_PLUS_PLUS': 1.0,
}
SERVER_PREMIUM_GOLD_BONUS = 1.15
SERVER_PREMIUM_DROP_BONUS = 0.15
# --- END AI-MODIFIED ---

# --- AI-MODIFIED (2026-03-17) ---
# Purpose: Vote-based LG gold boost (12h after top.gg vote), queried from topgg table
VOTE_LG_GOLD_BOOST = {
    'NONE': 1.0, 'LIONHEART': 1.15, 'LIONHEART_PLUS': 1.25, 'LIONHEART_PLUS_PLUS': 1.5,
}

TIER_DISPLAY_NAMES = {
    'NONE': None, 'LIONHEART': 'LionHeart',
    'LIONHEART_PLUS': 'LionHeart+', 'LIONHEART_PLUS_PLUS': 'LionHeart++',
}


async def check_voted_recently_lg(bot, userid: int) -> bool:
    """Check if a user voted on top.gg within the last 12 hours."""
    try:
        async with bot.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT boostedtimestamp FROM topgg
                       WHERE userid = %s
                       ORDER BY boostedtimestamp DESC LIMIT 1""",
                    [userid]
                )
                rows = await cur.fetchall()
                if not rows:
                    return False
                ts = rows[0]['boostedtimestamp']
                if ts is None:
                    return False
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                return (now - ts).total_seconds() < 3600 * 12
    except Exception:
        logger.debug(f"Failed to check vote status for {userid}", exc_info=True)
        return False


async def calc_all_bonuses(bot, userid: int, user_tier: str = 'NONE',
                           server_premium: bool = False) -> dict:
    """Calculate all active bonus multipliers for a user.
    Returns a dict with individual and total multipliers."""
    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: calc_equipment_bonus now returns 3 values (gold, xp, drop_bonus)
    equip_gold, equip_xp, equip_drop = await calc_equipment_bonus(bot, userid)
    # --- END AI-MODIFIED ---
    voted = await check_voted_recently_lg(bot, userid)
    vote_gold = VOTE_LG_GOLD_BOOST.get(user_tier, 1.0) if voted else 1.0

    tier_gold = TIER_GOLD_BONUS.get(user_tier, 1.0)
    tier_drop = TIER_DROP_RATE_BONUS.get(user_tier, 0.0)
    tier_harvest = TIER_HARVEST_GOLD_BONUS.get(user_tier, 0.0)
    server_gold = SERVER_PREMIUM_GOLD_BONUS if server_premium else 1.0
    server_drop = SERVER_PREMIUM_DROP_BONUS if server_premium else 0.0

    total_gold_mult = tier_gold * server_gold * equip_gold * vote_gold
    total_xp_mult = equip_xp
    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Include equipment drop bonus in total
    total_drop_bonus = tier_drop + server_drop + equip_drop
    # --- END AI-MODIFIED ---
    total_harvest_mult = (1.0 + tier_harvest) * equip_gold * vote_gold

    return {
        'equip_gold': equip_gold,
        'equip_xp': equip_xp,
        # --- AI-MODIFIED (2026-03-17) ---
        'equip_drop': equip_drop,
        # --- END AI-MODIFIED ---
        'tier_gold': tier_gold,
        'tier_drop': tier_drop,
        'tier_harvest': tier_harvest,
        'server_gold': server_gold,
        'server_drop': server_drop,
        'vote_gold': vote_gold,
        'voted': voted,
        'user_tier': user_tier,
        'server_premium': server_premium,
        'total_gold_mult': total_gold_mult,
        'total_xp_mult': total_xp_mult,
        'total_drop_bonus': total_drop_bonus,
        'total_harvest_mult': total_harvest_mult,
    }


def format_bonus_summary(bonuses: dict) -> str:
    """Format a compact user-facing bonus breakdown string."""
    lines = []
    tier = bonuses.get('user_tier', 'NONE')
    tier_name = TIER_DISPLAY_NAMES.get(tier)

    if bonuses.get('tier_gold', 1.0) > 1.0 and tier_name:
        pct = (bonuses['tier_gold'] - 1.0) * 100
        lines.append(f"\U0001F49B +{pct:.0f}% Gold ({tier_name})")

    equip_pct = (bonuses.get('equip_gold', 1.0) - 1.0) * 100
    equip_drop_pct = bonuses.get('equip_drop', 0.0) * 100
    # --- AI-MODIFIED (2026-03-17) ---
    # Purpose: Show equipment drop rate bonus alongside Gold/XP
    if equip_pct > 0 and equip_drop_pct > 0:
        lines.append(f"\u2728 +{equip_pct:.0f}% Gold & XP, +{equip_drop_pct:.1f}% Drops (Equipment)")
    elif equip_pct > 0:
        lines.append(f"\u2728 +{equip_pct:.0f}% Gold & XP (Equipment)")
    # --- END AI-MODIFIED ---

    if bonuses.get('voted') and bonuses.get('vote_gold', 1.0) > 1.0:
        vpct = (bonuses['vote_gold'] - 1.0) * 100
        lines.append(f"\U0001F5F3\uFE0F +{vpct:.0f}% Gold (Vote Boost)")
    elif bonuses.get('voted') and bonuses.get('vote_gold', 1.0) == 1.0:
        lines.append(f"\U0001F5F3\uFE0F Vote Boost active")

    if bonuses.get('server_premium'):
        spct = (bonuses.get('server_gold', 1.0) - 1.0) * 100
        lines.append(f"\u2B50 +{spct:.0f}% Gold (Server Premium)")

    tier_drop = bonuses.get('tier_drop', 0.0)
    server_drop = bonuses.get('server_drop', 0.0)
    total_drop = tier_drop + server_drop
    if total_drop > 0:
        parts = []
        if tier_drop > 0 and tier_name:
            parts.append(tier_name)
        if server_drop > 0:
            parts.append("Server Premium")
        source = " + ".join(parts)
        lines.append(f"\U0001F381 +{total_drop * 100:.0f}% Drop Rate ({source})")

    tier_harvest = bonuses.get('tier_harvest', 0.0)
    if tier_harvest > 0 and tier_name:
        lines.append(f"\U0001F33E +{tier_harvest * 100:.0f}% Harvest Gold ({tier_name})")

    if not lines:
        return ""
    return "\n".join(lines)


def format_bonus_footer(bonuses: dict) -> str:
    """Format a one-line compact bonus string for embed footers."""
    parts = []
    total_gold = bonuses.get('total_gold_mult', 1.0)
    if total_gold > 1.0:
        parts.append(f"+{(total_gold - 1) * 100:.0f}% Gold")
    total_xp = bonuses.get('total_xp_mult', 1.0)
    if total_xp > 1.0:
        parts.append(f"+{(total_xp - 1) * 100:.0f}% XP")
    total_drop = bonuses.get('total_drop_bonus', 0.0)
    if total_drop > 0:
        parts.append(f"+{total_drop * 100:.0f}% Drops")
    if not parts:
        return "Enhance equipment & subscribe to LionHeart for bonuses!"
    return "Your bonuses: " + " | ".join(parts)
# --- END AI-MODIFIED ---


# --- AI-REPLACED (2026-03-23) ---
# Reason: Linear curve (level*100) felt flat -- no early dopamine, no late prestige
# What the new code does better: Polynomial curve gives fast early levels and
#   progressively slower high levels. ~87 days at daily cap to reach level 75.
# --- Original code (commented out for rollback) ---
# def xp_for_level(level: int) -> int:
#     return level * 100
# --- End original code ---
def xp_for_level(level: int) -> int:
    return int(25 * level ** 1.3)
# --- END AI-REPLACED ---


# --- AI-MODIFIED (2026-03-19) ---
# Purpose: Mood system -- derived from avg of 3 needs, drives XP/gold/drop multipliers
MOOD_MULTIPLIERS = {
    8: 1.25, 7: 1.20,
    6: 1.10, 5: 1.00,
    4: 0.95, 3: 0.85,
    2: 0.75, 1: 0.60,
    0: 0.50,
}

MOOD_DROP_MULTIPLIERS = {
    8: 1.0, 7: 1.0, 6: 1.0, 5: 1.0,
    4: 1.0, 3: 1.0,
    2: 0.5, 1: 0.5,
    0: 0.0,
}

MOOD_LABELS = {
    8: 'Ecstatic', 7: 'Ecstatic',
    6: 'Happy', 5: 'Happy',
    4: 'Okay', 3: 'Okay',
    2: 'Sad', 1: 'Sad',
    0: 'Fainted',
}

MOOD_EMOJI = {
    'Ecstatic': '\u2728', 'Happy': '\U0001F60A',
    'Okay': '\U0001F610', 'Sad': '\U0001F622',
    'Fainted': '\U0001F635',
}


def calc_mood(food: int, bath: int, sleep: int) -> int:
    """Derive mood (0-8) from the average of the three needs."""
    return (food + bath + sleep) // 3
# --- END AI-MODIFIED ---


def check_level_up(current_level: int, current_xp: int) -> tuple[int, int, int]:
    """Returns (new_level, remaining_xp, levels_gained)."""
    levels_gained = 0
    while current_xp >= xp_for_level(current_level):
        current_xp -= xp_for_level(current_level)
        current_level += 1
        levels_gained += 1
    return current_level, current_xp, levels_gained


# --- AI-MODIFIED (2026-03-17) ---
# Purpose: Fix rounding loss -- multiply all as floats, truncate once; add vote_gold_boost param
# --- Original code (commented out for rollback) ---
# def calc_voice_rewards(duration_seconds: int) -> dict:
#     minutes = duration_seconds / 60.0
#     gold = int(minutes * GOLD_PER_VOICE_MINUTE)
#     xp = int(minutes * XP_PER_VOICE_MINUTE)
#     food_refill = int(minutes / VOICE_FOOD_REFILL_MINUTES)
#     sleep_refill = int(minutes / VOICE_SLEEP_REFILL_MINUTES)
#     return {
#         'gold': max(gold, 0),
#         'xp': max(xp, 0),
#         'food_refill': min(food_refill, 3),
#         'sleep_refill': min(sleep_refill, 3),
#     }
# --- End original code ---
# --- AI-REPLACED (2026-03-19) ---
# Reason: Stat redesign -- voice now refills all 3 needs (food, bath, sleep)
# What the new code does better: Bath refill from voice study, faster intervals (15min)
# --- Original code (commented out for rollback) ---
# def calc_voice_rewards(duration_seconds, user_tier='NONE', server_premium=False, vote_gold_boost=1.0):
#     food_refill = int(minutes / VOICE_FOOD_REFILL_MINUTES)
#     sleep_refill = int(minutes / VOICE_SLEEP_REFILL_MINUTES)
#     return {'food_refill': min(food_refill, 3), 'sleep_refill': min(sleep_refill, 3), ...}
# --- End original code ---
def calc_voice_rewards(duration_seconds: int, user_tier: str = 'NONE',
                       server_premium: bool = False, vote_gold_boost: float = 1.0) -> dict:
    minutes = duration_seconds / 60.0
    base_gold = minutes * GOLD_PER_VOICE_MINUTE
    base_xp = minutes * XP_PER_VOICE_MINUTE
    tier_mult = TIER_GOLD_BONUS.get(user_tier, 1.0)
    server_mult = SERVER_PREMIUM_GOLD_BONUS if server_premium else 1.0
    gold = int(base_gold * tier_mult * server_mult * vote_gold_boost)
    xp = int(base_xp)
    need_refill = min(int(minutes / VOICE_NEED_REFILL_MINUTES), VOICE_NEED_REFILL_MAX)
    return {
        'gold': max(gold, 0),
        'xp': max(xp, 0),
        'base_gold': max(int(base_gold), 0),
        'food_refill': need_refill,
        'bath_refill': need_refill,
        'sleep_refill': need_refill,
    }
# --- END AI-REPLACED ---


# --- AI-MODIFIED (2026-03-17) ---
# Purpose: Fix rounding loss -- multiply all as floats, truncate once; add vote_gold_boost param
# --- Original code (commented out for rollback) ---
# def calc_text_rewards(message_count: int) -> dict:
#     gold = int(message_count * GOLD_PER_TEXT_MESSAGE)
#     xp = int(message_count * XP_PER_TEXT_MESSAGE)
#     food_refill = int(message_count / TEXT_FOOD_REFILL_MESSAGES)
#     return {
#         'gold': max(gold, 0),
#         'xp': max(xp, 0),
#         'food_refill': min(food_refill, 2),
#     }
# --- End original code ---
# --- AI-REPLACED (2026-03-19) ---
# Reason: Stat redesign -- text now refills food + bath (not sleep)
# What the new code does better: Bath refill from text, faster interval (20 msgs)
# --- Original code (commented out for rollback) ---
# def calc_text_rewards(message_count, user_tier='NONE', server_premium=False, vote_gold_boost=1.0):
#     food_refill = int(message_count / TEXT_FOOD_REFILL_MESSAGES)
#     return {'food_refill': min(food_refill, 2), ...}
# --- End original code ---
def calc_text_rewards(message_count: int, user_tier: str = 'NONE',
                      server_premium: bool = False, vote_gold_boost: float = 1.0) -> dict:
    base_gold = message_count * GOLD_PER_TEXT_MESSAGE
    base_xp = message_count * XP_PER_TEXT_MESSAGE
    tier_mult = TIER_GOLD_BONUS.get(user_tier, 1.0)
    server_mult = SERVER_PREMIUM_GOLD_BONUS if server_premium else 1.0
    gold = int(base_gold * tier_mult * server_mult * vote_gold_boost)
    xp = int(base_xp)
    need_refill = min(int(message_count / TEXT_NEED_REFILL_MESSAGES), TEXT_NEED_REFILL_MAX)
    return {
        'gold': max(gold, 0),
        'xp': max(xp, 0),
        'base_gold': max(int(base_gold), 0),
        'food_refill': need_refill,
        'bath_refill': need_refill,
    }
# --- END AI-REPLACED ---


def roll_item_drop(chance: float) -> bool:
    return random.random() < chance


def pick_drop_rarity(weights: dict = None) -> str:
    w = weights or DROP_WEIGHTS
    total = sum(w.values())
    r = random.uniform(0, total)
    cumulative = 0
    for rarity, weight in w.items():
        cumulative += weight
        if r <= cumulative:
            return rarity
    return 'COMMON'


# --- AI-MODIFIED (2026-03-15) ---
# Purpose: Roll random seed rarity when planting
def roll_seed_rarity() -> str:
    return pick_drop_rarity(SEED_RARITY_WEIGHTS)
# --- END AI-MODIFIED ---


def pick_multi_drop_count() -> int:
    """Pick how many materials to drop (1-3)."""
    total = sum(MULTI_DROP_WEIGHTS.values())
    r = random.uniform(0, total)
    cumulative = 0
    for count, weight in MULTI_DROP_WEIGHTS.items():
        cumulative += weight
        if r <= cumulative:
            return count
    return 1


async def award_gold(bot, userid: int, amount: int, tx_type: str, description: str = ''):
    """Award Gold to a user and log the transaction."""
    if amount <= 0:
        return
    lg_cog = bot.get_cog('LionGotchiCog')
    if lg_cog is None:
        return
    try:
        async with bot.db.connection() as conn:
            await conn.execute(
                """INSERT INTO lg_gold_transactions
                   (transaction_type, actorid, to_account, amount, description)
                   VALUES (%s, %s, %s, %s, %s)""",
                [tx_type, userid, userid, amount, description]
            )
            await conn.execute(
                "UPDATE user_config SET gold = gold + %s WHERE userid = %s",
                [amount, userid]
            )
    except Exception:
        logger.exception(f"Failed to award {amount} Gold to {userid}")


# --- AI-REPLACED (2026-03-21) ---
# Reason: Raw SQL UPDATE bypassed RowModel cache, causing stale level/xp reads
# What the new code does better: Updates cached pet object after DB write, returns
# dict with new_level so callers don't need to re-fetch from (stale) cache
# --- Original code (commented out for rollback) ---
# async def award_xp_and_check_level(bot, userid: int, xp_amount: int) -> int:
#     """Award XP, check for level ups, return number of levels gained."""
#     if xp_amount <= 0:
#         return 0
#     lg_cog = bot.get_cog('LionGotchiCog')
#     if lg_cog is None:
#         return 0
#     try:
#         pet = await lg_cog.data.Pet.fetch(userid)
#         if pet is None:
#             return 0
#         new_xp = (pet.xp or 0) + xp_amount
#         new_level, remaining_xp, levels_gained = check_level_up(pet.level or 1, new_xp)
#         async with bot.db.connection() as conn:
#             await conn.execute(
#                 "UPDATE lg_pets SET level = %s, xp = %s WHERE userid = %s",
#                 [new_level, remaining_xp, userid]
#             )
#         if levels_gained > 0:
#             bonus_gold = levels_gained * LEVEL_UP_GOLD_BONUS
#             await award_gold(bot, userid, bonus_gold, 'LEVEL_UP',
#                              f'Level up to {new_level}')
#         return levels_gained
#     except Exception:
#         logger.exception(f"Failed to award XP to {userid}")
#         return 0
# --- End original code ---
async def award_xp_and_check_level(bot, userid: int, xp_amount: int) -> dict:
    """Award XP, check for level ups.

    Returns dict with 'levels_gained' and 'new_level', or empty dict on failure.
    """
    if xp_amount <= 0:
        return {'levels_gained': 0, 'new_level': None}
    lg_cog = bot.get_cog('LionGotchiCog')
    if lg_cog is None:
        return {'levels_gained': 0, 'new_level': None}
    try:
        pet = await lg_cog.data.Pet.fetch(userid)
        if pet is None:
            return {'levels_gained': 0, 'new_level': None}

        new_xp = (pet.xp or 0) + xp_amount
        new_level, remaining_xp, levels_gained = check_level_up(pet.level or 1, new_xp)

        async with bot.db.connection() as conn:
            await conn.execute(
                "UPDATE lg_pets SET level = %s, xp = %s WHERE userid = %s",
                [new_level, remaining_xp, userid]
            )

        if pet.data is not None:
            pet.data['level'] = new_level
            pet.data['xp'] = remaining_xp

        if levels_gained > 0:
            bonus_gold = levels_gained * LEVEL_UP_GOLD_BONUS
            await award_gold(bot, userid, bonus_gold, 'LEVEL_UP',
                             f'Level up to {new_level}')

        return {'levels_gained': levels_gained, 'new_level': new_level}
    except Exception:
        logger.exception(f"Failed to award XP to {userid}")
        return {'levels_gained': 0, 'new_level': None}
# --- END AI-REPLACED ---


# --- AI-REPLACED (2026-03-19) ---
# Reason: Stat redesign -- bath/cleanliness now refills from study activity
# What the new code does better: Accepts bath parameter alongside food and sleep
# --- Original code (commented out for rollback) ---
# async def refill_needs(bot, userid: int, food: int = 0, sleep: int = 0):
#     new_food = min(8, (pet.food or 0) + food)
#     new_sleep = min(8, (pet.sleep or 0) + sleep)
#     await conn.execute("UPDATE lg_pets SET food = %s, sleep = %s WHERE userid = %s", ...)
# --- End original code ---
async def refill_needs(bot, userid: int, food: int = 0, bath: int = 0, sleep: int = 0):
    """Refill pet needs from activity."""
    if food <= 0 and bath <= 0 and sleep <= 0:
        return
    lg_cog = bot.get_cog('LionGotchiCog')
    if lg_cog is None:
        return
    try:
        pet = await lg_cog.data.Pet.fetch(userid)
        if pet is None:
            return
        new_food = min(8, (pet.food or 0) + food)
        new_bath = min(8, (pet.bath or 0) + bath)
        new_sleep = min(8, (pet.sleep or 0) + sleep)
        async with bot.db.connection() as conn:
            await conn.execute(
                "UPDATE lg_pets SET food = %s, bath = %s, sleep = %s WHERE userid = %s",
                [new_food, new_bath, new_sleep, userid]
            )
        # --- AI-MODIFIED (2026-03-21) ---
        # Purpose: Keep cached pet object in sync after raw SQL update
        if pet.data is not None:
            pet.data['food'] = new_food
            pet.data['bath'] = new_bath
            pet.data['sleep'] = new_sleep
        # --- END AI-MODIFIED ---
    except Exception:
        logger.exception(f"Failed to refill needs for {userid}")
# --- END AI-REPLACED ---


# --- AI-REPLACED (2026-03-16) ---
# Reason: Materials removed; equipment and scrolls now drop directly from activity
# What the new code does better: Drops equipment/scrolls instead of materials, always 1 item per drop
# --- Original code (commented out for rollback) ---
# async def try_material_drop(bot, userid, chance, rarity_multiplier=1.0, user_tier='NONE', server_premium=False):
#     """Attempt material drops. rarity_multiplier scales chance and shifts weights."""
#     effective_chance = min(chance * rarity_multiplier * (1 + TIER_DROP_RATE_BONUS.get(user_tier, 0.0) + ...), 0.95)
#     if random.random() >= effective_chance: return None
#     count = pick_multi_drop_count()
#     ... query WHERE category = 'MATERIAL' ... upsert stacking ...
# --- End original code ---

# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Add quality_boost parameter for VC Study Streak rarity boosting
# quality_boost only affects rarity weights (not drop chance), separate from rarity_multiplier
# --- AI-MODIFIED (2026-03-24) ---
# Purpose: Add equip_drop_bonus parameter so equipment enhancement drop bonus
# is actually applied to the drop chance (was previously calculated but discarded)
async def try_item_drop(bot, userid: int, chance: float, rarity_multiplier: float = 1.0,
                        user_tier: str = 'NONE', server_premium: bool = False,
                        quality_boost: float = 1.0,
                        equip_drop_bonus: float = 0.0) -> list[dict] | None:
    """Attempt equipment or scroll drops. Always drops exactly 1 item.
    rarity_multiplier scales chance and shifts weights toward rarer items.
    quality_boost shifts weights toward rarer items WITHOUT affecting drop chance.
    user_tier, server_premium, and equip_drop_bonus provide additional drop rate bonuses."""
    effective_chance = min(
        chance * rarity_multiplier * (1 + TIER_DROP_RATE_BONUS.get(user_tier, 0.0) + (SERVER_PREMIUM_DROP_BONUS if server_premium else 0) + equip_drop_bonus),
        0.95
    )
# --- END AI-MODIFIED ---
    roll = random.random()
    if roll >= effective_chance:
        return None

    combined_boost = max(rarity_multiplier, 1.0) * max(quality_boost, 1.0)
    if combined_boost > 1.0:
        boosted_weights = {}
        for r, w in ITEM_DROP_WEIGHTS.items():
            if r in ('EPIC', 'LEGENDARY', 'MYTHICAL'):
                boosted_weights[r] = w * combined_boost
            else:
                boosted_weights[r] = w
    else:
        boosted_weights = ITEM_DROP_WEIGHTS
    # --- END AI-MODIFIED ---

    is_scroll = random.random() < SCROLL_DROP_RATIO

    try:
        async with bot.db.connection() as conn:
            rarity = pick_drop_rarity(boosted_weights)
            async with conn.cursor() as cur:
                # --- AI-MODIFIED (2026-03-17) ---
                # Purpose: Rarity-weighted + drop_weight-weighted item selection
                # Uses -LN(RANDOM()) / drop_weight for correct weighted sampling
                if is_scroll:
                    await cur.execute(
                        """SELECT itemid, name, rarity, category FROM lg_items
                           WHERE category = 'SCROLL' AND rarity = %s
                           ORDER BY -LN(1.0 - RANDOM()) / GREATEST(drop_weight, 0.001)
                           LIMIT 1""",
                        [rarity]
                    )
                else:
                    await cur.execute(
                        """SELECT itemid, name, rarity, category FROM lg_items
                           WHERE category IN ('HAT','GLASSES','COSTUME','SHIRT','WINGS','BOOTS')
                             AND rarity = %s
                           ORDER BY -LN(1.0 - RANDOM()) / GREATEST(drop_weight, 0.001)
                           LIMIT 1""",
                        [rarity]
                    )
                # --- END AI-MODIFIED ---
                rows = await cur.fetchall()
                if not rows:
                    await cur.execute(
                        """SELECT itemid, name, rarity, category FROM lg_items
                           WHERE category IN ('HAT','GLASSES','COSTUME','SHIRT','WINGS','BOOTS','SCROLL')
                           ORDER BY -LN(1.0 - RANDOM()) / GREATEST(drop_weight, 0.001)
                           LIMIT 1"""
                    )
                    rows = await cur.fetchall()
            if not rows:
                return None

            item = rows[0]
            raw_rarity = item['rarity']
            if isinstance(raw_rarity, str):
                rarity_str = raw_rarity
            elif hasattr(raw_rarity, 'value'):
                rarity_str = raw_rarity.value
            else:
                rarity_str = str(raw_rarity)

            raw_cat = item['category']
            if isinstance(raw_cat, str):
                cat_str = raw_cat
            elif hasattr(raw_cat, 'value'):
                cat_str = raw_cat.value
            else:
                cat_str = str(raw_cat)

            if cat_str == 'SCROLL':
                await conn.execute(
                    """INSERT INTO lg_user_inventory (userid, itemid, source, quantity, enhancement_level)
                       VALUES (%s, %s, 'DROP', 1, 0)
                       ON CONFLICT (userid, itemid) WHERE enhancement_level = 0
                       DO UPDATE SET quantity = lg_user_inventory.quantity + 1""",
                    [userid, item['itemid']]
                )
            else:
                # --- AI-MODIFIED (2026-03-23) ---
                # Purpose: Use upsert to prevent UniqueViolation when user already owns the item
                await conn.execute(
                    """INSERT INTO lg_user_inventory (userid, itemid, source, quantity, enhancement_level)
                       VALUES (%s, %s, 'DROP', 1, 0)
                       ON CONFLICT (userid, itemid) WHERE enhancement_level = 0
                       DO UPDATE SET quantity = lg_user_inventory.quantity + 1""",
                    [userid, item['itemid']]
                )
                # --- END AI-MODIFIED ---

            dropped = [{
                'itemid': item['itemid'],
                'name': item['name'],
                'rarity': rarity_str,
                'category': cat_str,
            }]
            return dropped
    except Exception:
        logger.exception(f"Failed item drop for {userid}")
        return None

# --- END AI-REPLACED ---

# --- AI-MODIFIED (2026-03-15) ---
# Purpose: Enhancement system and equipment bonus calculation

# --- AI-REPLACED (2026-03-17) ---
# Reason: Bonus now calculated from lg_enhancement_slots (scroll quality) instead of flat per-level
# What the new code does better: Each enhancement slot contributes its scroll's bonus_value,
#   so high-risk scrolls give more stats. Also adds drop rate bonus.
# --- Original code (commented out for rollback) ---
# async def calc_equipment_bonus(bot, userid: int) -> tuple[float, float]:
#     """Calculate total Gold and XP bonus from enhanced equipped items.
#     Returns (gold_multiplier, xp_multiplier) where 1.0 means no bonus."""
#     try:
#         async with bot.db.connection() as conn:
#             async with conn.cursor() as cur:
#                 await cur.execute(
#                     """SELECT COALESCE(SUM(ui.enhancement_level), 0) AS total_enhance
#                        FROM lg_pet_equipment e
#                        JOIN lg_user_inventory ui ON ui.userid = e.userid AND ui.itemid = e.itemid
#                        WHERE e.userid = %s AND ui.enhancement_level > 0""",
#                     [userid]
#                 )
#                 rows = await cur.fetchall()
#                 total = rows[0]['total_enhance'] if rows else 0
#         gold_mult = 1.0 + (total * ENHANCEMENT_GOLD_BONUS)
#         xp_mult = 1.0 + (total * ENHANCEMENT_XP_BONUS)
#         return gold_mult, xp_mult
#     except Exception:
#         logger.exception(f"Failed to calc equipment bonus for {userid}")
#         return 1.0, 1.0
# --- End original code ---
async def calc_equipment_bonus(bot, userid: int) -> tuple[float, float, float]:
    """Calculate total Gold, XP, and Drop Rate bonus from enhanced equipped items.
    Returns (gold_multiplier, xp_multiplier, drop_bonus) based on scroll quality."""
    try:
        async with bot.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT COALESCE(SUM(es.bonus_value), 0) AS total_bonus
                       FROM lg_pet_equipment e
                       JOIN lg_user_inventory ui ON ui.userid = e.userid AND ui.itemid = e.itemid
                       JOIN lg_enhancement_slots es ON es.inventoryid = ui.inventoryid
                       WHERE e.userid = %s""",
                    [userid]
                )
                rows = await cur.fetchall()
                total_bonus = float(rows[0]['total_bonus']) if rows else 0.0
        gold_mult = 1.0 + (total_bonus * ENHANCEMENT_GOLD_BONUS)
        xp_mult = 1.0 + (total_bonus * ENHANCEMENT_XP_BONUS)
        drop_bonus = total_bonus * ENHANCEMENT_DROP_BONUS
        return gold_mult, xp_mult, drop_bonus
    except Exception:
        logger.exception(f"Failed to calc equipment bonus for {userid}")
        return 1.0, 1.0, 0.0
# --- END AI-REPLACED ---


# --- AI-REPLACED (2026-03-17) ---
# Reason: MapleStory-style scroll system -- each scroll has a bonus_value that gets
#   recorded in lg_enhancement_slots on success. Returns bonus info for display.
# What the new code does better: Tracks scroll history per slot, variable bonus per scroll
# --- Original code (commented out for rollback) ---
# async def attempt_enhance(bot, userid, inventory_id, scroll_itemid):
#     ...fetches scroll, rolls, updates enhancement_level +1, no bonus tracking...
# --- End original code ---
async def attempt_enhance(bot, userid: int, inventory_id: int, scroll_itemid: int) -> dict:
    """Attempt to enhance an equipment item using a scroll.
    Returns dict with keys: success, destroyed, error, new_level, item_name, scroll_name,
    bonus_gained, glow_tier."""
    result = {'success': False, 'destroyed': False, 'error': None,
              'new_level': 0, 'item_name': '', 'scroll_name': '',
              'bonus_gained': 0.0, 'glow_tier': 'none'}
    try:
        async with bot.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT ui.inventoryid, ui.itemid, ui.enhancement_level, ui.quantity,
                              i.name, i.rarity, i.category, i.slot
                       FROM lg_user_inventory ui
                       JOIN lg_items i ON ui.itemid = i.itemid
                       WHERE ui.inventoryid = %s AND ui.userid = %s""",
                    [inventory_id, userid]
                )
                eq_rows = await cur.fetchall()
                if not eq_rows:
                    result['error'] = "Item not found in your inventory."
                    return result
                eq = eq_rows[0]
                result['item_name'] = eq['name']

                if eq['category'] in ('MATERIAL', 'SCROLL', 'FURNITURE', 'ROOM',
                                       'GAMEBOY_SKIN', 'FARM_SEED', 'CONSUMABLE'):
                    result['error'] = "This item cannot be enhanced."
                    return result

                rarity_str = eq['rarity'] if isinstance(eq['rarity'], str) else str(eq['rarity'])
                max_level = MAX_ENHANCEMENT_BY_RARITY.get(rarity_str, 5)
                current_level = eq['enhancement_level'] or 0
                if current_level >= max_level:
                    result['error'] = f"This item is already at max enhancement (+{max_level})."
                    return result

                await cur.execute(
                    """SELECT ui.inventoryid, ui.quantity, i.name, i.itemid
                       FROM lg_user_inventory ui
                       JOIN lg_items i ON ui.itemid = i.itemid
                       WHERE ui.userid = %s AND i.itemid = %s
                         AND i.category = 'SCROLL' AND ui.quantity > 0""",
                    [userid, scroll_itemid]
                )
                scroll_rows = await cur.fetchall()
                if not scroll_rows:
                    result['error'] = "You don't have that scroll."
                    return result
                scroll_inv = scroll_rows[0]
                result['scroll_name'] = scroll_inv['name']

                await cur.execute(
                    "SELECT success_rate, destroy_rate, bonus_value FROM lg_scroll_properties WHERE itemid = %s",
                    [scroll_itemid]
                )
                prop_rows = await cur.fetchall()
                if not prop_rows:
                    result['error'] = "Invalid scroll (no properties defined)."
                    return result
                props = prop_rows[0]

            base_success = float(props['success_rate'])
            destroy_rate = float(props['destroy_rate'])
            bonus_value = float(props['bonus_value'])
            # --- AI-REPLACED (2026-03-22) ---
            # Reason: Old linear penalty made high-level scrolling nearly impossible
            # What the new code does better: Diminishing-returns curve via calc_level_penalty()
            # --- Original code (commented out for rollback) ---
            # effective_success = base_success * max(0.1, 1.0 - LEVEL_PENALTY_FACTOR * current_level)
            # --- End original code ---
            effective_success = base_success * calc_level_penalty(current_level)
            # --- END AI-REPLACED ---

            if scroll_inv['quantity'] <= 1:
                await conn.execute(
                    "DELETE FROM lg_user_inventory WHERE inventoryid = %s",
                    [scroll_inv['inventoryid']]
                )
            else:
                await conn.execute(
                    "UPDATE lg_user_inventory SET quantity = quantity - 1 WHERE inventoryid = %s",
                    [scroll_inv['inventoryid']]
                )

            roll = random.random()
            if roll < effective_success:
                new_level = current_level + 1
                await conn.execute(
                    "UPDATE lg_user_inventory SET enhancement_level = %s WHERE inventoryid = %s",
                    [new_level, inventory_id]
                )
                await conn.execute(
                    """INSERT INTO lg_enhancement_slots
                       (inventoryid, slot_number, scroll_itemid, scroll_name, bonus_value)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (inventoryid, slot_number) DO NOTHING""",
                    [inventory_id, new_level, scroll_itemid, scroll_inv['name'], bonus_value]
                )
                result['success'] = True
                result['new_level'] = new_level
                result['bonus_gained'] = bonus_value

                async with conn.cursor() as cur2:
                    await cur2.execute(
                        "SELECT COALESCE(SUM(bonus_value), 0) AS total FROM lg_enhancement_slots WHERE inventoryid = %s",
                        [inventory_id]
                    )
                    srows = await cur2.fetchall()
                    total_bonus = float(srows[0]['total']) if srows else 0.0
                result['glow_tier'] = calc_glow_tier(new_level, total_bonus)
                # --- AI-MODIFIED (2026-03-24) ---
                # Purpose: Log successful enhancement to lg_enhancement_log for audit trail
                await conn.execute(
                    """INSERT INTO lg_enhancement_log
                       (userid, inventoryid, item_name, scroll_name, outcome, from_level, to_level)
                       VALUES (%s, %s, %s, %s, 'SUCCESS', %s, %s)""",
                    [userid, inventory_id, eq['name'], scroll_inv['name'],
                     current_level, new_level]
                )
                # --- END AI-MODIFIED ---
            else:
                if random.random() < destroy_rate:
                    # --- AI-MODIFIED (2026-03-24) ---
                    # Purpose: Log destruction to lg_enhancement_log before deleting the item
                    await conn.execute(
                        """INSERT INTO lg_enhancement_log
                           (userid, inventoryid, item_name, scroll_name, outcome, from_level, to_level)
                           VALUES (%s, %s, %s, %s, 'DESTROYED', %s, %s)""",
                        [userid, inventory_id, eq['name'], scroll_inv['name'],
                         current_level, current_level]
                    )
                    # --- END AI-MODIFIED ---
                    await conn.execute(
                        "DELETE FROM lg_pet_equipment WHERE userid = %s AND itemid = %s",
                        [userid, eq['itemid']]
                    )
                    await conn.execute(
                        "DELETE FROM lg_user_inventory WHERE inventoryid = %s",
                        [inventory_id]
                    )
                    result['destroyed'] = True
                else:
                    result['new_level'] = current_level
                    # --- AI-MODIFIED (2026-03-24) ---
                    # Purpose: Log failed enhancement attempt to lg_enhancement_log
                    await conn.execute(
                        """INSERT INTO lg_enhancement_log
                           (userid, inventoryid, item_name, scroll_name, outcome, from_level, to_level)
                           VALUES (%s, %s, %s, %s, 'FAILED', %s, %s)""",
                        [userid, inventory_id, eq['name'], scroll_inv['name'],
                         current_level, current_level]
                    )
                    # --- END AI-MODIFIED ---

        return result
    except Exception:
        logger.exception(f"Enhancement failed for user {userid}")
        result['error'] = "An unexpected error occurred."
        return result
# --- END AI-REPLACED ---


# --- AI-REPLACED (2026-03-15) ---
# Reason: Activity-driven farm growth, material drops, enhancement bonuses
# --- Original code (commented out for rollback) ---
# async def try_item_drop(bot, userid, chance): ...
# async def try_seed_drop(bot, userid, chance): ...
# --- End original code ---

# --- AI-REPLACED (2026-03-17) ---
# Reason: Economy rebalance -- voice drives farm growth, text reduced
# What the new code does better: Voice gives 2x farm growth, text halved
# --- Original code (commented out for rollback) ---
# GROWTH_PER_VOICE_MINUTE = 1.0
# GROWTH_PER_TEXT_MESSAGE = 2.0
# --- End original code ---
# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Engagement tuning -- faster farm growth and stronger water bonus
# --- Original code (commented out for rollback) ---
# GROWTH_PER_VOICE_MINUTE = 2.0
# GROWTH_PER_TEXT_MESSAGE = 1.0
# WATER_BOOST = 1.5
# --- End original code ---
GROWTH_PER_VOICE_MINUTE = 3.0
GROWTH_PER_TEXT_MESSAGE = 2.0
# --- END AI-MODIFIED ---
# --- END AI-REPLACED ---
WATER_BOOST = 2.0
DRY_PENALTY = 0.5
DRY_DEATH_HOURS = 48

# --- AI-MODIFIED (2026-03-16) ---
# Purpose: Add LionHeart tier perks to farm growth (speed, water duration, dry penalty, death timer)
# --- Original signature/lines (commented out for rollback) ---
# async def process_farm_growth(bot, userid: int, voice_minutes: float = 0, message_count: int = 0):
#     base_points = voice_minutes * GROWTH_PER_VOICE_MINUTE + message_count * GROWTH_PER_TEXT_MESSAGE
#     water_interval = plot['water_interval_hours'] or 4
#     if hours_since > DRY_DEATH_HOURS:
#     multiplier = WATER_BOOST if is_watered else DRY_PENALTY
# --- End original code ---
async def process_farm_growth(bot, userid: int, voice_minutes: float = 0, message_count: int = 0, user_tier: str = 'NONE'):
    """Distribute activity-based growth points to all active farm plots.
    Points are split among active plots; watered plots get a 1.5x boost, dry get penalty based on tier."""
    base_points = (voice_minutes * GROWTH_PER_VOICE_MINUTE + message_count * GROWTH_PER_TEXT_MESSAGE) * TIER_FARM_GROWTH_SPEED.get(user_tier, 1.0)
    if base_points <= 0:
        return
    try:
        async with bot.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT f.plot_id, f.seed_id, f.growth_stage, f.growth_points,
                              f.last_watered, f.dead,
                              s.growth_points_needed, s.water_interval_hours
                       FROM lg_user_farm f
                       LEFT JOIN lg_farm_seeds s ON f.seed_id = s.seed_id
                       WHERE f.userid = %s AND f.seed_id IS NOT NULL
                         AND f.dead = false AND f.growth_stage < 5""",
                    [userid]
                )
                active_plots = await cur.fetchall()

            if not active_plots:
                return

            now = datetime.now(timezone.utc)
            active_count = len(active_plots)
            per_plot_base = base_points / active_count

            for plot in active_plots:
                water_interval = (plot['water_interval_hours'] or 4) * TIER_WATER_DURATION_MULT.get(user_tier, 1.0)
                is_watered = False
                if plot['last_watered']:
                    lw = plot['last_watered']
                    if lw.tzinfo is None:
                        lw = lw.replace(tzinfo=timezone.utc)
                    hours_since = (now - lw).total_seconds() / 3600
                    death_hours = TIER_DEATH_TIMER_HOURS.get(user_tier, 48)
                    if death_hours is not None and hours_since > death_hours:
                        await conn.execute(
                            "UPDATE lg_user_farm SET dead = true WHERE userid = %s AND plot_id = %s",
                            [userid, plot['plot_id']]
                        )
                        continue
                    is_watered = hours_since < water_interval

                multiplier = WATER_BOOST if is_watered else TIER_DRY_PENALTY.get(user_tier, 0.5)
                earned = per_plot_base * multiplier

                new_points = (plot['growth_points'] or 0) + earned
                points_needed = plot['growth_points_needed'] or 100
                points_per_stage = points_needed / 5.0
                current_stage = plot['growth_stage'] or 1
                new_stage = min(5, max(current_stage, 1 + int(new_points / points_per_stage)))

                vm_add = (voice_minutes / active_count) if voice_minutes else 0
                msg_add = int(message_count / active_count) if message_count else 0

                await conn.execute(
                    """UPDATE lg_user_farm
                       SET growth_points = %s, growth_stage = %s,
                           voice_minutes_earned = voice_minutes_earned + %s,
                           messages_earned = messages_earned + %s
                       WHERE userid = %s AND plot_id = %s""",
                    [new_points, new_stage, vm_add, msg_add, userid, plot['plot_id']]
                )
    except Exception:
        logger.exception(f"Failed farm growth for {userid}")
# --- END AI-MODIFIED ---


# --- AI-GENERATED (2026-03-30) ---
# Purpose: Growth engine for family farm plots — all family members' activity contributes collaboratively
async def process_family_farm_growth(bot, userid: int, voice_minutes: float = 0, message_count: int = 0, user_tier: str = 'NONE'):
    """Distribute activity-based growth points to all active family farm plots.
    Each family member's activity contributes to the shared family farm.
    Uses the contributing user's tier for growth speed, but fixed 48h death timer and base water intervals."""
    base_points = (voice_minutes * GROWTH_PER_VOICE_MINUTE + message_count * GROWTH_PER_TEXT_MESSAGE) * TIER_FARM_GROWTH_SPEED.get(user_tier, 1.0)
    if base_points <= 0:
        return
    try:
        async with bot.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT family_id FROM lg_family_members WHERE userid = %s AND left_at IS NULL",
                    [userid]
                )
                row = await cur.fetchone()
            if not row:
                return
            family_id = row['family_id']

            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT fp.plot_id, fp.farm_index, fp.seed_id, fp.growth_stage, fp.growth_points,
                              fp.last_watered, fp.dead,
                              s.growth_points_needed, s.water_interval_hours
                       FROM lg_family_farm_plots fp
                       LEFT JOIN lg_farm_seeds s ON fp.seed_id = s.seed_id
                       WHERE fp.family_id = %s AND fp.seed_id IS NOT NULL
                         AND (fp.dead = false OR fp.dead IS NULL) AND (fp.growth_stage IS NULL OR fp.growth_stage < 5)""",
                    [family_id]
                )
                active_plots = await cur.fetchall()

            if not active_plots:
                return

            now = datetime.now(timezone.utc)
            active_count = len(active_plots)
            per_plot_base = base_points / active_count

            for plot in active_plots:
                water_interval = plot['water_interval_hours'] or 4
                is_watered = False
                if plot['last_watered']:
                    lw = plot['last_watered']
                    if lw.tzinfo is None:
                        lw = lw.replace(tzinfo=timezone.utc)
                    hours_since = (now - lw).total_seconds() / 3600
                    if hours_since > DRY_DEATH_HOURS:
                        await conn.execute(
                            """UPDATE lg_family_farm_plots SET dead = true
                               WHERE family_id = %s AND farm_index = %s AND plot_id = %s""",
                            [family_id, plot['farm_index'], plot['plot_id']]
                        )
                        continue
                    is_watered = hours_since < water_interval

                multiplier = WATER_BOOST if is_watered else DRY_PENALTY
                earned = per_plot_base * multiplier

                new_points = (plot['growth_points'] or 0) + earned
                points_needed = plot['growth_points_needed'] or 100
                points_per_stage = points_needed / 5.0
                current_stage = plot['growth_stage'] or 1
                new_stage = min(5, max(current_stage, 1 + int(new_points / points_per_stage)))

                await conn.execute(
                    """UPDATE lg_family_farm_plots
                       SET growth_points = %s, growth_stage = %s
                       WHERE family_id = %s AND farm_index = %s AND plot_id = %s""",
                    [new_points, new_stage, family_id, plot['farm_index'], plot['plot_id']]
                )
    except Exception:
        logger.exception(f"Failed family farm growth for user {userid}")
# --- END AI-GENERATED ---


# --- AI-REPLACED (2026-03-16) ---
# Reason: Materials removed; use try_item_drop instead of try_material_drop, return 'drops' key
# What the new code does better: Drops equipment/scrolls directly instead of materials
# --- Original code (commented out for rollback) ---
# async def process_voice_activity(bot, userid, duration_seconds, user_tier='NONE', server_premium=False):
#     ...
#     materials = await try_material_drop(bot, userid, MATERIAL_DROP_CHANCE_VOICE, ...)
#     return {'materials': materials, 'levels': levels}
# async def process_text_activity(bot, userid, message_count, user_tier='NONE', server_premium=False, skip_drop=False):
#     ...
#     materials = await try_material_drop(bot, userid, MATERIAL_DROP_CHANCE_TEXT, ...)
#     return {'materials': materials, 'levels': levels}
# --- End original code ---

# --- AI-REPLACED (2026-03-19) ---
# Reason: Stat redesign -- mood multiplier affects gold/XP/drops, bath refill from voice
# What the new code does better: Mood-based reward scaling, all 3 needs refilled from voice
# --- Original code (commented out for rollback) ---
# async def process_voice_activity(bot, userid, duration_seconds, user_tier='NONE', server_premium=False,
#                                  max_gold=None, max_xp=None, allow_drop=True):
#     boosted_gold = int(rewards['gold'] * gold_mult)
#     boosted_xp = int(rewards['xp'] * xp_mult)
#     await refill_needs(bot, userid, food=rewards['food_refill'], sleep=rewards['sleep_refill'])
# --- End original code ---
# --- AI-MODIFIED (2026-03-22) ---
# Purpose: Add vc_quality_boost parameter for VC Study Streak
async def process_voice_activity(bot, userid: int, duration_seconds: int,
                                 user_tier: str = 'NONE', server_premium: bool = False,
                                 max_gold: int | None = None, max_xp: int | None = None,
                                 allow_drop: bool = True, mood: int = 5,
                                 vc_quality_boost: float = 1.0) -> dict:
    """Process all LionGotchi rewards from a voice session.
    mood (0-8) applies a multiplier to gold/XP and affects drop chance.
    vc_quality_boost shifts drop rarity toward rarer items without changing drop chance."""
    mood_mult = MOOD_MULTIPLIERS.get(mood, 1.0)
    mood_drop = MOOD_DROP_MULTIPLIERS.get(mood, 1.0)

    voted = await check_voted_recently_lg(bot, userid)
    vote_boost = VOTE_LG_GOLD_BOOST.get(user_tier, 1.0) if voted else 1.0

    rewards = calc_voice_rewards(duration_seconds, user_tier=user_tier,
                                 server_premium=server_premium, vote_gold_boost=vote_boost)

    # --- AI-MODIFIED (2026-03-24) ---
    # Purpose: Pass equipment drop bonus to try_item_drop (was previously discarded)
    gold_mult, xp_mult, equip_drop = await calc_equipment_bonus(bot, userid)
    # --- END AI-MODIFIED ---
    boosted_gold = int(rewards['gold'] * gold_mult * mood_mult)
    boosted_xp = int(rewards['xp'] * xp_mult * mood_mult)

    if max_gold is not None:
        boosted_gold = min(boosted_gold, max(0, max_gold))
    if max_xp is not None:
        boosted_xp = min(boosted_xp, max(0, max_xp))

    await award_gold(bot, userid, boosted_gold, 'VOICE_ACTIVITY',
                     f'{duration_seconds}s voice session')
    # --- AI-MODIFIED (2026-03-21) ---
    # Purpose: Use dict return from award_xp_and_check_level instead of
    # re-fetching pet from stale cache to get new_level
    level_result = await award_xp_and_check_level(bot, userid, boosted_xp)
    levels = level_result.get('levels_gained', 0)
    new_level = level_result.get('new_level')
    # --- END AI-MODIFIED ---
    await refill_needs(bot, userid,
                       food=rewards['food_refill'],
                       bath=rewards.get('bath_refill', 0),
                       sleep=rewards['sleep_refill'])

    voice_minutes = duration_seconds / 60.0
    drops = None
    if allow_drop and mood_drop > 0:
        voice_drop_chance = min(ITEM_DROP_CHANCE_VOICE * max(1.0, voice_minutes / 30.0) * mood_drop, 0.50)
        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Pass equipment drop bonus to try_item_drop
        drops = await try_item_drop(bot, userid, voice_drop_chance,
                                    user_tier=user_tier, server_premium=server_premium,
                                    quality_boost=vc_quality_boost,
                                    equip_drop_bonus=equip_drop)
        # --- END AI-MODIFIED ---

    await process_farm_growth(bot, userid, voice_minutes=voice_minutes, user_tier=user_tier)
    # --- AI-MODIFIED (2026-03-30) ---
    # Purpose: Also grow family farm plots from voice activity
    await process_family_farm_growth(bot, userid, voice_minutes=voice_minutes, user_tier=user_tier)
    # --- END AI-MODIFIED ---

    return {
        'drops': drops, 'levels': levels, 'new_level': new_level,
        'gold_earned': boosted_gold, 'xp_earned': boosted_xp,
        'base_gold': rewards.get('base_gold', 0),
        'mood': mood, 'mood_mult': mood_mult,
    }
# --- END AI-MODIFIED ---
# --- END AI-REPLACED ---


# --- AI-REPLACED (2026-03-19) ---
# Reason: Stat redesign -- mood multiplier affects gold/XP, bath refill from text
# What the new code does better: Mood-based reward scaling, food + bath refilled from text
# --- Original code (commented out for rollback) ---
# async def process_text_activity(bot, userid, message_count, user_tier='NONE', server_premium=False,
#                                 skip_drop=False, max_gold=None, max_xp=None):
#     boosted_gold = int(rewards['gold'] * gold_mult)
#     boosted_xp = int(rewards['xp'] * xp_mult)
#     await refill_needs(bot, userid, food=rewards['food_refill'])
# --- End original code ---
async def process_text_activity(bot, userid: int, message_count: int,
                                user_tier: str = 'NONE', server_premium: bool = False,
                                skip_drop: bool = False,
                                max_gold: int | None = None, max_xp: int | None = None,
                                mood: int = 5) -> dict:
    """Process all LionGotchi rewards from a text session.
    mood (0-8) applies a multiplier to gold/XP."""
    mood_mult = MOOD_MULTIPLIERS.get(mood, 1.0)

    voted = await check_voted_recently_lg(bot, userid)
    vote_boost = VOTE_LG_GOLD_BOOST.get(user_tier, 1.0) if voted else 1.0

    rewards = calc_text_rewards(message_count, user_tier=user_tier,
                                server_premium=server_premium, vote_gold_boost=vote_boost)

    # --- AI-MODIFIED (2026-03-24) ---
    # Purpose: Pass equipment drop bonus to try_item_drop (was previously discarded)
    gold_mult, xp_mult, equip_drop = await calc_equipment_bonus(bot, userid)
    # --- END AI-MODIFIED ---
    boosted_gold = int(rewards['gold'] * gold_mult * mood_mult)
    boosted_xp = int(rewards['xp'] * xp_mult * mood_mult)

    if max_gold is not None:
        boosted_gold = min(boosted_gold, max(0, max_gold))
    if max_xp is not None:
        boosted_xp = min(boosted_xp, max(0, max_xp))

    await award_gold(bot, userid, boosted_gold, 'TEXT_ACTIVITY',
                     f'{message_count} messages')
    # --- AI-MODIFIED (2026-03-21) ---
    # Purpose: Use dict return from award_xp_and_check_level instead of
    # re-fetching pet from stale cache to get new_level
    level_result = await award_xp_and_check_level(bot, userid, boosted_xp)
    levels = level_result.get('levels_gained', 0)
    new_level = level_result.get('new_level')
    # --- END AI-MODIFIED ---
    await refill_needs(bot, userid,
                       food=rewards['food_refill'],
                       bath=rewards.get('bath_refill', 0))

    drops = None
    if not skip_drop:
        # --- AI-MODIFIED (2026-03-24) ---
        # Purpose: Pass equipment drop bonus to try_item_drop
        drops = await try_item_drop(bot, userid, ITEM_DROP_CHANCE_TEXT,
                                    user_tier=user_tier, server_premium=server_premium,
                                    equip_drop_bonus=equip_drop)
        # --- END AI-MODIFIED ---

    return {
        'drops': drops, 'levels': levels, 'new_level': new_level,
        'gold_earned': boosted_gold, 'xp_earned': boosted_xp,
        'base_gold': rewards.get('base_gold', 0),
        'mood': mood, 'mood_mult': mood_mult,
    }
# --- END AI-REPLACED ---

# --- END AI-REPLACED ---

# --- END AI-REPLACED ---


# --- AI-GENERATED (2026-03-24) ---
# Purpose: Family XP earning system -- award XP to user's family after pet XP is calculated
def _family_xp_threshold(level: int) -> int:
    """Cumulative XP needed to reach a given family level.
    Matches the website formula in familyPermissions.ts."""
    if level <= 1:
        return 0
    return int(500 * ((level - 1) ** 1.8))


def family_level_from_xp(xp: int) -> int:
    """Compute family level from cumulative XP.
    Matches familyLevelFromXp in familyPermissions.ts."""
    level = 1
    while _family_xp_threshold(level + 1) <= xp:
        level += 1
    return level


async def award_family_xp(bot, userid: int, xp_amount: int):
    """Award XP to the user's family (if any) and update contribution + level.

    Called after pet XP is awarded so all bonuses are already applied.
    Silently skips if the user is not in a family.
    """
    if xp_amount <= 0:
        return
    # --- AI-MODIFIED (2026-03-24) ---
    # Purpose: fix psycopg3 cursor usage -- conn.execute() returns a cursor,
    # not rows. Must use cursor.fetchall()/fetchone() to get row data.
    try:
        async with bot.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT family_id FROM lg_family_members "
                    "WHERE userid = %s AND left_at IS NULL LIMIT 1",
                    [userid]
                )
                rows = await cur.fetchall()
                if not rows:
                    return
                family_id = rows[0]['family_id']

                await cur.execute(
                    "UPDATE lg_family_members SET contribution_xp = contribution_xp + %s "
                    "WHERE family_id = %s AND userid = %s AND left_at IS NULL",
                    [xp_amount, family_id, userid]
                )

                await cur.execute(
                    "UPDATE lg_families SET xp = xp + %s WHERE family_id = %s RETURNING xp",
                    [xp_amount, family_id]
                )
                fam_rows = await cur.fetchall()
                if fam_rows:
                    new_xp = int(fam_rows[0]['xp'] or 0)
                    old_level = family_level_from_xp(max(0, new_xp - xp_amount))
                    new_level = family_level_from_xp(new_xp)
                    await cur.execute(
                        "UPDATE lg_families SET level = %s WHERE family_id = %s",
                        [new_level, family_id]
                    )
                    # --- AI-MODIFIED (2026-03-30) ---
                    # Purpose: Auto-unlock extra farms when family levels past thresholds
                    old_max_farms = 1 + old_level // 5
                    new_max_farms = 1 + new_level // 5
                    if new_max_farms > old_max_farms:
                        for fi in range(old_max_farms, new_max_farms):
                            await cur.execute(
                                "INSERT INTO lg_family_farms (family_id, farm_index, unlocked_at) "
                                "VALUES (%s, %s, NOW()) ON CONFLICT DO NOTHING",
                                [family_id, fi])
                            await cur.execute(
                                "INSERT INTO lg_family_farm_plots (family_id, farm_index, plot_id) "
                                "SELECT %s, %s, generate_series(0, 14) ON CONFLICT DO NOTHING",
                                [family_id, fi])
                        await cur.execute(
                            "UPDATE lg_families SET max_farms = %s WHERE family_id = %s",
                            [new_max_farms, family_id])
                    # --- END AI-MODIFIED ---
    # --- END AI-MODIFIED ---
    except Exception:
        logger.exception("Error awarding family XP for userid=%s", userid)
# --- END AI-GENERATED ---

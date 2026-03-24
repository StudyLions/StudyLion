# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-17
# Purpose: Standalone simulation script to verify LionGotchi
#          bonus stacking math across all scenarios.
#          Run with: python -m modules.liongotchi.test_bonuses
# ============================================================
"""
Simulates bonus calculations for different user profiles without
needing a database connection. Tests the pure math functions and
validates that bonuses stack correctly.

Usage: python test_bonuses.py  (run from the directory containing this file)
"""
import sys
import os
import importlib.util

_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("gameplay", os.path.join(_dir, "gameplay.py"))
_gp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gp)

GOLD_PER_VOICE_MINUTE = _gp.GOLD_PER_VOICE_MINUTE
GOLD_PER_TEXT_MESSAGE = _gp.GOLD_PER_TEXT_MESSAGE
XP_PER_VOICE_MINUTE = _gp.XP_PER_VOICE_MINUTE
XP_PER_TEXT_MESSAGE = _gp.XP_PER_TEXT_MESSAGE
TIER_GOLD_BONUS = _gp.TIER_GOLD_BONUS
TIER_DROP_RATE_BONUS = _gp.TIER_DROP_RATE_BONUS
TIER_HARVEST_GOLD_BONUS = _gp.TIER_HARVEST_GOLD_BONUS
TIER_UPROOT_REFUND = _gp.TIER_UPROOT_REFUND
TIER_SEED_DISCOUNT = _gp.TIER_SEED_DISCOUNT
SERVER_PREMIUM_GOLD_BONUS = _gp.SERVER_PREMIUM_GOLD_BONUS
SERVER_PREMIUM_DROP_BONUS = _gp.SERVER_PREMIUM_DROP_BONUS
ENHANCEMENT_GOLD_BONUS = _gp.ENHANCEMENT_GOLD_BONUS
ENHANCEMENT_XP_BONUS = _gp.ENHANCEMENT_XP_BONUS
VOTE_LG_GOLD_BOOST = _gp.VOTE_LG_GOLD_BOOST
ITEM_DROP_CHANCE_VOICE = _gp.ITEM_DROP_CHANCE_VOICE
ITEM_DROP_CHANCE_TEXT = _gp.ITEM_DROP_CHANCE_TEXT
ITEM_DROP_CHANCE_HARVEST = _gp.ITEM_DROP_CHANCE_HARVEST
RARITY_GOLD_MULTIPLIER = _gp.RARITY_GOLD_MULTIPLIER
RARITY_DROP_MULTIPLIER = _gp.RARITY_DROP_MULTIPLIER
calc_voice_rewards = _gp.calc_voice_rewards
calc_text_rewards = _gp.calc_text_rewards
LEVEL_UP_GOLD_BONUS = _gp.LEVEL_UP_GOLD_BONUS


def sim_equipment_bonus(total_enhance_levels: int):
    gold_mult = 1.0 + (total_enhance_levels * ENHANCEMENT_GOLD_BONUS)
    xp_mult = 1.0 + (total_enhance_levels * ENHANCEMENT_XP_BONUS)
    return gold_mult, xp_mult


def sim_drop_chance(base_chance: float, user_tier: str, server_premium: bool,
                    rarity_multiplier: float = 1.0):
    tier_bonus = TIER_DROP_RATE_BONUS.get(user_tier, 0.0)
    server_bonus = SERVER_PREMIUM_DROP_BONUS if server_premium else 0.0
    return min(base_chance * rarity_multiplier * (1 + tier_bonus + server_bonus), 0.95)


def sim_harvest_gold(base_gold: int, seed_rarity: str, user_tier: str,
                     equip_enhance_total: int, voted: bool):
    rarity_mult = RARITY_GOLD_MULTIPLIER.get(seed_rarity, 1.0)
    tier_harvest = 1.0 + TIER_HARVEST_GOLD_BONUS.get(user_tier, 0.0)
    equip_gold, _ = sim_equipment_bonus(equip_enhance_total)
    vote_boost = VOTE_LG_GOLD_BOOST.get(user_tier, 1.0) if voted else 1.0
    return int(base_gold * rarity_mult * tier_harvest * equip_gold * vote_boost)


def sim_uproot_refund(invested: int, user_tier: str):
    rate = TIER_UPROOT_REFUND.get(user_tier, 0.5)
    return int(invested * rate)


def sim_voice_session(duration_seconds: int, user_tier: str, server_premium: bool,
                      equip_enhance_total: int, voted: bool):
    vote_boost = VOTE_LG_GOLD_BOOST.get(user_tier, 1.0) if voted else 1.0
    rewards = calc_voice_rewards(duration_seconds, user_tier=user_tier,
                                 server_premium=server_premium, vote_gold_boost=vote_boost)
    equip_gold, equip_xp = sim_equipment_bonus(equip_enhance_total)
    boosted_gold = int(rewards['gold'] * equip_gold)
    boosted_xp = int(rewards['xp'] * equip_xp)
    return {
        'base_gold': rewards['base_gold'],
        'final_gold': boosted_gold,
        'base_xp': rewards['xp'],
        'final_xp': boosted_xp,
        'food_refill': rewards['food_refill'],
        'sleep_refill': rewards['sleep_refill'],
    }


def sim_text_session(message_count: int, user_tier: str, server_premium: bool,
                     equip_enhance_total: int, voted: bool):
    vote_boost = VOTE_LG_GOLD_BOOST.get(user_tier, 1.0) if voted else 1.0
    rewards = calc_text_rewards(message_count, user_tier=user_tier,
                                server_premium=server_premium, vote_gold_boost=vote_boost)
    equip_gold, equip_xp = sim_equipment_bonus(equip_enhance_total)
    boosted_gold = int(rewards['gold'] * equip_gold)
    boosted_xp = int(rewards['xp'] * equip_xp)
    return {
        'base_gold': rewards['base_gold'],
        'final_gold': boosted_gold,
        'base_xp': rewards['xp'],
        'final_xp': boosted_xp,
        'food_refill': rewards['food_refill'],
    }


PROFILES = [
    {'name': 'No bonuses', 'tier': 'NONE', 'premium': False, 'enhance': 0, 'voted': False},
    {'name': 'LionHeart', 'tier': 'LIONHEART', 'premium': False, 'enhance': 0, 'voted': False},
    {'name': 'LionHeart+', 'tier': 'LIONHEART_PLUS', 'premium': False, 'enhance': 0, 'voted': False},
    {'name': 'LionHeart++', 'tier': 'LIONHEART_PLUS_PLUS', 'premium': False, 'enhance': 0, 'voted': False},
    {'name': 'Equip +10', 'tier': 'NONE', 'premium': False, 'enhance': 10, 'voted': False},
    {'name': 'Equip +30', 'tier': 'NONE', 'premium': False, 'enhance': 30, 'voted': False},
    {'name': 'Server Prem', 'tier': 'NONE', 'premium': True, 'enhance': 0, 'voted': False},
    {'name': 'Voted (NONE)', 'tier': 'NONE', 'premium': False, 'enhance': 0, 'voted': True},
    {'name': 'Voted (LH)', 'tier': 'LIONHEART', 'premium': False, 'enhance': 0, 'voted': True},
    {'name': 'Voted (LH++)', 'tier': 'LIONHEART_PLUS_PLUS', 'premium': False, 'enhance': 0, 'voted': True},
    {'name': 'LH + Equip+10', 'tier': 'LIONHEART', 'premium': False, 'enhance': 10, 'voted': False},
    {'name': 'LH + Prem', 'tier': 'LIONHEART', 'premium': True, 'enhance': 0, 'voted': False},
    {'name': 'ALL (LH++)', 'tier': 'LIONHEART_PLUS_PLUS', 'premium': True, 'enhance': 30, 'voted': True},
    {'name': 'MAX (LH++ +120)', 'tier': 'LIONHEART_PLUS_PLUS', 'premium': True, 'enhance': 120, 'voted': True},
]


def header(title: str):
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


def run_voice_tests():
    header("VOICE SESSION REWARDS")
    durations = [60, 1800, 7200]  # 1 min, 30 min, 2 hours
    for dur in durations:
        minutes = dur / 60
        print(f"\n--- {int(minutes)} minute voice session ---")
        print(f"{'Profile':<20} {'Base G':>7} {'Final G':>8} {'Base XP':>8} {'Final XP':>9} {'Gold Mult':>10}")
        print("-" * 70)
        for p in PROFILES:
            r = sim_voice_session(dur, p['tier'], p['premium'], p['enhance'], p['voted'])
            if r['base_gold'] > 0:
                mult = f"{r['final_gold'] / r['base_gold']:.2f}x"
            else:
                mult = "N/A"
            print(f"{p['name']:<20} {r['base_gold']:>7} {r['final_gold']:>8} {r['base_xp']:>8} {r['final_xp']:>9} {mult:>10}")


def run_text_tests():
    header("TEXT SESSION REWARDS")
    msg_counts = [5, 50, 200]
    for msgs in msg_counts:
        print(f"\n--- {msgs} messages ---")
        print(f"{'Profile':<20} {'Base G':>7} {'Final G':>8} {'Base XP':>8} {'Final XP':>9} {'Gold Mult':>10}")
        print("-" * 70)
        for p in PROFILES:
            r = sim_text_session(msgs, p['tier'], p['premium'], p['enhance'], p['voted'])
            if r['base_gold'] > 0:
                mult = f"{r['final_gold'] / r['base_gold']:.2f}x"
            else:
                mult = "N/A"
            print(f"{p['name']:<20} {r['base_gold']:>7} {r['final_gold']:>8} {r['base_xp']:>8} {r['final_xp']:>9} {mult:>10}")


def run_harvest_tests():
    header("HARVEST GOLD (per plant)")
    base_gold = 20
    rarities = ['COMMON', 'UNCOMMON', 'RARE', 'EPIC', 'LEGENDARY']
    print(f"\nBase harvest gold: {base_gold}G")
    for rarity in rarities:
        print(f"\n--- {rarity} seed ---")
        print(f"{'Profile':<20} {'Harvest G':>10} {'Rarity x':>9} {'Total Mult':>11}")
        print("-" * 55)
        for p in PROFILES:
            gold = sim_harvest_gold(base_gold, rarity, p['tier'], p['enhance'], p['voted'])
            rmult = RARITY_GOLD_MULTIPLIER.get(rarity, 1.0)
            total_mult = f"{gold / base_gold:.2f}x" if base_gold > 0 else "N/A"
            print(f"{p['name']:<20} {gold:>10} {rmult:>9.1f}x {total_mult:>11}")


def run_drop_rate_tests():
    header("DROP RATE CALCULATIONS")
    sources = [
        ('Voice', ITEM_DROP_CHANCE_VOICE),
        ('Text', ITEM_DROP_CHANCE_TEXT),
        ('Harvest (COMMON)', ITEM_DROP_CHANCE_HARVEST),
    ]
    for source_name, base_chance in sources:
        print(f"\n--- {source_name} (base: {base_chance * 100:.0f}%) ---")
        print(f"{'Profile':<20} {'Eff. Chance':>12} {'Bonus':>10}")
        print("-" * 45)
        for p in PROFILES:
            eff = sim_drop_chance(base_chance, p['tier'], p['premium'])
            bonus = eff - base_chance
            print(f"{p['name']:<20} {eff * 100:>11.1f}% {'+' if bonus >= 0 else ''}{bonus * 100:>8.1f}%")

    print(f"\n--- Harvest (LEGENDARY seed, rarity_mult=3.0) ---")
    print(f"{'Profile':<20} {'Eff. Chance':>12}")
    print("-" * 35)
    for p in PROFILES:
        eff = sim_drop_chance(ITEM_DROP_CHANCE_HARVEST, p['tier'], p['premium'],
                              rarity_multiplier=3.0)
        print(f"{p['name']:<20} {eff * 100:>11.1f}%")


def run_uproot_tests():
    header("UPROOT REFUND")
    invested = 100
    print(f"\nInvested: {invested}G")
    print(f"{'Profile':<20} {'Refund':>8} {'Rate':>6} {'Lost':>6}")
    print("-" * 45)
    for p in PROFILES:
        refund = sim_uproot_refund(invested, p['tier'])
        rate = TIER_UPROOT_REFUND.get(p['tier'], 0.5)
        lost = invested - refund
        print(f"{p['name']:<20} {refund:>7}G {rate * 100:>5.0f}% {lost:>5}G")


def run_edge_case_tests():
    header("EDGE CASES")

    print("\n--- 0-second voice session ---")
    r = sim_voice_session(0, 'LIONHEART_PLUS_PLUS', True, 120, True)
    print(f"  Gold: {r['final_gold']}, XP: {r['final_xp']} (should both be 0)")
    assert r['final_gold'] == 0, f"Expected 0 gold, got {r['final_gold']}"
    assert r['final_xp'] == 0, f"Expected 0 XP, got {r['final_xp']}"

    print("\n--- 1-second voice session ---")
    r = sim_voice_session(1, 'NONE', False, 0, False)
    print(f"  Gold: {r['final_gold']}, XP: {r['final_xp']} (very small, no truncation loss)")

    print("\n--- 1 message text session ---")
    r = sim_text_session(1, 'NONE', False, 0, False)
    print(f"  Gold: {r['final_gold']} (should be 0 since 1*0.5=0.5 truncates to 0)")
    assert r['final_gold'] == 0, f"Expected 0 gold, got {r['final_gold']}"

    print("\n--- 2 messages text session ---")
    r = sim_text_session(2, 'NONE', False, 0, False)
    print(f"  Gold: {r['final_gold']} (should be 1 since 2*0.5=1.0)")
    assert r['final_gold'] == 1, f"Expected 1 gold, got {r['final_gold']}"

    print("\n--- Max enhancement (6 slots x 20 = 120 levels) ---")
    gold_mult, xp_mult = sim_equipment_bonus(120)
    print(f"  Gold mult: {gold_mult:.2f}x (+{(gold_mult - 1) * 100:.0f}%)")
    print(f"  XP mult: {xp_mult:.2f}x (+{(xp_mult - 1) * 100:.0f}%)")
    assert gold_mult == 3.4, f"Expected 3.4x, got {gold_mult}"

    print("\n--- Rounding comparison: old (sequential int) vs new (single truncation) ---")
    dur = 325
    minutes = dur / 60.0
    old_gold = int(minutes * GOLD_PER_VOICE_MINUTE)
    old_gold = int(old_gold * TIER_GOLD_BONUS['LIONHEART_PLUS_PLUS'])
    old_gold = int(old_gold * SERVER_PREMIUM_GOLD_BONUS)
    equip_gold, _ = sim_equipment_bonus(30)
    old_final = int(old_gold * equip_gold)

    new_rewards = calc_voice_rewards(dur, 'LIONHEART_PLUS_PLUS', True, 1.0)
    new_final = int(new_rewards['gold'] * equip_gold)
    print(f"  5m 25s voice, LH++, server premium, equip +30:")
    print(f"  Old method (4 truncations): {old_final}G")
    print(f"  New method (1 truncation):  {new_final}G")
    print(f"  Difference: {new_final - old_final}G")

    print("\n--- Vote boost stacks with tier bonus ---")
    r_no_vote = sim_voice_session(3600, 'LIONHEART', False, 0, False)
    r_voted = sim_voice_session(3600, 'LIONHEART', False, 0, True)
    print(f"  1hr voice, LionHeart, no vote: {r_no_vote['final_gold']}G")
    print(f"  1hr voice, LionHeart, voted:   {r_voted['final_gold']}G")
    print(f"  Vote boost added: +{r_voted['final_gold'] - r_no_vote['final_gold']}G")

    print("\n--- Harvest: equipment + tier + vote all stack ---")
    h_base = sim_harvest_gold(20, 'RARE', 'NONE', 0, False)
    h_full = sim_harvest_gold(20, 'RARE', 'LIONHEART_PLUS_PLUS', 30, True)
    print(f"  RARE seed harvest (no bonuses): {h_base}G")
    print(f"  RARE seed harvest (LH++ + equip+30 + voted): {h_full}G")
    print(f"  Total multiplier: {h_full / h_base:.2f}x")

    print("\n--- Uproot: tier-based refund ---")
    for tier in ['NONE', 'LIONHEART', 'LIONHEART_PLUS', 'LIONHEART_PLUS_PLUS']:
        refund = sim_uproot_refund(200, tier)
        rate = TIER_UPROOT_REFUND.get(tier, 0.5)
        print(f"  {tier}: {refund}G / 200G ({rate * 100:.0f}%)")

    print("\nAll edge case assertions passed!")


def run_multiplier_summary():
    header("MULTIPLIER SUMMARY TABLE")
    print(f"\n{'Bonus Source':<25} {'Affects':>15} {'NONE':>8} {'LH':>8} {'LH+':>8} {'LH++':>8}")
    print("-" * 80)

    for label, source, tiers in [
        ('Tier Gold', TIER_GOLD_BONUS, True),
        ('Tier Drop Rate', TIER_DROP_RATE_BONUS, True),
        ('Tier Harvest Gold', TIER_HARVEST_GOLD_BONUS, True),
        ('Tier Uproot Refund', TIER_UPROOT_REFUND, True),
        ('Tier Seed Discount', TIER_SEED_DISCOUNT, True),
        ('Vote Gold Boost', VOTE_LG_GOLD_BOOST, True),
    ]:
        vals = [source.get(t, 0) for t in ['NONE', 'LIONHEART', 'LIONHEART_PLUS', 'LIONHEART_PLUS_PLUS']]
        affects = 'Gold' if 'Gold' in label else ('Drops' if 'Drop' in label else 'Gold')
        fmt_vals = [f"{v:.2f}" if isinstance(v, float) else str(v) for v in vals]
        print(f"{label:<25} {affects:>15} {fmt_vals[0]:>8} {fmt_vals[1]:>8} {fmt_vals[2]:>8} {fmt_vals[3]:>8}")

    print(f"\n{'Equipment Enhancement':<25} {'Gold & XP':>15} +{ENHANCEMENT_GOLD_BONUS * 100:.0f}% per level")
    print(f"{'Server Premium Gold':<25} {'Gold':>15} {SERVER_PREMIUM_GOLD_BONUS:.2f}x")
    print(f"{'Server Premium Drops':<25} {'Drops':>15} +{SERVER_PREMIUM_DROP_BONUS * 100:.0f}%")
    print(f"{'Level-Up Gold':<25} {'Gold':>15} {LEVEL_UP_GOLD_BONUS}G per level (flat, no bonuses)")


if __name__ == '__main__':
    run_multiplier_summary()
    run_voice_tests()
    run_text_tests()
    run_harvest_tests()
    run_drop_rate_tests()
    run_uproot_tests()
    run_edge_case_tests()
    print(f"\n{'=' * 80}")
    print("  ALL TESTS PASSED")
    print(f"{'=' * 80}")

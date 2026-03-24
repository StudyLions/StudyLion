# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: Unit tests for LionGotchi gameplay logic -- rewards,
#          leveling, mood, glow, drops, and bonus formatting
# ============================================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from modules.liongotchi.gameplay import (
    calc_voice_rewards,
    calc_text_rewards,
    calc_mood,
    check_level_up,
    xp_for_level,
    calc_glow_tier,
    calc_glow_intensity,
    format_bonus_summary,
    format_bonus_footer,
    pick_drop_rarity,
    roll_item_drop,
    GOLD_PER_VOICE_MINUTE,
    GOLD_PER_TEXT_MESSAGE,
    XP_PER_VOICE_MINUTE,
    XP_PER_TEXT_MESSAGE,
    TIER_GOLD_BONUS,
    SERVER_PREMIUM_GOLD_BONUS,
    VOICE_NEED_REFILL_MINUTES,
    VOICE_NEED_REFILL_MAX,
    TEXT_NEED_REFILL_MESSAGES,
    TEXT_NEED_REFILL_MAX,
)


class TestXpForLevel:
    def test_level_1(self):
        assert xp_for_level(1) == 100

    def test_level_10(self):
        assert xp_for_level(10) == 1000

    def test_level_0(self):
        assert xp_for_level(0) == 0

    def test_scales_linearly(self):
        for lvl in range(1, 50):
            assert xp_for_level(lvl) == lvl * 100


class TestCheckLevelUp:
    def test_no_level_up(self):
        new_lvl, remaining, gained = check_level_up(1, 50)
        assert new_lvl == 1
        assert remaining == 50
        assert gained == 0

    def test_single_level_up(self):
        new_lvl, remaining, gained = check_level_up(1, 100)
        assert new_lvl == 2
        assert remaining == 0
        assert gained == 1

    def test_multi_level_up(self):
        new_lvl, remaining, gained = check_level_up(1, 350)
        # Level 1: needs 100 XP -> 250 left, now level 2
        # Level 2: needs 200 XP -> 50 left, now level 3
        # Level 3: needs 300 XP -> not enough
        assert new_lvl == 3
        assert remaining == 50
        assert gained == 2

    def test_exact_boundary(self):
        new_lvl, remaining, gained = check_level_up(5, 500)
        assert new_lvl == 6
        assert remaining == 0
        assert gained == 1

    def test_zero_xp(self):
        new_lvl, remaining, gained = check_level_up(10, 0)
        assert new_lvl == 10
        assert remaining == 0
        assert gained == 0


class TestCalcMood:
    def test_all_max(self):
        assert calc_mood(8, 8, 8) == 8

    def test_all_zero(self):
        assert calc_mood(0, 0, 0) == 0

    def test_mixed(self):
        assert calc_mood(6, 3, 3) == 4  # avg = 12/3 = 4

    def test_rounding_down(self):
        assert calc_mood(5, 5, 4) == 4  # 14/3 = 4.66 -> 4 (int div)

    def test_range_bounds(self):
        for f in range(9):
            for b in range(9):
                for s in range(9):
                    mood = calc_mood(f, b, s)
                    assert 0 <= mood <= 8


class TestCalcVoiceRewards:
    def test_basic_rewards(self):
        rewards = calc_voice_rewards(3600)  # 1 hour
        assert rewards['gold'] > 0
        assert rewards['xp'] > 0

    def test_gold_calculation(self):
        rewards = calc_voice_rewards(600)  # 10 minutes
        minutes = 600 / 60.0
        expected_gold = int(minutes * GOLD_PER_VOICE_MINUTE)
        assert rewards['gold'] == expected_gold

    def test_xp_calculation(self):
        rewards = calc_voice_rewards(600)
        minutes = 600 / 60.0
        expected_xp = int(minutes * XP_PER_VOICE_MINUTE)
        assert rewards['xp'] == expected_xp

    def test_zero_duration(self):
        rewards = calc_voice_rewards(0)
        assert rewards['gold'] == 0
        assert rewards['xp'] == 0

    def test_tier_bonus(self):
        base = calc_voice_rewards(3600)
        boosted = calc_voice_rewards(3600, user_tier='LIONHEART_PLUS_PLUS')
        assert boosted['gold'] > base['gold']

    def test_server_premium_bonus(self):
        base = calc_voice_rewards(3600)
        premium = calc_voice_rewards(3600, server_premium=True)
        assert premium['gold'] > base['gold']

    def test_vote_boost(self):
        base = calc_voice_rewards(3600)
        voted = calc_voice_rewards(3600, vote_gold_boost=1.5)
        assert voted['gold'] > base['gold']

    def test_need_refill(self):
        rewards_short = calc_voice_rewards(60)  # 1 minute
        assert rewards_short['food_refill'] == 0
        assert rewards_short['bath_refill'] == 0
        assert rewards_short['sleep_refill'] == 0

        rewards_long = calc_voice_rewards(VOICE_NEED_REFILL_MINUTES * 60 * 5)
        assert rewards_long['food_refill'] == VOICE_NEED_REFILL_MAX

    def test_need_refill_cap(self):
        rewards = calc_voice_rewards(VOICE_NEED_REFILL_MINUTES * 60 * 100)
        assert rewards['food_refill'] <= VOICE_NEED_REFILL_MAX

    def test_all_rewards_non_negative(self):
        for duration in [0, 1, 60, 600, 3600, 36000]:
            rewards = calc_voice_rewards(duration)
            assert rewards['gold'] >= 0
            assert rewards['xp'] >= 0
            assert rewards['food_refill'] >= 0


class TestCalcTextRewards:
    def test_basic_rewards(self):
        rewards = calc_text_rewards(10)
        assert rewards['gold'] > 0
        assert rewards['xp'] > 0

    def test_gold_calculation(self):
        rewards = calc_text_rewards(10)
        expected_gold = int(10 * GOLD_PER_TEXT_MESSAGE)
        assert rewards['gold'] == expected_gold

    def test_xp_calculation(self):
        rewards = calc_text_rewards(10)
        expected_xp = int(10 * XP_PER_TEXT_MESSAGE)
        assert rewards['xp'] == expected_xp

    def test_zero_messages(self):
        rewards = calc_text_rewards(0)
        assert rewards['gold'] == 0
        assert rewards['xp'] == 0

    def test_tier_bonus(self):
        base = calc_text_rewards(100)
        boosted = calc_text_rewards(100, user_tier='LIONHEART_PLUS_PLUS')
        assert boosted['gold'] > base['gold']

    def test_need_refill(self):
        rewards_small = calc_text_rewards(5)
        assert rewards_small['food_refill'] == 0

        rewards_large = calc_text_rewards(TEXT_NEED_REFILL_MESSAGES * 5)
        assert rewards_large['food_refill'] == TEXT_NEED_REFILL_MAX

    def test_need_refill_cap(self):
        rewards = calc_text_rewards(TEXT_NEED_REFILL_MESSAGES * 100)
        assert rewards['food_refill'] <= TEXT_NEED_REFILL_MAX


class TestCalcGlowTier:
    def test_no_enhancement(self):
        assert calc_glow_tier(0, 0) == 'none'

    def test_negative(self):
        assert calc_glow_tier(-1, 5.0) == 'none'

    def test_celestial(self):
        assert calc_glow_tier(10, 70.0) == 'celestial'  # avg 7.0

    def test_diamond(self):
        assert calc_glow_tier(10, 50.0) == 'diamond'  # avg 5.0

    def test_gold(self):
        assert calc_glow_tier(10, 30.0) == 'gold'  # avg 3.0

    def test_silver(self):
        assert calc_glow_tier(10, 20.0) == 'silver'  # avg 2.0

    def test_bronze(self):
        assert calc_glow_tier(10, 5.0) == 'bronze'  # avg 0.5


class TestCalcGlowIntensity:
    def test_zero(self):
        assert calc_glow_intensity(0) == 0

    def test_low(self):
        assert calc_glow_intensity(3) == 0

    def test_level_4(self):
        assert calc_glow_intensity(4) == 1

    def test_level_8(self):
        assert calc_glow_intensity(8) == 2

    def test_level_13(self):
        assert calc_glow_intensity(13) == 3

    def test_very_high(self):
        assert calc_glow_intensity(20) == 3


class TestDropMechanics:
    def test_roll_item_drop_zero(self):
        assert roll_item_drop(0.0) is False

    def test_roll_item_drop_one(self):
        assert roll_item_drop(1.0) is True

    def test_pick_drop_rarity_returns_valid(self):
        valid = {'COMMON', 'UNCOMMON', 'RARE', 'EPIC', 'LEGENDARY', 'MYTHICAL'}
        for _ in range(100):
            rarity = pick_drop_rarity()
            assert rarity in valid

    def test_pick_drop_rarity_custom_weights(self):
        result = pick_drop_rarity({'LEGENDARY': 100})
        assert result == 'LEGENDARY'


class TestBonusFormatting:
    def test_format_bonus_summary_empty(self):
        bonuses = {'user_tier': 'NONE', 'tier_gold': 1.0, 'equip_gold': 1.0,
                   'equip_drop': 0.0, 'voted': False, 'vote_gold': 1.0,
                   'server_premium': False, 'server_gold': 1.0,
                   'tier_drop': 0.0, 'server_drop': 0.0, 'tier_harvest': 0.0}
        result = format_bonus_summary(bonuses)
        assert result == ""

    def test_format_bonus_summary_with_tier(self):
        bonuses = {'user_tier': 'LIONHEART', 'tier_gold': 1.15, 'equip_gold': 1.0,
                   'equip_drop': 0.0, 'voted': False, 'vote_gold': 1.0,
                   'server_premium': False, 'server_gold': 1.0,
                   'tier_drop': 0.15, 'server_drop': 0.0, 'tier_harvest': 0.15}
        result = format_bonus_summary(bonuses)
        assert "LionHeart" in result
        assert "+15%" in result

    def test_format_bonus_footer_no_bonuses(self):
        bonuses = {'total_gold_mult': 1.0, 'total_xp_mult': 1.0, 'total_drop_bonus': 0.0}
        result = format_bonus_footer(bonuses)
        assert "Enhance" in result

    def test_format_bonus_footer_with_gold(self):
        bonuses = {'total_gold_mult': 1.5, 'total_xp_mult': 1.0, 'total_drop_bonus': 0.0}
        result = format_bonus_footer(bonuses)
        assert "+50% Gold" in result

# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: Unit tests for pomodoro gamification functions
# ============================================================
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from modules.pomodoro.gamification import (
    get_focus_power_multiplier,
    _parse_date,
    _iso_week,
    FOCUS_POWER_MULTIPLIERS,
)


class TestGetFocusPowerMultiplier:
    def test_zero(self):
        assert get_focus_power_multiplier(0) == 1.0

    def test_level_1(self):
        assert get_focus_power_multiplier(1) == 1.2

    def test_level_3(self):
        assert get_focus_power_multiplier(3) == 1.5

    def test_level_5(self):
        assert get_focus_power_multiplier(5) == 2.0

    def test_above_max(self):
        assert get_focus_power_multiplier(10) == 2.0

    def test_large_value(self):
        assert get_focus_power_multiplier(999) == 2.0

    def test_all_levels_defined(self):
        for level in range(6):
            result = get_focus_power_multiplier(level)
            assert result == FOCUS_POWER_MULTIPLIERS[level]

    def test_multipliers_non_decreasing(self):
        prev = 0.0
        for level in range(6):
            current = get_focus_power_multiplier(level)
            assert current >= prev
            prev = current


class TestParseDate:
    def test_none(self):
        assert _parse_date(None) is None

    def test_date_object(self):
        d = date(2026, 3, 20)
        assert _parse_date(d) == d

    def test_iso_string(self):
        result = _parse_date("2026-03-20")
        assert result == date(2026, 3, 20)

    def test_invalid_string(self):
        assert _parse_date("not-a-date") is None

    def test_integer(self):
        assert _parse_date(12345) is None


class TestIsoWeek:
    def test_basic(self):
        d = date(2026, 3, 20)  # a Friday
        year, week = _iso_week(d)
        assert year == 2026
        assert isinstance(week, int)
        assert 1 <= week <= 53

    def test_new_year(self):
        d = date(2026, 1, 1)
        year, week = _iso_week(d)
        assert isinstance(year, int)
        assert isinstance(week, int)

    def test_end_of_year(self):
        d = date(2025, 12, 31)
        year, week = _iso_week(d)
        assert isinstance(year, int)

    def test_same_week(self):
        d1 = date(2026, 3, 16)  # Monday
        d2 = date(2026, 3, 20)  # Friday
        assert _iso_week(d1) == _iso_week(d2)

    def test_different_weeks(self):
        d1 = date(2026, 3, 15)  # Sunday (end of previous week)
        d2 = date(2026, 3, 16)  # Monday (start of next week)
        assert _iso_week(d1) != _iso_week(d2)

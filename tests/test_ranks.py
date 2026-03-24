# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: Unit tests for rank utility functions
# ============================================================
from core.data import RankType
from modules.ranks.utils import stat_data_to_value, stat_value_to_data, format_stat_range


class TestStatDataToValue:
    def test_voice_conversion(self):
        data = 360000  # 100 hours in centiseconds (ish)
        value = stat_data_to_value(RankType.VOICE, data)
        assert isinstance(value, float)
        assert value == round(360000 / 36) / 100  # 100.0

    def test_voice_small(self):
        value = stat_data_to_value(RankType.VOICE, 3600)
        assert value == round(3600 / 36) / 100  # 1.0

    def test_voice_zero(self):
        assert stat_data_to_value(RankType.VOICE, 0) == 0.0

    def test_message_passthrough(self):
        assert stat_data_to_value(RankType.MESSAGE, 42) == 42

    def test_xp_passthrough(self):
        assert stat_data_to_value(RankType.XP, 1000) == 1000


class TestStatValueToData:
    def test_voice_roundtrip(self):
        original_hours = 5.0
        data = stat_value_to_data(RankType.VOICE, original_hours)
        assert data == int(round(5.0 * 100) * 36)  # 18000

    def test_message_passthrough(self):
        assert stat_value_to_data(RankType.MESSAGE, 100) == 100

    def test_xp_passthrough(self):
        assert stat_value_to_data(RankType.XP, 500) == 500

    def test_voice_roundtrip_consistency(self):
        for hours in [0, 0.5, 1.0, 2.5, 10.0, 100.0]:
            data = stat_value_to_data(RankType.VOICE, hours)
            back = stat_data_to_value(RankType.VOICE, data)
            assert abs(back - hours) < 0.02, f"Roundtrip failed for {hours}: got {back}"


class TestFormatStatRange:
    def test_voice_even_hours(self):
        result = format_stat_range(RankType.VOICE, 3600, 7200, short=True)
        assert "1 - 2 hrs" == result

    def test_voice_uneven(self):
        result = format_stat_range(RankType.VOICE, 3700, 7300, short=True)
        assert " - " in result

    def test_voice_no_end(self):
        result = format_stat_range(RankType.VOICE, 3600, short=True)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_message_range(self):
        result = format_stat_range(RankType.MESSAGE, 100, 200, short=True)
        assert result == "100 - 200 msgs"

    def test_message_no_end(self):
        result = format_stat_range(RankType.MESSAGE, 50, short=True)
        assert result == "50 msgs"

    def test_xp_range(self):
        result = format_stat_range(RankType.XP, 500, 1000, short=True)
        assert result == "500 - 1000 XP"

    def test_xp_no_end(self):
        result = format_stat_range(RankType.XP, 1000, short=True)
        assert result == "1000 XP"

    def test_message_long_format(self):
        result = format_stat_range(RankType.MESSAGE, 5, 10, short=False)
        assert result == "5 - 10 messages"

    def test_voice_long_even_hours(self):
        result = format_stat_range(RankType.VOICE, 3600, 7200, short=False)
        assert "hours" in result

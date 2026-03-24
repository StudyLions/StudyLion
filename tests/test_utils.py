# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: Unit tests for pure utility functions in utils/lib.py
# ============================================================
import datetime
import pytest


def test_strfdelta_basic():
    from utils.lib import strfdelta
    delta = datetime.timedelta(hours=2, minutes=30)
    result = strfdelta(delta, short=True)
    assert "2h" in result
    assert "30m" in result


def test_strfdelta_zero():
    from utils.lib import strfdelta
    delta = datetime.timedelta(0)
    result = strfdelta(delta, short=True)
    assert result.strip() != ""


def test_strfdelta_with_days():
    from utils.lib import strfdelta
    delta = datetime.timedelta(days=3, hours=5, minutes=15)
    result = strfdelta(delta, short=True)
    assert "3d" in result
    assert "5h" in result


def test_strfdelta_long_format():
    from utils.lib import strfdelta
    delta = datetime.timedelta(hours=1, minutes=1)
    result = strfdelta(delta, short=False)
    assert "hour" in result
    assert "minute" in result


def test_strfdelta_plural_long():
    from utils.lib import strfdelta
    delta = datetime.timedelta(hours=2, minutes=5)
    result = strfdelta(delta, short=False)
    assert "hours" in result
    assert "minutes" in result


def test_strfdur_basic():
    from utils.lib import strfdur
    result = strfdur(3661, short=True)
    assert "1h" in result
    assert "1m" in result
    assert "1s" in result


def test_strfdur_zero():
    from utils.lib import strfdur
    result = strfdur(0, short=True)
    assert "0s" in result


def test_strfdur_hours_only():
    from utils.lib import strfdur
    result = strfdur(7200, short=True)
    assert "2h" in result
    assert "m" not in result


def test_strfdur_with_days():
    from utils.lib import strfdur
    result = strfdur(90061, short=True, show_days=True)
    assert "1d" in result
    assert "1h" in result


def test_strfdur_long_format():
    from utils.lib import strfdur
    result = strfdur(3661, short=False)
    assert "hour" in result
    assert "minute" in result
    assert "second" in result


def test_parse_dur_basic():
    from utils.lib import _parse_dur
    assert _parse_dur("1h 30m") == 5400
    assert _parse_dur("2d") == 172800
    assert _parse_dur("1h") == 3600
    assert _parse_dur("30m") == 1800
    assert _parse_dur("45s") == 45


def test_parse_dur_combined():
    from utils.lib import _parse_dur
    assert _parse_dur("1d 2h 30m 15s") == 86400 + 7200 + 1800 + 15


def test_parse_dur_empty():
    from utils.lib import _parse_dur
    assert _parse_dur("") == 0


def test_substitute_ranges_basic():
    from utils.lib import substitute_ranges
    result = substitute_ranges("1-3")
    assert "1,2,3" in result


def test_substitute_ranges_mixed():
    from utils.lib import substitute_ranges
    result = substitute_ranges("1-3, 5, 7-9")
    assert "1,2,3" in result
    assert "5" in result
    assert "7,8,9" in result


def test_substitute_ranges_too_large():
    from utils.lib import substitute_ranges
    with pytest.raises(ValueError, match="too large"):
        substitute_ranges("1-5000", max_range=1000)


def test_parse_ranges_basic():
    from utils.lib import parse_ranges
    result = parse_ranges("1, 2, 3")
    assert result == [1, 2, 3]


def test_parse_ranges_with_range():
    from utils.lib import parse_ranges
    result = parse_ranges("1-3, 5")
    assert result == [1, 2, 3, 5]


def test_parse_ranges_invalid():
    from utils.lib import parse_ranges
    with pytest.raises(ValueError):
        parse_ranges("abc, 1, 2")


def test_parse_ranges_ignore_errors():
    from utils.lib import parse_ranges
    result = parse_ranges("abc, 1, 2", ignore_errors=True)
    assert result == [1, 2]


def test_tabulate_basic():
    from utils.lib import tabulate
    result = tabulate(("key1", "val1"), ("longer_key", "val2"))
    assert len(result) == 2
    for row in result:
        assert isinstance(row, str)


def test_tabulate_multiline():
    from utils.lib import tabulate
    result = tabulate(("key", "line1\r\nline2"))
    assert len(result) == 1
    assert "\n" in result[0]


def test_split_text_short():
    from utils.lib import split_text
    text = "Hello World"
    result = split_text(text)
    assert len(result) == 1


def test_split_text_long():
    from utils.lib import split_text
    text = "A" * 5000
    result = split_text(text, blocksize=2000)
    assert len(result) > 1
    for block in result:
        assert len(block) <= 2000


def test_split_text_no_code():
    from utils.lib import split_text
    text = "Hello World"
    result = split_text(text, code=False)
    assert "```" not in result[0]


def test_paginate_list_basic():
    from utils.lib import paginate_list
    items = [f"Item {i}" for i in range(5)]
    result = paginate_list(items)
    assert len(result) == 1
    assert "```" in result[0]


def test_paginate_list_multiple_pages():
    from utils.lib import paginate_list
    items = [f"Item {i}" for i in range(50)]
    result = paginate_list(items, block_length=10)
    assert len(result) == 5


def test_paginate_list_with_title():
    from utils.lib import paginate_list
    items = ["a", "b", "c"]
    result = paginate_list(items, title="My List")
    assert "My List" in result[0]


def test_shard_of():
    from utils.lib import shard_of
    guild_id = 780195610154237993
    result = shard_of(32, guild_id)
    assert 0 <= result < 32
    assert result == (guild_id >> 22) % 32


def test_shard_of_single():
    from utils.lib import shard_of
    assert shard_of(1, 12345) == 0


def test_jumpto():
    from utils.lib import jumpto
    result = jumpto(111, 222, 333)
    assert "111" in result
    assert "222" in result
    assert "333" in result
    assert result.startswith("https://discord.com/channels/")


def test_multiple_replace():
    from utils.lib import multiple_replace
    result = multiple_replace("hello world foo", {"hello": "hi", "foo": "bar"})
    assert result == "hi world bar"


def test_multiple_replace_empty():
    from utils.lib import multiple_replace
    result = multiple_replace("hello", {})
    assert result == "hello"


def test_replace_multiple():
    from utils.lib import replace_multiple
    result = replace_multiple("{name} is {age}", {"{name}": "Alice", "{age}": "30"})
    assert "Alice" in result
    assert "30" in result


class TestConvDateString:
    def test_days(self):
        from utils.lib import convdatestring
        result = convdatestring("2d")
        assert result == datetime.timedelta(days=2)

    def test_hours(self):
        from utils.lib import convdatestring
        result = convdatestring("3h")
        assert result == datetime.timedelta(hours=3)

    def test_minutes(self):
        from utils.lib import convdatestring
        result = convdatestring("30m")
        assert result == datetime.timedelta(minutes=30)

    def test_combined(self):
        from utils.lib import convdatestring
        result = convdatestring("1d2h30m")
        assert result == datetime.timedelta(days=1, hours=2, minutes=30)

from datetime import timedelta
import pytz


def extract_weekid(timestamp) -> int:
    """
    Extract a weekid from a given timestamp with timezone.

    Weekids are calculated by first stripping the timezone,
    then extracting the UTC timestamp of the start of the week.
    """
    day_start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    return int(week_start.replace(tzinfo=pytz.utc).timestamp())


def extract_monthid(timestamp) -> int:
    """
    Extract a monthid from a given timestamp with timezone.

    Monthids are calculated by first stripping the timezone,
    then extracting the UTC timestamp from the start of the month.
    """
    month_start = timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(month_start.replace(tzinfo=pytz.utc).timestamp())


def apply_week_offset(timestamp, offset):
    return timestamp - timedelta(weeks=offset)


def apply_month_offset(timestamp, offset):
    raw_month = timestamp.month - offset - 1
    timestamp = timestamp.replace(
        year=timestamp.year + int(raw_month // 12),
        month=(raw_month % 12) + 1
    )
    return timestamp


def week_difference(ts_1, ts_2):
    return int((ts_2 - ts_1).total_seconds() // (7*24*3600))


def month_difference(ts_1, ts_2):
    return (ts_2.month - ts_1.month) + (ts_2.year - ts_1.year) * 12

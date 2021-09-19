import datetime


def utc_now():
    """
    Return the current timezone-aware utc timestamp.
    """
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

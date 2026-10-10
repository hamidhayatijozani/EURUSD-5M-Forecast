"""Conservative market-session classification for expected FX weekend closure.

This is not a full holiday calendar. Holidays or unexplained stale feeds remain
unconfirmed and must not be silently classified as a closed market.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def expected_weekend_closure(now: datetime) -> bool:
    """Return true only for the conventional FX weekend closure window.

    Spot FX is conventionally closed from Friday 17:00 New York time until
    Sunday 17:00 New York time. This deliberately does not infer public
    holidays from stale data.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(NEW_YORK)
    if local.weekday() == 5:  # Saturday
        return True
    if local.weekday() == 4 and local.time() >= time(17, 0):
        return True
    if local.weekday() == 6 and local.time() < time(17, 0):
        return True
    return False

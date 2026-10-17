"""Conservative market-session classification for expected FX weekend closure.

This is not a full holiday calendar. Holidays or unexplained stale feeds remain
unconfirmed and must not be silently classified as a closed market.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def expected_weekend_closure(now: datetime) -> bool:
    """Return true only for the conventional FX weekend closure window."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(NEW_YORK)
    if local.weekday() == 5:
        return True
    if local.weekday() == 4 and local.time() >= time(17, 0):
        return True
    if local.weekday() == 6 and local.time() < time(17, 0):
        return True
    return False


def session_snapshot(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    closed = expected_weekend_closure(now)
    local = now.astimezone(NEW_YORK)
    if closed and local.weekday() == 5:
        reason = "WEEKEND_SATURDAY"
    elif closed and local.weekday() == 4:
        reason = "WEEKEND_AFTER_FRIDAY_1700_NEW_YORK"
    elif closed:
        reason = "WEEKEND_BEFORE_SUNDAY_1700_NEW_YORK"
    else:
        reason = "NOT_IN_SCHEDULED_WEEKEND_CLOSURE"
    return {
        "schema": "hamidcognition.fx_session.v1",
        "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "timezone": "America/New_York",
        "market_open_by_schedule": not closed,
        "reason": reason,
        "weekly_close": "Friday 17:00 America/New_York",
        "weekly_open": "Sunday 17:00 America/New_York",
        "broker_holiday_calendar_checked": False,
        "live_quote_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output")
    parser.add_argument("--json-path")
    args = parser.parse_args()
    snapshot = session_snapshot()
    print(json.dumps(snapshot, sort_keys=True))
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(f"market_open={'true' if snapshot['market_open_by_schedule'] else 'false'}\n")
            handle.write(f"market_reason={snapshot['reason']}\n")
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

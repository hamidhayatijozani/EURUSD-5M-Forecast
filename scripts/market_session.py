"""Broker-configurable FX spot session gate.

Default schedule: open Sunday 21:00 UTC, close Friday 21:00 UTC.
This is an operational guard, not an exchange calendar; broker holidays and
instrument-specific hours must be supplied separately where applicable.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def market_status(now: datetime, open_hour_utc: int = 21, close_hour_utc: int = 21) -> dict:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    weekday = now.weekday()  # Mon=0 ... Sun=6
    minute = now.hour * 60 + now.minute
    open_minute = open_hour_utc * 60
    close_minute = close_hour_utc * 60

    # The weekly FX window is Sunday open -> Friday close in UTC.
    if weekday == 5:
        opened, reason = False, "WEEKEND_SATURDAY"
    elif weekday == 6 and minute < open_minute:
        opened, reason = False, "WAITING_FOR_SUNDAY_OPEN"
    elif weekday == 4 and minute >= close_minute:
        opened, reason = False, "WEEKEND_AFTER_FRIDAY_CLOSE"
    else:
        opened, reason = True, "SCHEDULED_OPEN"

    return {
        "schema": "hamidcognition.fx_session.v1",
        "market_open_by_schedule": opened,
        "reason": reason,
        "checked_at_utc": now.isoformat(),
        "timezone": "UTC",
        "weekly_open": f"Sunday {open_hour_utc:02d}:00 UTC",
        "weekly_close": f"Friday {close_hour_utc:02d}:00 UTC",
        "broker_holiday_calendar_checked": False,
        "source_is_live_quote": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output")
    parser.add_argument("--json-path")
    args = parser.parse_args()
    open_hour = int(os.getenv("FX_WEEKLY_OPEN_UTC_HOUR", "21"))
    close_hour = int(os.getenv("FX_WEEKLY_CLOSE_UTC_HOUR", "21"))
    if not 0 <= open_hour <= 23 or not 0 <= close_hour <= 23:
        raise SystemExit("FX session hours must be 0..23 UTC")
    status = market_status(datetime.now(timezone.utc), open_hour, close_hour)
    payload = json.dumps(status, sort_keys=True)
    print(payload)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(f"market_open={'true' if status['market_open_by_schedule'] else 'false'}\n")
            f.write(f"market_reason={status['reason']}\n")
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

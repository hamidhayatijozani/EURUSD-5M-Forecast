"""Probe the historical EUR/USD research dataset and emit explicit freshness evidence.

This source is a static historical dataset, not a live market feed. A successful
HTTP fetch must never be interpreted as a fresh/live market observation.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from claimlab.ingestion import GitHubEURUSD5mHistoricalClient

FRESHNESS_THRESHOLD_SECONDS = 15 * 60


def parse_timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main():
    candle = GitHubEURUSD5mHistoricalClient().fetch_latest_eurusd_candle()
    if candle is None:
        raise SystemExit("HISTORICAL_MARKET_DATA_UNAVAILABLE")

    observed_at = datetime.now(timezone.utc)
    candle_ts = parse_timestamp(candle["timestamp"])
    age_seconds = max(0, int((observed_at - candle_ts).total_seconds()))
    payload = {
        "status": "HISTORICAL_DATASET_REACHABLE",
        "source": "getdata-finance EURUSD 5m GitHub dataset",
        "live": False,
        "research_only": True,
        "observed_at": observed_at.isoformat(),
        "candle_timestamp": candle_ts.isoformat(),
        "candle_age_seconds": age_seconds,
        "freshness_threshold_seconds": FRESHNESS_THRESHOLD_SECONDS,
        "freshness_status": (
            "FRESH_BY_TIMESTAMP_ONLY"
            if age_seconds <= FRESHNESS_THRESHOLD_SECONDS
            else "STALE_HISTORICAL_DATA"
        ),
        "candle": candle,
        "github_sha": os.getenv("GITHUB_SHA"),
    }
    out = Path("evidence/claimlab-market/latest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

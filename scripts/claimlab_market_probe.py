"""Probe the configured public EUR/USD 5m research feed and emit evidence."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from claimlab.ingestion import YahooEURUSD5mClient


def main():
    candle = YahooEURUSD5mClient().fetch_latest_eurusd_candle()
    if candle is None:
        raise SystemExit("LIVE_MARKET_FEED_UNAVAILABLE")
    payload = {
        "status": "LIVE_FEED_REACHABLE",
        "source": "Yahoo Finance chart API",
        "research_only": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "candle": candle,
        "github_sha": os.getenv("GITHUB_SHA"),
    }
    out = Path("evidence/claimlab-market/latest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

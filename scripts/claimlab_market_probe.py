"""Probe real EUR/USD research data and emit provenance evidence."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from claimlab.ingestion import GitHubEURUSD5mHistoricalClient


def main():
    candle = GitHubEURUSD5mHistoricalClient().fetch_latest_eurusd_candle()
    if candle is None:
        raise SystemExit("HISTORICAL_MARKET_DATA_UNAVAILABLE")
    payload = {
        "status": "REAL_HISTORICAL_FEED_REACHABLE",
        "source": "getdata-finance EURUSD 5m GitHub dataset",
        "live": False,
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

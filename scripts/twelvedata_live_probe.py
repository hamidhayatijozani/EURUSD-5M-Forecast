"""Probe Twelve Data and persist a sanitized market-ingestion evidence record."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from claimlab.twelvedata import TwelveDataEURUSD5mClient


def main() -> int:
    out = Path("evidence/claimlab-market/twelvedata-latest.json")
    try:
        candle = TwelveDataEURUSD5mClient().fetch_latest_eurusd_candle()
        record = {
            "schema_version": 1,
            "probe": "twelvedata_eurusd_5min_ingestion",
            "status": "PASS" if candle["freshness_status"] == "FRESH" else "FAIL",
            "live_feed_claim": "VERIFIED_FOR_THIS_OBSERVATION" if candle["freshness_status"] == "FRESH" else "STALE",
            "forecast_or_prediction_created": False,
            "provider": candle["provider"],
            "symbol": candle["symbol"],
            "interval": candle["interval"],
            "candle": candle,
            "probe_completed_at": datetime.now(timezone.utc).isoformat(),
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({
            "probe": record["probe"],
            "status": record["status"],
            "provider": record["provider"],
            "symbol": record["symbol"],
            "interval": record["interval"],
            "candle_timestamp": candle["timestamp"],
            "candle_closed_at": candle["candle_closed_at"],
            "data_age_seconds": candle["data_age_seconds"],
            "freshness_status": candle["freshness_status"],
            "raw_payload_hash": candle["raw_payload_hash"],
            "evidence_file": str(out),
            "forecast_or_prediction_created": False,
        }, sort_keys=True))
        return 0 if record["status"] == "PASS" else 2
    except Exception as exc:
        # Do not print provider exception text, URLs, or credential-bearing request details.
        record = {
            "schema_version": 1,
            "probe": "twelvedata_eurusd_5min_ingestion",
            "status": "FAIL",
            "live_feed_claim": "UNVERIFIED",
            "forecast_or_prediction_created": False,
            "error_type": type(exc).__name__,
            "probe_completed_at": datetime.now(timezone.utc).isoformat(),
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: record[k] for k in ("probe", "status", "live_feed_claim", "error_type", "forecast_or_prediction_created")}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())

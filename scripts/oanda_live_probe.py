"""Run a one-shot OANDA EUR/USD quote probe and emit sanitized JSON."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from claimlab.oanda_live import OandaLiveClient


def main() -> int:
    try:
        client = OandaLiveClient()
        result = client.get_latest_quote()
        report = {
            "probe": "oanda_eurusd_live_quote",
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "provider_id": result.get("provider_id"),
            "environment": result.get("environment"),
            "instrument": result.get("instrument"),
            "event_timestamp_utc": result.get("provider_event_timestamp_utc"),
            "received_at_utc": result.get("received_at_utc"),
            "event_age_ms": result.get("event_age_ms"),
            "freshness_status": result.get("freshness_status"),
            "raw_payload_hash": result.get("raw_payload_hash"),
            "request_id": result.get("request_id"),
            "status": "PASS" if result.get("freshness_status") == "PASS" else "FAIL",
        }
        # Prices are intentionally omitted from CI logs; the evidence hash and timing remain.
        print(json.dumps(report, sort_keys=True))
        return 0 if report["status"] == "PASS" else 2
    except Exception as exc:
        # Avoid printing exception details that could contain request metadata or secrets.
        print(json.dumps({
            "probe": "oanda_eurusd_live_quote",
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "FAIL",
            "error_type": type(exc).__name__,
        }, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())

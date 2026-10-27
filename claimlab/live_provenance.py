"""Fail-closed validation for live forecast freshness provenance."""
from datetime import datetime
import math


_REQUIRED = (
    "provider",
    "source_candle_ts",
    "observed_at",
    "data_age_seconds",
    "freshness_limit_seconds",
    "freshness_status",
)


def require_freshness_provenance(row):
    """Return validated freshness fields; never manufacture missing provenance."""
    missing = [
        key for key in _REQUIRED
        if key not in row or row[key] is None or row[key] == ""
    ]
    if missing:
        raise ValueError("LIVE_FRESHNESS_PROVENANCE_MISSING:" + ",".join(missing))

    if not isinstance(row["provider"], str) or not row["provider"].strip():
        raise ValueError("LIVE_FRESHNESS_PROVIDER_INVALID")
    if row["freshness_status"] != "FRESH":
        raise ValueError("LIVE_FRESHNESS_STATUS_NOT_FRESH")

    try:
        age = float(row["data_age_seconds"])
        limit = float(row["freshness_limit_seconds"])
    except (TypeError, ValueError) as exc:
        raise ValueError("LIVE_FRESHNESS_AGE_INVALID") from exc
    if not math.isfinite(age) or not math.isfinite(limit) or age < 0 or limit <= 0:
        raise ValueError("LIVE_FRESHNESS_AGE_INVALID")
    if age > limit:
        raise ValueError("LIVE_FRESHNESS_LIMIT_EXCEEDED")

    try:
        source = datetime.fromisoformat(str(row["source_candle_ts"]).replace("Z", "+00:00"))
        observed = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("LIVE_FRESHNESS_TIMESTAMP_INVALID") from exc
    if source.tzinfo is None or observed.tzinfo is None:
        raise ValueError("LIVE_FRESHNESS_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    if source > observed:
        raise ValueError("LIVE_FRESHNESS_SOURCE_FROM_FUTURE")

    return {
        "provider": row["provider"].strip(),
        "source_candle_ts": str(row["source_candle_ts"]),
        "observed_at": str(row["observed_at"]),
        "data_age_seconds": age,
        "freshness_limit_seconds": limit,
        "freshness_status": "FRESH",
    }

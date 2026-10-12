"""Leakage-safe electricity-grid proxy features; no network access or trading signal.

Grid load is an infrastructure/regime proxy. It is not datacenter-specific load and
must never be interpreted as a directional EUR/USD vote without separate evidence.
"""
from datetime import datetime, timezone
from statistics import median
from typing import Iterable

def _dt(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return dt.astimezone(timezone.utc)

def _clip(value, lo=-1.0, hi=1.0):
    return max(lo, min(hi, float(value)))

def grid_load_features(observations: Iterable[dict], forecast_at,
                       *, max_age_seconds=1800, min_history=12,
                       anomaly_scale=0.15):
    """Return a bounded, non-directional grid-load anomaly using only past data.

    Each observation requires timestamp and finite numeric value in a consistent
    unit and region. The newest observation must not be after forecast_at and
    must be fresh. Baseline uses only preceding observations, excluding the newest.
    """
    now = _dt(forecast_at)
    valid = []
    for row in observations:
        try:
            ts = _dt(row["timestamp"])
            value = float(row["value"])
            if not value == value or value in (float("inf"), float("-inf")) or value < 0:
                continue
            valid.append((ts, value, str(row.get("region", "UNKNOWN")),
                          str(row.get("unit", "UNKNOWN"))))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    valid.sort(key=lambda x: x[0])
    valid = [x for x in valid if x[0] <= now]
    if not valid:
        return {"status": "INSUFFICIENT_DATA", "score": 0.0,
                "load_value": None, "baseline_value": None, "age_seconds": None,
                "n_history": 0, "directional": False}
    latest = valid[-1]
    age = (now - latest[0]).total_seconds()
    same_unit_region = [x for x in valid if x[2:] == latest[2:]]
    prior = [x for x in same_unit_region[:-1] if x[0] < latest[0]]
    base = [x[1] for x in prior[-max(min_history, 1):]]
    if age < 0 or age > max_age_seconds:
        return {"status": "STALE", "score": 0.0, "load_value": latest[1],
                "baseline_value": median(base) if base else None,
                "age_seconds": age, "n_history": len(base), "directional": False}
    if len(base) < min_history:
        return {"status": "INSUFFICIENT_HISTORY", "score": 0.0,
                "load_value": latest[1], "baseline_value": median(base) if base else None,
                "age_seconds": age, "n_history": len(base), "directional": False}
    baseline = median(base)
    if baseline <= 0:
        return {"status": "INVALID_BASELINE", "score": 0.0,
                "load_value": latest[1], "baseline_value": baseline,
                "age_seconds": age, "n_history": len(base), "directional": False}
    anomaly = latest[1] / baseline - 1.0
    return {"status": "OK", "score": _clip(anomaly / anomaly_scale),
            "load_value": latest[1], "baseline_value": baseline,
            "anomaly_fraction": anomaly, "age_seconds": age,
            "n_history": len(base), "region": latest[2], "unit": latest[3],
            "directional": False}

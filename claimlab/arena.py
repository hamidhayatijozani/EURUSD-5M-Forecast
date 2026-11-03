"""Same-window strategy arena with strict temporal and provenance eligibility."""
from datetime import datetime, timezone
import math
from statistics import mean

from .statistics import StatisticalEngine


def _parse_timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError("missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)



def _parse_aware_timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError("missing timezone-aware timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _provenance_eligible(row):
    """Require an explicit live or historical source contract before scoring."""
    mode = row.get("data_mode")
    provider = row.get("provider")
    source_value = row.get("source_candle_ts")
    if not isinstance(provider, str) or not provider.strip() or not source_value:
        return False
    try:
        source = _parse_aware_timestamp(source_value)
        cutoff = _parse_aware_timestamp(row["feature_cutoff_at"])
    except (KeyError, TypeError, ValueError):
        return False
    if source > cutoff:
        return False

    if mode == "HISTORICAL":
        return (
            row.get("freshness_status") == "NOT_APPLICABLE"
            and row.get("observed_at") in (None, "")
            and row.get("data_age_seconds") is None
            and row.get("freshness_limit_seconds") is None
        )

    if mode == "LIVE":
        required = (
            row.get("observed_at"),
            row.get("data_age_seconds"),
            row.get("freshness_limit_seconds"),
        )
        if any(value is None or value == "" for value in required):
            return False
        if row.get("freshness_status") != "FRESH":
            return False
        try:
            observed = _parse_aware_timestamp(row["observed_at"])
            issued = _parse_aware_timestamp(row["issued_at"])
            age = float(row["data_age_seconds"])
            limit = float(row["freshness_limit_seconds"])
        except (KeyError, TypeError, ValueError):
            return False
        expected_age = (issued - _parse_aware_timestamp(row["feature_cutoff_at"])).total_seconds()
        return (
            source <= observed <= issued
            and math.isfinite(age)
            and math.isfinite(limit)
            and 0 <= age <= limit
            and limit > 0
            and expected_age >= 0
            and abs(age - expected_age) <= 1.0
        )

    return False


def _temporally_eligible(row):
    """Only score rows whose feature cutoff is strictly before issuance."""
    try:
        cutoff = _parse_timestamp(row["feature_cutoff_at"])
        issued = _parse_timestamp(row["issued_at"])
        target = _parse_timestamp(row["target_at"])
        resolved = _parse_timestamp(row["resolved_at"])
    except (KeyError, TypeError, ValueError):
        return False
    return cutoff < issued < target <= resolved


def score(
    rows,
    prediction_key="prediction",
    baseline_key="baseline_prediction",
    horizon=5,
    bootstrap_resamples=2000,
    alpha=0.05,
):
    candidates = [r for r in rows if r.get("status") == "VALID"]
    provenance_valid = [r for r in candidates if _provenance_eligible(r)]
    rejected_provenance = len(candidates) - len(provenance_valid)
    valid = [r for r in provenance_valid if _temporally_eligible(r)]
    rejected_temporal = len(provenance_valid) - len(valid)
    if not valid:
        return {
            "n": 0,
            "status": "INSUFFICIENT_DATA",
            "temporal_rejected": rejected_temporal,
            "provenance_rejected": rejected_provenance,
        }

    mae = mean(abs(float(r["actual"]) - float(r[prediction_key])) for r in valid)
    bmae = mean(abs(float(r["actual"]) - float(r[baseline_key])) for r in valid)
    base = {
        "n": len(valid),
        "temporal_rejected": rejected_temporal,
        "provenance_rejected": rejected_provenance,
        "mae": mae,
        "baseline_mae": bmae,
        "mae_delta": bmae - mae,
        "friction_adjusted_return": mean(
            float(r["friction_adjusted_return"]) for r in valid
        ),
        "hit_rate": mean(bool(r["direction_hit"]) for r in valid),
    }
    inferred = StatisticalEngine.summarize(
        valid,
        horizon=horizon,
        resamples=bootstrap_resamples,
        alpha=alpha,
    )
    base.update(inferred)
    if base["n"] < 100:
        base["status"] = "INSUFFICIENT_DATA"
    return base


def arena(rows, models):
    return {name: score(rows, key) for name, key in models.items()}

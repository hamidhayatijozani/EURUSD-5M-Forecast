"""Same-window strategy arena with strict temporal eligibility."""
from datetime import datetime, timezone
from statistics import mean

from .statistics import StatisticalEngine


def _parse_timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError("missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
    valid = [r for r in candidates if _temporally_eligible(r)]
    rejected_temporal = len(candidates) - len(valid)
    if not valid:
        return {
            "n": 0,
            "status": "INSUFFICIENT_DATA",
            "temporal_rejected": rejected_temporal,
        }

    mae = mean(abs(float(r["actual"]) - float(r[prediction_key])) for r in valid)
    bmae = mean(abs(float(r["actual"]) - float(r[baseline_key])) for r in valid)
    base = {
        "n": len(valid),
        "temporal_rejected": rejected_temporal,
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

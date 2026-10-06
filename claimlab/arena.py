"""Same-window strategy arena with overlap-aware statistical inference."""
from statistics import mean
from .statistics import StatisticalEngine


def score(
    rows,
    prediction_key="prediction",
    baseline_key="baseline_prediction",
    horizon=5,
    bootstrap_resamples=2000,
    alpha=0.05,
):
    valid = [r for r in rows if r.get("status") == "VALID"]
    if not valid:
        return {"n": 0, "status": "INSUFFICIENT_DATA"}

    mae = mean(abs(float(r["actual"]) - float(r[prediction_key])) for r in valid)
    bmae = mean(abs(float(r["actual"]) - float(r[baseline_key])) for r in valid)
    base = {
        "n": len(valid),
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
    return base


def arena(rows, models):
    return {name: score(rows, key) for name, key in models.items()}

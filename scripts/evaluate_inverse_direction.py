"""Compare original and strict-inverse EURUSD direction on the same resolved ClaimLab rows.

This is an exploratory diagnostic, not a trading recommendation. It deliberately
reports overlapping observations as naive sample counts and does not claim an
effective independent sample size.
"""
import json
import math
from pathlib import Path

LEDGER = Path("research/claimlab_live_observations.jsonl")
FRICTION_KEYS = ("spread_cost", "slippage_cost", "commission_cost")


def wilson_interval(hits: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = hits / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return [center - margin, center + margin]


def evaluate(rows):
    rows = [
        row for row in rows
        if row.get("status") == "VALID"
        and int(row.get("horizon_seconds", 0)) == 300
        and "prediction" in row and "actual" in row
    ]
    original_hits = inverse_hits = eligible = 0
    original_net = inverse_net = 0.0
    for row in rows:
        prediction = float(row["prediction"])
        actual = float(row["actual"])
        direction = (prediction > 0) - (prediction < 0)
        actual_direction = (actual > 0) - (actual < 0)
        friction_threshold = float(row.get("spread_cost", 0.0))
        if direction != 0 and abs(actual) > friction_threshold:
            eligible += 1
            original_hits += int(direction == actual_direction)
            inverse_hits += int(-direction == actual_direction)
        costs = sum(float(row.get(key, 0.0)) for key in FRICTION_KEYS)
        original_net += direction * actual - costs if direction else 0.0
        inverse_net += -direction * actual - costs if direction else 0.0
    n = len(rows)
    return {
        "rows": n,
        "directionally_resolvable_rows": eligible,
        "original": {
            "hits": original_hits,
            "hit_rate_all_rows": original_hits / n if n else None,
            "hit_rate_resolvable_rows": original_hits / eligible if eligible else None,
            "wilson_95_naive_all_rows": wilson_interval(original_hits, n),
            "wilson_95_naive_resolvable_rows": wilson_interval(original_hits, eligible),
            "mean_net_return_per_row": original_net / n if n else None,
        },
        "inverse": {
            "hits": inverse_hits,
            "hit_rate_all_rows": inverse_hits / n if n else None,
            "hit_rate_resolvable_rows": inverse_hits / eligible if eligible else None,
            "wilson_95_naive_all_rows": wilson_interval(inverse_hits, n),
            "wilson_95_naive_resolvable_rows": wilson_interval(inverse_hits, eligible),
            "mean_net_return_per_row": inverse_net / n if n else None,
        },
        "limitations": [
            "Five-minute forecasts are issued every minute and overlap.",
            "Wilson intervals are naive and do not correct serial dependence.",
            "A zero or friction-sized target move is not a directional hit for either side.",
            "This ledger is exploratory; no 90% performance claim is supported by this script.",
        ],
    }


def main():
    if not LEDGER.exists():
        raise SystemExit(f"missing evidence ledger: {LEDGER}")
    rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(json.dumps(evaluate(rows), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

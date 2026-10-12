#!/usr/bin/env python3
"""Offline, reproducible evaluation of immutable live forecast evidence.

This tool never fetches market data and never changes model state. It reports
what can be scored from the fields actually persisted in the evidence ledgers.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from statistics import mean

CONTRACT = "freshness-90s-v2"
FRICTION = 0.00002
BLOCK_LENGTH = 5
BOOTSTRAP_REPLICATES = 1000


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        rows.append(value)
    return rows


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def resolved_current_rows(rows: list[dict]) -> list[dict]:
    selected = [
        row for row in rows
        if row.get("data_contract_version") == CONTRACT
        and row.get("status") == "RESOLVED"
        and _number(row.get("actual_return")) is not None
        and _number(row.get("predicted_return")) is not None
    ]
    selected.sort(key=lambda row: (str(row.get("target_at", "")), str(row.get("prediction_id", ""))))
    ids = [row.get("prediction_id") for row in selected]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("current-contract resolved rows must have unique non-empty prediction_id values")
    return selected


def _max_drawdown(net_returns: list[float]) -> float:
    equity = peak = 1.0
    drawdown = 0.0
    for value in net_returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        if peak:
            drawdown = max(drawdown, (peak - equity) / peak)
    return drawdown


def _block_bootstrap_mean_ci(values: list[float], *, seed: int = 1729,
                              replicates: int = BOOTSTRAP_REPLICATES,
                              block_length: int = BLOCK_LENGTH) -> list[float] | None:
    """Non-circular moving-block bootstrap CI for mean per-observation net return."""
    n = len(values)
    if n < max(10, block_length * 2):
        return None
    rng = random.Random(seed)
    starts = list(range(max(1, n - block_length + 1)))
    estimates = []
    blocks_needed = math.ceil(n / block_length)
    for _ in range(replicates):
        sample = []
        for _ in range(blocks_needed):
            start = rng.choice(starts)
            sample.extend(values[start:start + block_length])
        estimates.append(mean(sample[:n]))
    estimates.sort()
    low = estimates[int(0.025 * (replicates - 1))]
    high = estimates[int(0.975 * (replicates - 1))]
    return [low, high]


def score_signal(pairs: list[tuple[float, float]], *, friction: float = FRICTION,
                 seed: int = 1729) -> dict:
    """Score (predicted return, actual return) pairs with explicit abstention."""
    if not pairs:
        return {"status": "INSUFFICIENT_DATA", "n": 0}
    active = []
    errors = []
    net_by_forecast = []
    hits = 0
    for prediction, actual in pairs:
        if not math.isfinite(prediction) or not math.isfinite(actual):
            continue
        errors.append(abs(actual - prediction))
        position = 1 if prediction > 0 else -1 if prediction < 0 else 0
        if position == 0:
            net_by_forecast.append(0.0)
            continue
        net = position * actual - friction
        active.append((position, actual, net))
        net_by_forecast.append(net)
        if (position > 0 and actual > friction) or (position < 0 and actual < -friction):
            hits += 1
    n = len(errors)
    if n == 0:
        return {"status": "INSUFFICIENT_DATA", "n": 0}
    active_returns = [item[2] for item in active]
    net_sum = sum(net_by_forecast)
    ci = _block_bootstrap_mean_ci(net_by_forecast, seed=seed)
    status = "INSUFFICIENT_DATA" if n < 10 else "NO_ACTIVE_SIGNALS" if not active else "SCORED"
    return {
        "status": status,
        "n": n,
        "active_n": len(active),
        "coverage": len(active) / n,
        "hits": hits,
        "hit_rate_all": hits / n,
        "hit_rate_active": hits / len(active) if active else None,
        "mae": mean(errors),
        "gross_return_sum": sum(item[1] * item[0] for item in active),
        "net_return_sum": net_sum,
        "mean_net_return_per_active": mean(active_returns) if active_returns else None,
        "mean_net_return_per_forecast": mean(net_by_forecast),
        "max_drawdown": _max_drawdown(net_by_forecast),
        "block_bootstrap_95ci_mean_net_per_forecast": ci,
        "bootstrap_status": "AVAILABLE" if ci is not None else "INSUFFICIENT_DATA_FOR_BLOCK_CI",
        "friction_per_active_trade": friction,
    }

def evaluate_predictions(rows: list[dict]) -> dict:
    selected = resolved_current_rows(rows)
    if not selected:
        return {"status": "INSUFFICIENT_DATA", "contract": CONTRACT, "n": 0, "strategies": {}}

    strategies: dict[str, list[tuple[float, float]]] = {
        "ensemble": [],
        "ensemble_inverse": [],
        "baseline": [],
        "baseline_inverse": [],
    }
    algorithm_names = sorted({
        str(item.get("name"))
        for row in selected for item in row.get("algorithms", [])
        if isinstance(item, dict) and item.get("name")
    })
    for name in algorithm_names:
        strategies[f"algorithm:{name}"] = []

    context_pairs = []
    context_rows = 0
    context_coverage = 0
    for row in selected:
        actual = float(row["actual_return"])
        predicted = float(row["predicted_return"])
        baseline = _number(row.get("baseline_prediction"))
        if baseline is not None:
            strategies["baseline"].append((baseline, actual))
            strategies["baseline_inverse"].append((-baseline, actual))
        strategies["ensemble"].append((predicted, actual))
        strategies["ensemble_inverse"].append((-predicted, actual))
        for item in row.get("algorithms", []):
            if isinstance(item, dict) and item.get("name"):
                value = _number(item.get("predicted_return"))
                if value is not None:
                    strategies[f"algorithm:{item['name']}"].append((value, actual))
        context = row.get("external_context") or {}
        context_rows += 1
        if int(context.get("directional_sources_available") or 0) > 0:
            context_coverage += 1
            value = _number(context.get("context_score"))
            if value is not None:
                # The live score multiplies context_score by 0.18, then maps
                # the final score to predicted return with scale 0.0005.
                context_pairs.append((value * 0.18 * 0.0005, actual))

    scored = {
        name: score_signal(pairs, seed=1729 + index)
        for index, (name, pairs) in enumerate(sorted(strategies.items()))
    }
    if context_pairs:
        scored["context_only_proxy"] = score_signal(context_pairs, seed=1997)
        scored["context_only_proxy"]["n"] = len(context_pairs)
        scored["context_only_proxy"]["available_source_rows"] = context_coverage
    else:
        scored["context_only_proxy"] = {
            "status": "UNAVAILABLE_NO_DIRECTIONAL_CONTEXT",
            "n": 0,
            "available_source_rows": context_coverage,
        }

    return {
        "status": "SCORED" if len(selected) >= 10 else "INSUFFICIENT_DATA",
        "contract": CONTRACT,
        "n": len(selected),
        "prediction_ids": [row["prediction_id"] for row in selected],
        "target_times": [row.get("target_at") for row in selected],
        "common_cohort": True,
        "context_coverage": {
            "rows": context_rows,
            "rows_with_directional_source": context_coverage,
            "fraction": context_coverage / context_rows if context_rows else 0.0,
        },
        "strategies": scored,
        "limitations": [
            "PST/base component score is not persisted per prediction, so PST-only ablation cannot be reconstructed honestly.",
            "External-context scoring uses only rows with at least one available directional source; it is not the same cohort as the full-engine comparison.",
            "One-minute forecasts with five-minute targets overlap; block-bootstrap intervals are exploratory and do not replace a preregistered untouched evaluation window.",
            "A pass in this evaluator is not evidence of live profitability or a license to trade.",
        ],
    }


def evaluate_cross_asset(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("schema") != "claimlab.live_cross_asset_observation.v1":
            continue
        candidate = row.get("candidate_id")
        actual = _number(row.get("actual_return"))
        position = _number(row.get("position"))
        net = _number(row.get("net_return"))
        if not candidate or actual is None or position is None or net is None:
            continue
        groups.setdefault(str(candidate), []).append({
            "actual": actual,
            "position": int(position),
            "net": net,
            "friction": _number(row.get("friction")) or 0.0,
            "freshness_status": row.get("freshness_status"),
            "target_at": row.get("target_at"),
        })

    out = {}
    for candidate, observations in sorted(groups.items()):
        observations.sort(key=lambda row: str(row.get("target_at") or ""))
        active = [row for row in observations if row["position"] != 0]
        wins = sum(
            (row["position"] > 0 and row["actual"] > row["friction"])
            or (row["position"] < 0 and row["actual"] < -row["friction"])
            for row in active
        )
        net_by_forecast = [row["net"] if row["position"] != 0 else 0.0 for row in observations]
        ci = _block_bootstrap_mean_ci(net_by_forecast, seed=3000 + len(candidate))
        n = len(observations)
        status = "INSUFFICIENT_DATA" if n < 10 else "NO_ACTIVE_SIGNALS" if not active else "SCORED"
        out[candidate] = {
            "status": status,
            "n": n,
            "active_n": len(active),
            "coverage": len(active) / n if n else 0.0,
            "hits": wins,
            "hit_rate_all": wins / n if n else None,
            "hit_rate_active": wins / len(active) if active else None,
            "recorded_gross_return_sum": sum(row["net"] + row["friction"] for row in active),
            "recorded_net_return_sum": sum(net_by_forecast),
            "mean_net_return_per_active": mean(row["net"] for row in active) if active else None,
            "mean_net_return_per_forecast": mean(net_by_forecast) if net_by_forecast else None,
            "max_drawdown": _max_drawdown(net_by_forecast),
            "block_bootstrap_95ci_mean_net_per_forecast": ci,
            "bootstrap_status": "AVAILABLE" if ci is not None else "INSUFFICIENT_DATA_FOR_BLOCK_CI",
            "fresh_rows": sum(row["freshness_status"] == "FRESH" for row in observations),
            "warning": "Small candidate samples are descriptive only; no strategy edge is established.",
        }
    return {"status": "SCORED" if out else "INSUFFICIENT_DATA", "candidates": out}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=Path("research/live_predictions.jsonl"))
    parser.add_argument("--cross-asset", type=Path, default=Path("research/cross_asset_live_observations.jsonl"))
    parser.add_argument("--output", type=Path, help="Optional path for JSON report")
    args = parser.parse_args()

    report = {
        "schema": "eurusd.offline_ablation_report.v1",
        "predictions": evaluate_predictions(read_jsonl(args.predictions)),
        "cross_asset": evaluate_cross_asset(read_jsonl(args.cross_asset)),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

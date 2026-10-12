"""Generate a conservative coverage report for forward-only feature snapshots.

This report is descriptive only. It does not fit a model or claim feature value.
"""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from statistics import mean

PREDICTIONS = Path("research/live_predictions.jsonl")
OUTPUT = Path("research/results/cross_repo_feature_capture_report.json")
MIN_VALID = 100


def read_jsonl(path):
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
    return rows


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf")


def _timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def build_report(rows):
    seen_ids = set()
    duplicate_ids = 0
    missing_ids = 0
    total = len(rows)
    ready = 0
    unavailable = 0
    missing_snapshot = 0
    invalid_temporal = 0
    valid_joined = []

    for row in rows:
        pid = row.get("prediction_id")
        if not pid:
            missing_ids += 1
            continue
        if pid in seen_ids:
            duplicate_ids += 1
            continue
        seen_ids.add(pid)

        snapshot = row.get("experimental_feature_snapshot")
        if not isinstance(snapshot, dict):
            missing_snapshot += 1
            continue
        if snapshot.get("status") != "READY":
            unavailable += 1
            continue
        ready += 1

        issue = _timestamp(row.get("prediction_ts"))
        cutoff = _timestamp(snapshot.get("feature_cutoff_at"))
        target = _timestamp(row.get("target_at"))
        if issue is None or cutoff is None or target is None or cutoff > issue or target <= issue:
            invalid_temporal += 1
            continue
        values = snapshot.get("values")
        required = ("pressure", "novelty", "tenacity", "realized_volatility", "trend_efficiency")
        if not isinstance(values, dict) or any(not _finite_number(values.get(key)) for key in required):
            invalid_temporal += 1
            continue
        if row.get("status") != "RESOLVED":
            continue
        actual = row.get("actual_return")
        prediction = row.get("predicted_return")
        baseline = row.get("baseline_prediction")
        if not all(_finite_number(v) for v in (actual, prediction, baseline)):
            continue
        if _timestamp(row.get("resolved_at")) is None:
            continue
        valid_joined.append({
            "prediction_id": pid,
            "target_at": row["target_at"],
            "prediction_ts": row["prediction_ts"],
            "actual_return": actual,
            "engine_abs_error": abs(prediction - actual),
            "baseline_abs_error": abs(baseline - actual),
            "features": values,
        })

    n = len(valid_joined)
    result = {
        "schema": "cross_repo_feature_capture_report.v1",
        "verdict": "INSUFFICIENT_DATA" if n < MIN_VALID else "DESCRIPTIVE_ONLY_REQUIRES_PREREGISTERED_TEST",
        "performance_claim_permitted": False,
        "minimum_valid_observations": MIN_VALID,
        "counts": {
            "prediction_rows": total,
            "unique_prediction_ids": len(seen_ids),
            "missing_prediction_ids": missing_ids,
            "duplicate_prediction_ids": duplicate_ids,
            "snapshots_ready": ready,
            "snapshots_unavailable_or_unknown": unavailable,
            "snapshots_missing": missing_snapshot,
            "invalid_or_temporally_unverifiable_snapshots": invalid_temporal,
            "resolved_valid_joined_observations": n,
        },
        "coverage": n / total if total else 0.0,
        "descriptive_errors": None,
        "feature_target_correlations": None,
        "notes": [
            "No model is fitted and no feature is credited with incremental predictive value.",
            "Each observation is taken from one immutable prediction record keyed by prediction_id and exact target_at.",
            "Timestamp comparisons parse timezone-aware ISO-8601 values and compare instants; timezone-naive timestamps are rejected.",
            "Duplicate or missing prediction IDs are excluded from valid evidence.",
            "Overlapping five-minute targets are dependent; raw count is not effective sample size.",
            "A separate preregistered forward test with dependence-aware uncertainty and cost sensitivity is required.",
        ],
    }
    if n:
        result["descriptive_errors"] = {
            "engine_mae": mean(item["engine_abs_error"] for item in valid_joined),
            "baseline_mae": mean(item["baseline_abs_error"] for item in valid_joined),
            "mae_difference_baseline_minus_engine": mean(
                item["baseline_abs_error"] - item["engine_abs_error"] for item in valid_joined
            ),
        }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    result["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=PREDICTIONS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = build_report(read_jsonl(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Audit immutable decision snapshots in the existing prediction JSONL ledger.

Historical predictions without snapshots remain explicitly unaudited. The report is emitted as JSON for CI artifact capture.
"""
import json
from pathlib import Path
from engine.forecast_evidence import verify_decision_evidence


def audit(rows):
    resolved = [r for r in rows if r.get("status") == "RESOLVED"]
    present = [r for r in resolved if isinstance(r.get("decision_evidence"), dict)]
    valid = []
    invalid = []
    for row in present:
        evidence = row["decision_evidence"]
        ok = verify_decision_evidence(evidence)
        ok = ok and row.get("decision_evidence_sha256") == evidence.get("snapshot_sha256")
        (valid if ok else invalid).append(row.get("prediction_id", "UNKNOWN"))
    component_counts = {"signal_name": 0, "adjusted_score": 0, "algorithms": 0,
                        "external_context": 0, "series_close_inputs": 0,
                        "eurusd_ohlc_inputs": 0}
    for row in present:
        if row.get("prediction_id") not in valid:
            continue
        evidence = row["decision_evidence"]
        components = evidence.get("model_components") or {}
        for key in ("signal_name", "adjusted_score", "algorithms"):
            component_counts[key] += int(key in components)
        for key in ("external_context", "series_close_inputs", "eurusd_ohlc_inputs"):
            component_counts[key] += int(bool(evidence.get(key)))
    n = len(resolved)
    return {
        "schema": "claimlab.decision_evidence_audit.v1",
        "status": "INTEGRITY_FAILURE" if invalid else "INSUFFICIENT_DATA" if not valid else "AUDITED",
        "resolved_rows": n,
        "rows_with_evidence": len(present),
        "valid_evidence_rows": len(valid),
        "missing_evidence_rows": n - len(present),
        "invalid_evidence_rows": len(invalid),
        "valid_evidence_fraction": len(valid) / n if n else 0.0,
        "invalid_prediction_ids": invalid,
        "component_presence_counts": component_counts,
        "note": "Missing historical snapshots are not reconstructed from current code or post-outcome data.",
    }


def main():
    path = Path("research/live_predictions.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    print(json.dumps(audit(rows), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()

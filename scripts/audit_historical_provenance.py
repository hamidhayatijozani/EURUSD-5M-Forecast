"""Audit historical forecast provenance without modifying canonical rows.

Missing provenance stays UNKNOWN. This tool never fills missing timestamps, source
names, ages, or freshness labels and never rewrites the source ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SOURCE_KEYS = ("source", "provider", "provider_name", "data_source")
TIMESTAMP_KEYS = ("source_candle_ts", "source_timestamp", "candle_timestamp")
OBSERVED_KEYS = ("observed_at", "observation_time", "received_at")
AGE_KEYS = ("data_age_seconds", "candle_age_seconds", "age_seconds")
FRESHNESS_KEYS = ("freshness_status", "freshness", "data_freshness")


def _present(row: dict, keys: tuple[str, ...]) -> tuple[bool, str | None]:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return True, key
    return False, None


def audit_ledger(path: Path) -> dict:
    raw = path.read_bytes()
    file_hash = hashlib.sha256(raw).hexdigest()
    rows = []
    eligible = 0
    excluded = 0
    text = raw.decode("utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            rows.append({
                "row_id": f"line:{line_number}",
                "line_number": line_number,
                "missing_fields": ["valid_json"],
                "parse_error": str(exc),
                "source_file": str(path),
                "source_file_sha256": file_hash,
                "metric_inclusion": {
                    "forecast_metrics": False,
                    "directional_metrics": False,
                    "cost_metrics": False,
                },
                "status": "EXCLUDED_INVALID_ROW",
            })
            excluded += 1
            continue
        if not isinstance(row, dict):
            missing = ["object_row"]
            row_id = f"line:{line_number}"
        else:
            row_id = next((str(row[k]) for k in ("prediction_id", "forecast_id", "decision_id", "id")
                           if row.get(k) not in (None, "")), f"line:{line_number}")
            missing = []
            for label, keys in (
                ("source", SOURCE_KEYS),
                ("source_timestamp", TIMESTAMP_KEYS),
                ("observed_at", OBSERVED_KEYS),
                ("data_age_seconds", AGE_KEYS),
                ("freshness_status", FRESHNESS_KEYS),
            ):
                found, _ = _present(row, keys)
                if not found:
                    missing.append(label)
        is_eligible = not missing
        eligible += int(is_eligible)
        excluded += int(not is_eligible)
        rows.append({
            "row_id": row_id,
            "line_number": line_number,
            "missing_fields": missing,
            "source_file": str(path),
            "source_file_sha256": file_hash,
            "metric_inclusion": {
                "forecast_metrics": is_eligible,
                "directional_metrics": is_eligible,
                "cost_metrics": is_eligible,
            },
            "status": "ELIGIBLE_PROVENANCE_PRESENT" if is_eligible else "EXCLUDED_PROVENANCE_UNKNOWN",
        })
    return {
        "schema_version": "claimlab-historical-provenance-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(path),
        "source_file_sha256": file_hash,
        "source_bytes": len(raw),
        "raw_rows": len(rows),
        "eligible_rows": eligible,
        "excluded_rows": excluded,
        "filtering_rule": "A row is eligible only when source, source timestamp, observed_at, data age, and freshness status are explicitly present. No defaults or inferred values are used.",
        "limitations": [
            "This audit checks field presence, not whether a provider's claims are independently authentic.",
            "It does not establish profitability, predictive superiority, or out-of-sample validity.",
            "Original ledger bytes are read-only and are not changed by this script.",
        ],
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="research/live_predictions.jsonl")
    parser.add_argument("--output", default="research/results/historical_provenance_audit.json")
    args = parser.parse_args()
    source = Path(args.input)
    if not source.is_file():
        raise SystemExit(f"CANONICAL_LEDGER_NOT_FOUND: {source}")
    report = audit_ledger(source)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "source_file", "source_file_sha256", "raw_rows", "eligible_rows", "excluded_rows"
    )}, sort_keys=True))
    if report["raw_rows"] == 0:
        raise SystemExit("EMPTY_CANONICAL_LEDGER")


if __name__ == "__main__":
    main()

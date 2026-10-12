"""Bridge the live forecast loop to immutable JSONL + SQLite evidence stores."""
from __future__ import annotations

import json
from pathlib import Path

from claimlab.evidence_store import (
    JsonLedger, LedgerDB, create_row, SettlementExistsError, TargetNotReachedError,
)

EVIDENCE_JSONL = Path("research/live_decision_evidence.jsonl")
SETTLEMENTS_JSONL = Path("research/live_decision_settlements.jsonl")
SQLITE_PATH = Path("research/live_evidence.db")


def _paths(evidence_dir=None):
    if evidence_dir is None:
        return EVIDENCE_JSONL, SETTLEMENTS_JSONL, SQLITE_PATH
    base = Path(evidence_dir)
    return (
        base / "live_decision_evidence.jsonl",
        base / "live_decision_settlements.jsonl",
        base / "live_evidence.db",
    )


def _read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_once(path, row, identity="prediction_id"):
    rows = _read_jsonl(path)
    prior = next((item for item in rows if item.get(identity) == row.get(identity)), None)
    if prior is not None:
        if prior != row:
            raise RuntimeError(f"LIVE_EVIDENCE_DUPLICATE_CONFLICT:{row.get(identity)}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        handle.flush()
    return True


def persist_issue(row, code_commit, evidence_dir=None):
    evidence_jsonl, settlements_jsonl, sqlite_path = _paths(evidence_dir)
    snapshot = row.get("decision_evidence")
    if not isinstance(snapshot, dict):
        raise ValueError("LIVE_DECISION_SNAPSHOT_REQUIRED")
    record = create_row(
        prediction_id=row["prediction_id"],
        decision_snapshot=snapshot,
        feature_cutoff_at=snapshot["feature_cutoff_at"],
        issued_at=row["prediction_ts"],
        target_ts=row["target_at"],
        symbol="EURUSD",
        horizon_seconds=300,
        prediction=float(row["predicted_return"]),
        baseline_prediction=float(row["baseline_prediction"]),
        config_hash=row["config_hash"],
        code_commit=str(code_commit),
        provider=row.get("provider", "Yahoo"),
        source_candle_ts=row["source_candle_ts"],
        observed_at=row["observed_at"],
        data_age_seconds=float(row["data_age_seconds"]),
        freshness_limit_seconds=float(row.get("freshness_limit_seconds", 90.0)),
        freshness_status=row.get("freshness_status", "FRESH"),
        entry_price=float(row["entry_price"]),
        direction=row["direction"],
        status="PENDING",
    )
    ledger = JsonLedger(evidence_jsonl)
    db = LedgerDB(sqlite_path)
    try:
        existing = db.get_prediction(record["prediction_id"])
        if existing is None:
            db.insert_prediction(record)
        elif existing["evidence_hash"] != record["evidence_hash"]:
            raise RuntimeError("LIVE_EVIDENCE_SQLITE_PREDICTION_CONFLICT")
        stored_snapshot = db.get_snapshot(record["prediction_id"])
        if stored_snapshot is None:
            db.insert_snapshot(record["prediction_id"], snapshot)
        elif stored_snapshot["snapshot_sha256"] != snapshot["snapshot_sha256"]:
            raise RuntimeError("LIVE_EVIDENCE_SQLITE_SNAPSHOT_CONFLICT")
        existing_jsonl = next((x for x in ledger._rows() if x.get("prediction_id") == record["prediction_id"]), None)
        if existing_jsonl is None:
            ledger.append(record)
        elif existing_jsonl.get("evidence_hash") != record["evidence_hash"]:
            raise RuntimeError("LIVE_EVIDENCE_JSONL_PREDICTION_CONFLICT")
        if not ledger.verify():
            raise RuntimeError("LIVE_EVIDENCE_JSONL_CHAIN_INVALID")
        audit_stores(db=db, ledger=ledger, evidence_dir=evidence_dir)
    finally:
        db.close()
    return record["evidence_hash"]


def persist_settlement(row, actual_return, resolved_at, evidence_dir=None):
    evidence_jsonl, settlements_jsonl, sqlite_path = _paths(evidence_dir)
    pid = row["prediction_id"]
    settlement = {
        "prediction_id": pid,
        "settled_at": resolved_at,
        "target_at": row["target_at"],
        "actual_return": float(actual_return),
        "predicted_return": float(row["predicted_return"]),
        "baseline_prediction": float(row["baseline_prediction"]),
        "entry_price": float(row["entry_price"]),
        "resolved_at": resolved_at,
        "source_candle_ts": row["source_candle_ts"],
        "decision_evidence_sha256": row["decision_evidence_sha256"],
    }
    db = LedgerDB(sqlite_path)
    try:
        if db.get_prediction(pid) is None:
            raise RuntimeError("LIVE_EVIDENCE_SETTLEMENT_WITHOUT_ISSUANCE")
        existing = db.connection.execute(
            "SELECT payload_json FROM settlements WHERE prediction_id=?", (pid,)
        ).fetchone()
        if existing is None:
            db.insert_settlement(pid, settlement, settled_at=resolved_at)
        elif json.loads(existing["payload_json"]) != settlement:
            raise RuntimeError("LIVE_EVIDENCE_SETTLEMENT_CONFLICT")
    finally:
        db.close()
    _append_once(settlements_jsonl, settlement)
    audit_stores(evidence_dir=evidence_dir)


def audit_stores(db=None, ledger=None, evidence_dir=None):
    evidence_jsonl, settlements_jsonl, sqlite_path = _paths(evidence_dir)
    own_db = db is None
    own_ledger = ledger is None
    db = db or LedgerDB(sqlite_path)
    ledger = ledger or JsonLedger(evidence_jsonl)
    try:
        if not ledger.verify():
            raise RuntimeError("LIVE_EVIDENCE_JSONL_CHAIN_INVALID")
        rows = ledger._rows()
        db_predictions = db.connection.execute("SELECT prediction_id,evidence_hash FROM predictions").fetchall()
        db_snapshots = db.connection.execute("SELECT prediction_id,snapshot_sha256 FROM snapshots").fetchall()
        db_settlements = db.connection.execute("SELECT prediction_id FROM settlements").fetchall()
        json_by_id = {r["prediction_id"]: r for r in rows}
        pred_by_id = {r["prediction_id"]: r for r in db_predictions}
        snap_by_id = {r["prediction_id"]: r for r in db_snapshots}
        if set(json_by_id) != set(pred_by_id) or set(json_by_id) != set(snap_by_id):
            raise RuntimeError("LIVE_EVIDENCE_STORE_IDENTITY_PARITY_FAILURE")
        for pid, row in json_by_id.items():
            if row.get("evidence_hash") != pred_by_id[pid]["evidence_hash"]:
                raise RuntimeError(f"LIVE_EVIDENCE_HASH_PARITY_FAILURE:{pid}")
            if row.get("snapshot_sha256") != snap_by_id[pid]["snapshot_sha256"]:
                raise RuntimeError(f"LIVE_EVIDENCE_SNAPSHOT_PARITY_FAILURE:{pid}")
        settlement_rows = _read_jsonl(settlements_jsonl)
        settlement_ids = [r.get("prediction_id") for r in settlement_rows]
        db_settlement_ids = [r["prediction_id"] for r in db_settlements]
        if len(set(settlement_ids)) != len(settlement_ids) or set(settlement_ids) != set(db_settlement_ids):
            raise RuntimeError("LIVE_EVIDENCE_SETTLEMENT_PARITY_FAILURE")
        return {
            "status": "AUDITED",
            "predictions": len(rows),
            "snapshots": len(db_snapshots),
            "settlements": len(db_settlements),
        }
    finally:
        if own_db:
            db.close()

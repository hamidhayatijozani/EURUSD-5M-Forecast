"""Audit JSONL, SQLite, snapshot digests, and settlement parity."""
import json
from pathlib import Path
from claimlab.evidence_store import JsonLedger, LedgerDB, verify_snapshot

def audit(jsonl_path, db_path, settlements_path):
    ledger = JsonLedger(jsonl_path)
    db = LedgerDB(db_path)
    try:
        rows = ledger._rows()
        jsonl_valid = ledger.verify()
        db_predictions = {r[0] for r in db.connection.execute("SELECT prediction_id FROM predictions")}
        db_snapshots = {r[0] for r in db.connection.execute("SELECT prediction_id FROM snapshots")}
        db_settlements = {r[0] for r in db.connection.execute("SELECT prediction_id FROM settlements")}
        jsonl_ids = [str(r.get("prediction_id")) for r in rows]
        snapshots_valid = all(verify_snapshot(row.get("decision_snapshot")) and row.get("snapshot_sha256") == row.get("decision_snapshot", {}).get("snapshot_sha256") for row in rows)
        path = Path(settlements_path)
        settlement_rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
        settlement_ids = [str(row.get("prediction_id")) for row in settlement_rows]
        stores_match = len(jsonl_ids) == len(set(jsonl_ids)) and set(jsonl_ids) == db_predictions and db_predictions == db_snapshots and len(settlement_ids) == len(set(settlement_ids)) and set(settlement_ids) == db_settlements
        ok = jsonl_valid and snapshots_valid and stores_match
        return {"status": "AUDITED" if ok else "INTEGRITY_FAILURE", "jsonl_valid": jsonl_valid, "snapshots_valid": snapshots_valid, "stores_match": stores_match, "jsonl_predictions": len(rows), "sqlite_predictions": len(db_predictions), "sqlite_snapshots": len(db_snapshots), "sqlite_settlements": len(db_settlements), "jsonl_settlements": len(settlement_rows)}
    finally:
        db.close()

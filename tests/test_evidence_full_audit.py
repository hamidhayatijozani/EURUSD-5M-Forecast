import json
from claimlab.evidence_store import JsonLedger, LedgerDB
from scripts.audit_evidence_ledger import audit
from tests.evidence_helpers import sample_record, sample_snapshot

def test_end_to_end_evidence_chain_audits_all_stores(tmp_path):
    row = sample_record("e2e-full-audit")
    jsonl_path = tmp_path / "evidence_ledger.jsonl"
    db_path = tmp_path / "evidence.db"
    settlements_path = tmp_path / "settlements.jsonl"
    ledger = JsonLedger(jsonl_path)
    db = LedgerDB(db_path)
    ledger.append(row)
    prediction_id = db.insert_prediction(row)
    db.insert_snapshot(prediction_id, sample_snapshot())
    settlement = {"prediction_id": prediction_id, "settled_at": "2026-10-12T02:30:01Z", "actual": 0.0002}
    db.insert_settlement(prediction_id, settlement, settled_at=settlement["settled_at"])
    settlements_path.write_text(json.dumps(settlement) + "\n", encoding="utf-8")
    assert db.get_prediction(prediction_id) is not None
    assert db.get_snapshot(prediction_id) is not None
    db.close()
    result = audit(jsonl_path, db_path, settlements_path)
    assert result["status"] == "AUDITED"
    assert result["stores_match"]
    assert result["snapshots_valid"]

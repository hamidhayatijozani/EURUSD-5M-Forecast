from claimlab.evidence_store import JsonLedger, LedgerDB
from tests.evidence_helpers import sample_record, sample_snapshot


def test_end_to_end_evidence_chain(tmp_path):
    row = sample_record("e2e-001")
    jsonl = JsonLedger(tmp_path / "evidence_ledger.jsonl")
    db = LedgerDB(tmp_path / "evidence.db")

    jsonl.append(row)
    pid = db.insert_prediction(row)
    db.insert_snapshot(pid, sample_snapshot())
    db.insert_settlement(pid, {"actual": 0.0002}, settled_at="2026-10-12T02:30:01Z")

    assert jsonl.verify()
    assert db.get_prediction(pid) is not None
    assert db.get_snapshot(pid) is not None
    assert db.connection.execute("SELECT 1 FROM settlements WHERE prediction_id=?", (pid,)).fetchone()
    db.close()

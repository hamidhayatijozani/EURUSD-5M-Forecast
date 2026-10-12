import pytest
from claimlab.evidence_store import LedgerDB, TargetNotReachedError
from tests.evidence_helpers import sample_record


def test_pending_becomes_resolved():
    db = LedgerDB(":memory:")
    pid = db.insert_prediction(sample_record())
    db.insert_settlement(pid, {"actual": 0.0001}, settled_at="2026-10-12T02:30:01Z")
    row = db.connection.execute("SELECT * FROM settlements WHERE prediction_id=?", (pid,)).fetchone()
    assert row is not None


def test_settlement_requires_target_reached():
    db = LedgerDB(":memory:")
    pid = db.insert_prediction(sample_record())
    with pytest.raises(TargetNotReachedError):
        db.insert_settlement(pid, {"actual": 0.0001}, settled_at="2026-10-12T02:29:59Z")

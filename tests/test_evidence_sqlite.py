import pytest
from claimlab.evidence_store import LedgerDB, SettlementExistsError
from tests.evidence_helpers import sample_record, sample_snapshot


def test_sqlite_insert_prediction():
    db = LedgerDB(":memory:")
    pid = db.insert_prediction(sample_record())
    assert db.get_prediction(pid) is not None


def test_sqlite_snapshot_join():
    db = LedgerDB(":memory:")
    record = sample_record()
    pid = db.insert_prediction(record)
    db.insert_snapshot(pid, sample_snapshot())
    snapshot = db.get_snapshot(pid)
    assert snapshot is not None
    assert snapshot["snapshot_sha256"] == record["snapshot_sha256"]


def test_sqlite_settlement_once():
    db = LedgerDB(":memory:")
    pid = db.insert_prediction(sample_record())
    db.insert_settlement(pid, {"actual": 0.0001}, settled_at="2026-10-12T02:30:01Z")
    with pytest.raises(SettlementExistsError):
        db.insert_settlement(pid, {"actual": 0.0002}, settled_at="2026-10-12T02:30:02Z")

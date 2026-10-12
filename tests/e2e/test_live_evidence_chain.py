"""System-level evidence tests using isolated stores.

These tests prove the evidence subsystem's synthetic contract only. They do not
claim that the production live forecast loop is wired to this subsystem.
"""
import json
import sqlite3

import pytest

from claimlab.evidence_store import (
    JsonLedger,
    LedgerDB,
    SettlementExistsError,
    verify_snapshot,
)
from scripts.audit_evidence_ledger import audit
from tests.evidence_helpers import sample_record, sample_snapshot


def _persist_prediction(record, jsonl_path, db_path):
    ledger = JsonLedger(jsonl_path)
    db = LedgerDB(db_path)
    db.insert_prediction(record)
    db.insert_snapshot(record["prediction_id"], record["decision_snapshot"])
    ledger.append(record)
    return ledger, db


def test_full_synthetic_evidence_chain_jsonl_sqlite_settlement_audit(tmp_path):
    jsonl_path = tmp_path / "evidence.jsonl"
    db_path = tmp_path / "evidence.sqlite"
    settlements_path = tmp_path / "settlements.jsonl"
    record = sample_record("e2e-chain-001")

    ledger, db = _persist_prediction(record, jsonl_path, db_path)
    assert ledger.verify()
    assert verify_snapshot(record["decision_snapshot"])
    assert db.get_prediction(record["prediction_id"]) is not None
    assert db.get_snapshot(record["prediction_id"]) is not None

    # Synthetic clock: target_ts is 02:30:00Z; settle strictly afterwards.
    settlement = {
        "prediction_id": record["prediction_id"],
        "settled_at": "2026-10-12T02:30:01Z",
        "actual": 1.1515,
    }
    db.insert_settlement(
        record["prediction_id"], settlement, settled_at=settlement["settled_at"]
    )
    settlements_path.write_text(
        json.dumps(settlement, sort_keys=True) + "\n", encoding="utf-8"
    )
    db.close()

    report = audit(jsonl_path, db_path, settlements_path)
    assert report["status"] == "AUDITED"
    assert report["jsonl_valid"] is True
    assert report["snapshots_valid"] is True
    assert report["stores_match"] is True


def test_jsonl_sqlite_identity_and_hash_references_match(tmp_path):
    record = sample_record("e2e-parity-001")
    jsonl_path, db_path = tmp_path / "evidence.jsonl", tmp_path / "evidence.sqlite"
    ledger, db = _persist_prediction(record, jsonl_path, db_path)
    jsonl_row = ledger._rows()[0]
    sqlite_row = db.get_prediction(record["prediction_id"])
    sqlite_payload = json.loads(sqlite_row["payload_json"])

    for field in ("prediction_id", "snapshot_sha256", "evidence_hash"):
        assert jsonl_row[field] == sqlite_payload[field]
    assert jsonl_row["decision_snapshot"] == sqlite_payload["decision_snapshot"]
    db.close()


def test_audit_detects_tampered_jsonl_payload(tmp_path):
    record = sample_record("e2e-tamper-001")
    jsonl_path, db_path = tmp_path / "evidence.jsonl", tmp_path / "evidence.sqlite"
    ledger, db = _persist_prediction(record, jsonl_path, db_path)
    rows = ledger._rows()
    rows[0]["forecast_direction"] = "DOWN"
    jsonl_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    db.close()

    report = audit(jsonl_path, db_path, tmp_path / "missing-settlements.jsonl")
    assert report["status"] == "INTEGRITY_FAILURE"
    assert report["jsonl_valid"] is False


def test_snapshot_replay_is_rejected_by_sqlite_uniqueness(tmp_path):
    record = sample_record("e2e-replay-001")
    db = LedgerDB(tmp_path / "evidence.sqlite")
    pid = db.insert_prediction(record)
    db.insert_snapshot(pid, record["decision_snapshot"])
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_snapshot(pid, record["decision_snapshot"])
    db.close()


def test_double_settlement_is_rejected_end_to_end(tmp_path):
    record = sample_record("e2e-double-settle-001")
    db = LedgerDB(tmp_path / "evidence.sqlite")
    pid = db.insert_prediction(record)
    db.insert_snapshot(pid, record["decision_snapshot"])
    db.insert_settlement(pid, {"actual": 1.1515}, settled_at="2026-10-12T02:30:01Z")
    with pytest.raises(SettlementExistsError):
        db.insert_settlement(pid, {"actual": 1.1516}, settled_at="2026-10-12T02:30:02Z")
    db.close()


def test_global_audit_reports_parity_across_jsonl_sqlite_and_settlements(tmp_path):
    jsonl_path, db_path = tmp_path / "evidence.jsonl", tmp_path / "evidence.sqlite"
    settlements_path = tmp_path / "settlements.jsonl"
    record = sample_record("e2e-global-audit-001")
    ledger, db = _persist_prediction(record, jsonl_path, db_path)
    settlement = {
        "prediction_id": record["prediction_id"],
        "settled_at": "2026-10-12T02:30:01Z",
        "actual": 1.1515,
    }
    db.insert_settlement(record["prediction_id"], settlement, settled_at=settlement["settled_at"])
    settlements_path.write_text(json.dumps(settlement, sort_keys=True) + "\n", encoding="utf-8")
    db.close()

    report = audit(jsonl_path, db_path, settlements_path)
    assert report["status"] == "AUDITED"
    assert report["jsonl_predictions"] == report["sqlite_predictions"] == 1
    assert report["sqlite_snapshots"] == 1
    assert report["sqlite_settlements"] == report["jsonl_settlements"] == 1

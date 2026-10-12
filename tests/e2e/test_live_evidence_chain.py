"""System-level tests for the evidence path. These use isolated stores, not live-market claims."""
import json
import sqlite3

import pytest

from claimlab.evidence_store import (
    JsonLedger,
    LedgerDB,
    SettlementExistsError,
    TargetNotReachedError,
    verify_snapshot,
)
from scripts.audit_evidence_ledger import audit
from scripts import evidence_cli
from tests.evidence_helpers import sample_record


def _paths(tmp_path):
    return {
        "jsonl": tmp_path / "evidence_ledger.jsonl",
        "db": tmp_path / "evidence.db",
        "settlements": tmp_path / "settlements.jsonl",
    }


def test_full_evidence_chain_forecast_snapshot_jsonl_sqlite_settlement_audit(tmp_path):
    paths = _paths(tmp_path)
    record = sample_record("e2e-full-chain")
    ledger = JsonLedger(paths["jsonl"])
    db = LedgerDB(paths["db"])

    assert record["prediction_id"]
    assert verify_snapshot(record["decision_snapshot"])
    assert record["snapshot_sha256"] == record["decision_snapshot"]["snapshot_sha256"]
    assert len(record["evidence_hash"]) == 64

    ledger.append(record)
    pid = db.insert_prediction(record)
    db.insert_snapshot(pid, record["decision_snapshot"])
    assert db.get_prediction(pid) is not None
    assert db.get_snapshot(pid) is not None

    settlement = {"prediction_id": pid, "actual_price": 1.1515, "settled_at": "2026-10-12T02:30:01Z"}
    db.insert_settlement(pid, settlement, settled_at=settlement["settled_at"])
    paths["settlements"].write_text(json.dumps(settlement) + "\n", encoding="utf-8")
    db.close()

    report = audit(paths["jsonl"], paths["db"], paths["settlements"])
    assert report["status"] == "AUDITED"
    assert report["jsonl_predictions"] == report["sqlite_predictions"] == 1
    assert report["sqlite_snapshots"] == report["sqlite_settlements"] == report["jsonl_settlements"] == 1


def test_jsonl_and_sqlite_have_same_identity_and_hashes(tmp_path):
    paths = _paths(tmp_path)
    record = sample_record("e2e-cross-store")
    JsonLedger(paths["jsonl"]).append(record)
    db = LedgerDB(paths["db"])
    db.insert_prediction(record)
    db.insert_snapshot(record["prediction_id"], record["decision_snapshot"])

    jsonl_row = JsonLedger(paths["jsonl"])._rows()[0]
    sqlite_row = db.get_prediction(record["prediction_id"])
    sqlite_payload = json.loads(sqlite_row["payload_json"])
    assert jsonl_row["prediction_id"] == sqlite_row["prediction_id"]
    assert jsonl_row["snapshot_sha256"] == sqlite_payload["snapshot_sha256"]
    assert jsonl_row["evidence_hash"] == sqlite_row["evidence_hash"]
    db.close()


def test_cli_issue_requires_complete_evidence_not_direction_only(tmp_path):
    paths = _paths(tmp_path)
    with pytest.raises(SystemExit) as exc:
        evidence_cli.main(["--jsonl", str(paths["jsonl"]), "--db", str(paths["db"]),
                           "--settlements", str(paths["settlements"]), "issue", "--direction", "UP"])
    assert exc.value.code == 2
    assert not paths["jsonl"].exists()


def test_cli_issue_and_settle_use_persistent_ledger_path(tmp_path, capsys):
    paths = _paths(tmp_path)
    record = sample_record("e2e-cli-settle")
    args = ["--jsonl", str(paths["jsonl"]), "--db", str(paths["db"]),
            "--settlements", str(paths["settlements"])]
    assert evidence_cli.main(args + ["issue", "--record-json", json.dumps(record)]) == 0
    issue_output = json.loads(capsys.readouterr().out)
    assert issue_output["status"] == "ISSUED"

    assert evidence_cli.main(args + ["settle", "--prediction-id", record["prediction_id"],
        "--settled-at", "2026-10-12T02:30:01Z", "--settlement-json", '{"actual_price":1.1515}']) == 0
    settlement_output = json.loads(capsys.readouterr().out)
    assert settlement_output["status"] == "RESOLVED"
    assert paths["settlements"].exists()
    db = LedgerDB(paths["db"])
    assert db.connection.execute("SELECT 1 FROM settlements WHERE prediction_id=?",
                                 (record["prediction_id"],)).fetchone()
    db.close()


def test_cli_settle_rejects_before_target(tmp_path):
    paths = _paths(tmp_path)
    record = sample_record("e2e-early-settlement")
    args = ["--jsonl", str(paths["jsonl"]), "--db", str(paths["db"]),
            "--settlements", str(paths["settlements"])]
    evidence_cli.main(args + ["issue", "--record-json", json.dumps(record)])
    with pytest.raises(TargetNotReachedError):
        evidence_cli.main(args + ["settle", "--prediction-id", record["prediction_id"],
            "--settled-at", "2026-10-12T02:29:59Z", "--settlement-json", '{"actual_price":1.1515}'])


def test_evidence_tampering_is_detected_by_audit(tmp_path):
    paths = _paths(tmp_path)
    record = sample_record("e2e-tamper")
    ledger = JsonLedger(paths["jsonl"])
    ledger.append(record)
    db = LedgerDB(paths["db"])
    db.insert_prediction(record)
    db.insert_snapshot(record["prediction_id"], record["decision_snapshot"])
    db.close()

    row = json.loads(paths["jsonl"].read_text(encoding="utf-8").splitlines()[0])
    row["forecast_direction"] = "DOWN"
    paths["jsonl"].write_text(json.dumps(row) + "\n", encoding="utf-8")
    report = audit(paths["jsonl"], paths["db"], paths["settlements"])
    assert report["status"] == "INTEGRITY_FAILURE"
    assert report["jsonl_valid"] is False


def test_snapshot_replay_is_rejected(tmp_path):
    record = sample_record("e2e-snapshot-replay")
    db = LedgerDB(tmp_path / "evidence.db")
    db.insert_prediction(record)
    db.insert_snapshot(record["prediction_id"], record["decision_snapshot"])
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_snapshot(record["prediction_id"], record["decision_snapshot"])
    db.close()


def test_double_settlement_is_rejected(tmp_path):
    record = sample_record("e2e-double-settle")
    db = LedgerDB(tmp_path / "evidence.db")
    db.insert_prediction(record)
    settlement = {"actual_price": 1.1515}
    db.insert_settlement(record["prediction_id"], settlement, settled_at="2026-10-12T02:30:01Z")
    with pytest.raises(SettlementExistsError):
        db.insert_settlement(record["prediction_id"], settlement, settled_at="2026-10-12T02:30:02Z")
    db.close()


def test_global_audit_reports_zero_invalid_hashes_and_no_orphans(tmp_path):
    paths = _paths(tmp_path)
    record = sample_record("e2e-global-audit")
    JsonLedger(paths["jsonl"]).append(record)
    db = LedgerDB(paths["db"])
    db.insert_prediction(record)
    db.insert_snapshot(record["prediction_id"], record["decision_snapshot"])
    db.close()
    report = audit(paths["jsonl"], paths["db"], paths["settlements"])
    assert report["status"] == "AUDITED"
    assert report["stores_match"] is True
    assert report["snapshots_valid"] is True


def test_live_cycle_source_failure_holds_without_fabricating_forecast(monkeypatch):
    from scripts import live_minute_loop as loop

    monkeypatch.setattr(loop, "load_state", lambda: {"last_prediction": None})
    monkeypatch.setattr(loop, "read_predictions", lambda: [])
    monkeypatch.setattr(loop, "closed_1m_rows", lambda *args, **kwargs: [])
    def unavailable(*args, **kwargs):
        raise RuntimeError("TEST_FEED_UNAVAILABLE")
    monkeypatch.setattr(loop, "aligned_closed_1m_series", unavailable)
    monkeypatch.setattr(loop, "save_predictions", lambda rows: pytest.fail("must not save a synthetic forecast"))
    monkeypatch.setattr(loop, "save_state", lambda state: None)
    assert loop.cycle() == "HOLD"

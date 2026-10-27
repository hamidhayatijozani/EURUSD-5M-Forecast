from datetime import datetime, timedelta, timezone

import claimlab.live_evidence_bridge as bridge
from engine.forecast_evidence import build_decision_evidence


def _row():
    base = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
    times = [base + timedelta(minutes=i) for i in range(30)]
    issue = times[-1] + timedelta(minutes=1)
    target = issue + timedelta(minutes=5)
    closes = [1.10 + i * 0.00001 for i in range(len(times))]
    snapshot = build_decision_evidence(
        candle_times=times,
        series={"EURUSD": closes},
        ohlc={"EURUSD": [(p, p + 0.0001, p - 0.0001, p) for p in closes]},
        source_candle_ts=times[-1],
        feature_cutoff_at=times[-1],
        issued_at=issue,
        target_ts=target,
        config_hash="test-config-hash",
        model_components={"model": "frozen-test-fixture"},
        external_context={},
    )
    return {
        "prediction_id": "live-test-001",
        "prediction_ts": issue.isoformat(),
        "target_at": target.isoformat(),
        "decision_evidence": snapshot,
        "decision_evidence_sha256": snapshot["snapshot_sha256"],
        "predicted_return": 0.0001,
        "baseline_prediction": 0.0,
        "config_hash": "test-config-hash",
        "provider": "test-fixture",
        "source_candle_ts": times[-1].isoformat(),
        "observed_at": (issue + timedelta(seconds=10)).isoformat(),
        "data_age_seconds": 10.0,
        "freshness_limit_seconds": 90.0,
        "freshness_status": "FRESH",
        "entry_price": closes[-1],
        "direction": "UP",
    }


def test_live_bridge_persists_same_identity_and_hash_to_jsonl_and_sqlite(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "EVIDENCE_JSONL", tmp_path / "evidence.jsonl")
    monkeypatch.setattr(bridge, "SETTLEMENTS_JSONL", tmp_path / "settlements.jsonl")
    monkeypatch.setattr(bridge, "SQLITE_PATH", tmp_path / "evidence.db")
    row = _row()

    evidence_hash = bridge.persist_issue(row, "test-commit")
    assert len(evidence_hash) == 64
    audit = bridge.audit_stores()
    assert audit == {"status": "AUDITED", "predictions": 1, "snapshots": 1, "settlements": 0}

    settled_at = row["target_at"]
    bridge.persist_settlement(row, 0.0002, settled_at)
    bridge.persist_settlement(row, 0.0002, settled_at)
    audit = bridge.audit_stores()
    assert audit == {"status": "AUDITED", "predictions": 1, "snapshots": 1, "settlements": 1}


def test_live_bridge_rejects_settlement_before_target(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(bridge, "EVIDENCE_JSONL", tmp_path / "evidence.jsonl")
    monkeypatch.setattr(bridge, "SETTLEMENTS_JSONL", tmp_path / "settlements.jsonl")
    monkeypatch.setattr(bridge, "SQLITE_PATH", tmp_path / "evidence.db")
    row = _row()
    bridge.persist_issue(row, "test-commit")
    with pytest.raises(Exception, match="TARGET_NOT_REACHED"):
        bridge.persist_settlement(row, 0.0002, (datetime.fromisoformat(row["target_at"]) - timedelta(seconds=1)).isoformat())


def test_live_bridge_recovers_missing_sqlite_issuance_from_verified_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "EVIDENCE_JSONL", tmp_path / "evidence.jsonl")
    monkeypatch.setattr(bridge, "SETTLEMENTS_JSONL", tmp_path / "settlements.jsonl")
    monkeypatch.setattr(bridge, "SQLITE_PATH", tmp_path / "evidence.db")
    row = _row()
    bridge.persist_issue(row, "test-commit")

    # Simulate a concurrent workflow/run artifact mismatch: JSONL issuance
    # exists, but the corresponding SQLite prediction and snapshot are absent.
    from claimlab.evidence_store import LedgerDB
    db = LedgerDB(tmp_path / "evidence.db")
    db.connection.execute("DELETE FROM snapshots WHERE prediction_id=?", (row["prediction_id"],))
    db.connection.execute("DELETE FROM predictions WHERE prediction_id=?", (row["prediction_id"],))
    db.connection.commit()
    db.close()

    bridge.persist_settlement(row, 0.0002, row["target_at"])
    assert bridge.audit_stores() == {
        "status": "AUDITED", "predictions": 1, "snapshots": 1, "settlements": 1
    }

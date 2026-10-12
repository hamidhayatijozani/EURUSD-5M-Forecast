import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from claimlab.ledger import Ledger
from claimlab.schema import Observation
from scripts import live_minute_loop as loop


def _observation(prediction_id, issued_minute):
    issued = f"2026-10-12T12:{issued_minute:02d}:00+00:00"
    target = f"2026-10-12T{12 + (issued_minute + 5) // 60:02d}:{(issued_minute + 5) % 60:02d}:00+00:00"
    resolved = target
    return Observation(
        schema_version="claimlab.observation.v1",
        prediction_id=prediction_id,
        issued_at=issued,
        target_at=target,
        resolved_at=resolved,
        symbol="EURUSD",
        horizon_seconds=300,
        prediction=0.0001,
        actual=0.0002,
        baseline_prediction=0.0,
        error_absolute=0.0001,
        baseline_error_absolute=0.0002,
        direction_hit=True,
        gross_return=0.0002,
        spread_cost=0.00002,
        slippage_cost=0.0,
        commission_cost=0.0,
        friction_adjusted_return=0.00018,
        feature_cutoff_at=issued,
        code_commit="abc123",
        config_hash="config",
        claim_registry_hash="registry",
        provider="Yahoo",
        source_candle_ts="2026-10-12T11:59:00+00:00",
        observed_at=(datetime.fromisoformat(issued) + timedelta(seconds=30)).isoformat(),
        data_age_seconds=30.0,
        freshness_limit_seconds=90.0,
        freshness_status="FRESH",
    )


def test_merge_predictions_prefers_resolved_row_without_losing_identity():
    pending = {
        "prediction_id": "p1", "prediction_ts": "2026-10-12T12:00:00+00:00",
        "target_at": "2026-10-12T12:05:00+00:00", "prediction": 0.0001,
        "baseline_prediction": 0.0, "source_candle_ts": "2026-10-12T11:59:00+00:00",
        "feature_cutoff_at": "2026-10-12T12:00:00+00:00", "config_hash": "cfg",
        "status": "PENDING", "observed_at": "2026-10-12T12:00:30+00:00",
    }
    resolved = {**pending, "status": "RESOLVED", "actual": 0.0002,
                "target_price": 1.1, "resolved_at": "2026-10-12T12:05:00+00:00",
                "error": 0.0001, "error_absolute": 0.0001,
                "baseline_error_absolute": 0.0002, "direction_hit": True}
    merged = loop._merge_prediction_texts(json.dumps(pending), json.dumps(resolved))
    assert len(merged) == 1
    assert merged[0]["status"] == "RESOLVED"


def test_claim_ledger_merge_rebuilds_hash_chain(tmp_path, monkeypatch):
    local_path = tmp_path / "local.jsonl"
    remote_path = tmp_path / "remote.jsonl"
    merged_path = tmp_path / "merged.jsonl"
    Ledger(local_path).append(_observation("p1", 0))
    Ledger(remote_path).append(_observation("p2", 1))
    monkeypatch.setattr(loop, "CLAIM_LEDGER_PATH", merged_path)

    loop._merge_claim_ledger_texts(local_path.read_text(), remote_path.read_text())

    ledger = Ledger(merged_path)
    assert ledger.verify()
    assert {row["prediction_id"] for row in ledger._rows()} == {"p1", "p2"}


def test_cross_asset_merge_rechains_and_deduplicates(tmp_path, monkeypatch):
    def write_branch(path, prediction_id, candidate_id):
        monkeypatch.setattr(loop, "CROSS_ASSET_LEDGER_PATH", path)
        prediction = {
            "prediction_id": prediction_id,
            "prediction_ts": "2026-10-12T12:00:00+00:00",
            "target_at": "2026-10-12T12:05:00+00:00",
            "provider": "Yahoo",
            "source_candle_ts": "2026-10-12T11:59:00+00:00",
            "observed_at": "2026-10-12T12:00:30+00:00",
            "data_age_seconds": 30.0,
            "freshness_status": "FRESH",
            "cross_asset_status": "READY",
            "cross_asset_candidates": {candidate_id: 1},
        }
        loop.append_cross_asset_observations(
            prediction, 0.0001, "2026-10-12T12:05:00+00:00", "abc123"
        )
        return path.read_text()

    local = write_branch(tmp_path / "local-cross.jsonl", "p1", "LIVE1M_DOLLAR_CONSENSUS_3M")
    remote = write_branch(tmp_path / "remote-cross.jsonl", "p2", "LIVE1M_DXY_INVERSE_3M")
    merged_path = tmp_path / "merged-cross.jsonl"
    monkeypatch.setattr(loop, "CROSS_ASSET_LEDGER_PATH", merged_path)

    loop._merge_cross_asset_ledger_texts(local, remote)
    rows, last_hash = loop._read_cross_asset_ledger()
    assert len(rows) == 2
    assert len({row["observation_id"] for row in rows}) == 2
    assert rows[-1]["record_hash"] == last_hash


def test_prediction_merge_preserves_legacy_rows_without_ids():
    legacy={"status":"QUARANTINED","prediction":0.0,"reason":"legacy schema"}
    current={
        "prediction_id":"p1","prediction_ts":"2026-10-12T12:00:00+00:00",
        "target_at":"2026-10-12T12:05:00+00:00","prediction":0.0001,
        "baseline_prediction":0.0,"source_candle_ts":"2026-10-12T11:59:00+00:00",
        "feature_cutoff_at":"2026-10-12T12:00:00+00:00","config_hash":"cfg",
        "status":"PENDING"
    }
    merged=loop._merge_prediction_texts(
        json.dumps(legacy)+"\n"+json.dumps(current),
        json.dumps(legacy)
    )
    assert len(merged)==2
    assert sum("prediction_id" not in row for row in merged)==1
    assert any(row.get("prediction_id")=="p1" for row in merged)


def _decision_evidence():
    from engine.forecast_evidence import build_decision_evidence
    return build_decision_evidence(
        candle_times=["2026-10-12T11:57:00+00:00", "2026-10-12T11:58:00+00:00", "2026-10-12T11:59:00+00:00"],
        series={"EURUSD": [1.1, 1.2, 1.3]},
        ohlc={"EURUSD": [(1.0, 1.2, 0.9, 1.1), (1.1, 1.3, 1.0, 1.2), (1.2, 1.4, 1.1, 1.3)]},
        source_candle_ts="2026-10-12T11:59:00+00:00",
        feature_cutoff_at="2026-10-12T11:59:00+00:00",
        issued_at="2026-10-12T12:00:00+00:00",
        target_ts="2026-10-12T12:05:00+00:00",
        config_hash="cfg",
        model_components={"signal_name": "TEST", "adjusted_score": 0.1, "algorithms": []},
        external_context={},
    )


def test_prediction_merge_rejects_tampered_decision_evidence():
    evidence = _decision_evidence()
    evidence["model_components"]["adjusted_score"] = 999
    row = {
        "prediction_id": "evidence-tampered",
        "prediction_ts": "2026-10-12T12:00:00+00:00",
        "target_at": "2026-10-12T12:05:00+00:00",
        "prediction": 0.0001,
        "baseline_prediction": 0.0,
        "source_candle_ts": "2026-10-12T11:59:00+00:00",
        "feature_cutoff_at": "2026-10-12T12:00:00+00:00",
        "config_hash": "cfg",
        "status": "PENDING",
        "decision_evidence": evidence,
        "decision_evidence_sha256": evidence["snapshot_sha256"],
    }
    with pytest.raises(RuntimeError, match="EVIDENCE_HASH_INVALID"):
        loop._merge_prediction_texts(json.dumps(row), "")


def test_prediction_merge_rejects_hash_reference_mismatch():
    evidence = _decision_evidence()
    row = {
        "prediction_id": "evidence-ref-mismatch",
        "prediction_ts": "2026-10-12T12:00:00+00:00",
        "target_at": "2026-10-12T12:05:00+00:00",
        "prediction": 0.0001,
        "baseline_prediction": 0.0,
        "source_candle_ts": "2026-10-12T11:59:00+00:00",
        "feature_cutoff_at": "2026-10-12T12:00:00+00:00",
        "config_hash": "cfg",
        "status": "PENDING",
        "decision_evidence": evidence,
        "decision_evidence_sha256": "0" * 64,
    }
    with pytest.raises(RuntimeError, match="HASH_REFERENCE_MISMATCH"):
        loop._merge_prediction_texts(json.dumps(row), "")

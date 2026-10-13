from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import claimlab.live_evidence_bridge as bridge
from engine.forecast_evidence import build_decision_evidence

import pytest

from scripts import live_minute_loop as loop


def test_evidence_push_rebases_and_retries_after_non_fast_forward():
    pushes = 0

    def fake_run(args, **kwargs):
        nonlocal pushes
        if args[:2] == ["git", "push"]:
            pushes += 1
            if pushes == 1:
                return CompletedProcess(args, 1, "", "non-fast-forward")
        return CompletedProcess(args, 0, "", "")

    with patch.object(loop.subprocess, "run", side_effect=fake_run), patch.object(loop.time, "sleep"):
        loop._push_commit_with_rebase(max_attempts=3)

    assert pushes == 2


def test_evidence_push_fails_loudly_after_retry_budget():
    def fake_run(args, **kwargs):
        if args[:2] == ["git", "push"]:
            return CompletedProcess(args, 1, "", "non-fast-forward")
        return CompletedProcess(args, 0, "", "")

    with patch.object(loop.subprocess, "run", side_effect=fake_run), patch.object(loop.time, "sleep"):
        with pytest.raises(RuntimeError, match="LIVE_EVIDENCE_PUSH_RETRIES_EXHAUSTED"):
            loop._push_commit_with_rebase(max_attempts=2)


def test_evidence_rebase_conflict_aborts_and_fails_closed():
    def fake_run(args, **kwargs):
        if args[:2] == ["git", "rebase"] and args[2] == "origin/main":
            return CompletedProcess(args, 1, "", "content conflict")
        return CompletedProcess(args, 0, "", "")

    with patch.object(loop.subprocess, "run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="LIVE_EVIDENCE_REBASE_CONFLICT"):
            loop._push_commit_with_rebase(max_attempts=2)



def test_rebase_conflict_on_any_bridge_store_path_uses_reconciliation(monkeypatch):
    conflicts = {
        str(loop.EVIDENCE_JSONL),
        str(loop.SETTLEMENTS_JSONL),
        str(loop.SQLITE_PATH),
    }

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "rebase"] and args[2] == "origin/main":
            return CompletedProcess(args, 1, "", "content conflict")
        if args[:3] == ["git", "diff", "--name-only"]:
            return CompletedProcess(args, 0, "\n".join(sorted(conflicts)) + "\n", "")
        return CompletedProcess(args, 0, "", "")

    with patch.object(loop.subprocess, "run", side_effect=fake_run), \
         patch.object(loop, "_merge_concurrent_evidence_to_main", return_value=True) as reconcile:
        loop._push_commit_with_rebase(max_attempts=2)

    reconcile.assert_called_once()


def _bridge_fixture_row(prediction_id, minute_offset=0):
    base = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=minute_offset)
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
        model_components={"fixture": prediction_id},
        external_context={},
    )
    return {
        "prediction_id": prediction_id,
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


def _read_bridge_fixture(directory):
    evidence_path = directory / "live_decision_evidence.jsonl"
    settlements_path = directory / "live_decision_settlements.jsonl"
    sqlite_path = directory / "live_evidence.db"
    return loop._validate_live_bridge_source(
        evidence_path.read_text(encoding="utf-8") if evidence_path.exists() else "",
        settlements_path.read_text(encoding="utf-8") if settlements_path.exists() else "",
        loop._read_live_bridge_db_snapshot(sqlite_path),
        "TEST",
    )


def test_concurrent_bridge_store_reconciliation_preserves_both_sides(tmp_path):
    local_dir = tmp_path / "local"
    remote_dir = tmp_path / "remote"
    merged_dir = tmp_path / "merged"

    local_row = _bridge_fixture_row("live-test-local", 0)
    remote_row = _bridge_fixture_row("live-test-remote", 1)
    bridge.persist_issue(local_row, "test-commit-local", evidence_dir=local_dir)
    bridge.persist_settlement(local_row, 0.0002, local_row["target_at"], evidence_dir=local_dir)
    bridge.persist_issue(remote_row, "test-commit-remote", evidence_dir=remote_dir)

    local = _read_bridge_fixture(local_dir)
    remote = _read_bridge_fixture(remote_dir)
    merged_predictions = loop._merge_live_bridge_prediction_records(
        local["predictions"], remote["predictions"]
    )
    merged_settlements = loop._merge_live_bridge_settlement_records(
        local["settlements"], remote["settlements"]
    )

    audit = loop._write_live_bridge_store(
        merged_predictions,
        merged_settlements,
        evidence_path=merged_dir / "live_decision_evidence.jsonl",
        settlement_path=merged_dir / "live_decision_settlements.jsonl",
        sqlite_path=merged_dir / "live_evidence.db",
    )
    assert audit == {"status": "AUDITED", "predictions": 2, "snapshots": 2, "settlements": 1}
    assert bridge.audit_stores(evidence_dir=merged_dir) == audit
    assert loop.JsonLedger(merged_dir / "live_decision_evidence.jsonl").verify()
    merged = _read_bridge_fixture(merged_dir)
    assert {row["prediction_id"] for row in merged["predictions"]} == {
        "live-test-local", "live-test-remote"
    }
    assert {row["prediction_id"] for row in merged["settlements"]} == {"live-test-local"}

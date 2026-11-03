from pathlib import Path
import json

import pytest

from claimlab.schema import Observation
from claimlab.ledger import Ledger
from claimlab.resolver import resolve, validate_window
from claimlab.arena import score
from claimlab.verdict import verdict


def prediction():
    return {
        "schema_version": "claimlab.observation.v2",
        "data_mode": "HISTORICAL",
        "provider": "test-historical",
        "source_candle_ts": "2026-10-06T09:55:00Z",
        "freshness_status": "NOT_APPLICABLE",
        "prediction_id": "p-001",
        "issued_at": "2026-10-06T10:00:00Z",
        "target_at": "2026-10-06T10:05:00Z",
        "feature_cutoff_at": "2026-10-06T09:59:59Z",
        "symbol": "EURUSD",
        "horizon_seconds": 300,
        "prediction": 0.0010,
        "code_commit": "abc",
        "config_hash": "cfg",
        "claim_registry_hash": "reg",
    }


def test_resolver_enforces_temporal_boundary():
    p = prediction()
    resolved = resolve(p, actual=0.0015, baseline_prediction=0.0002,
                       resolved_at="2026-10-06T10:05:00Z")
    assert resolved["status"] == "VALID"
    assert resolved["error_absolute"] == pytest.approx(0.0005)
    assert resolved["baseline_error_absolute"] == pytest.approx(0.0013)
    assert resolved["friction_adjusted_return"] < resolved["gross_return"]


@pytest.mark.parametrize(
    "issued,target,resolved,cutoff",
    [
        ("2026-10-06T10:00:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:00:01Z"),
        ("2026-10-06T10:00:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:00:00Z"),
        ("2026-10-06T10:06:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:05:00Z", "2026-10-06T09:59:00Z"),
        ("2026-10-06T10:00:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:04:00Z", "2026-10-06T09:59:00Z"),
    ],
)
def test_temporal_violations_are_invalid(issued, target, resolved, cutoff):
    with pytest.raises(ValueError, match="INVALID temporal ordering"):
        validate_window(issued, target, resolved, cutoff)


def test_schema_digest_changes_when_observation_changes():
    kwargs = prediction() | {
        "resolved_at": "2026-10-06T10:05:00Z",
        "actual": 0.0015,
        "baseline_prediction": 0.0002,
        "error_absolute": 0.0005,
        "baseline_error_absolute": 0.0013,
        "direction_hit": True,
        "gross_return": 0.0015,
        "spread_cost": 0.00002,
        "slippage_cost": 0.0,
        "commission_cost": 0.0,
        "friction_adjusted_return": 0.00148,
    }
    a = Observation(**kwargs)
    b = Observation(**{**kwargs, "actual": 0.0016})
    assert a.digest() != b.digest()


def test_ledger_is_append_only_and_detects_tampering(tmp_path: Path):
    p = prediction()
    resolved = resolve(p, actual=0.0015, baseline_prediction=0.0002,
                       resolved_at="2026-10-06T10:05:00Z")
    obs = Observation(**resolved)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    first_hash = ledger.append(obs)
    assert ledger.verify() is True
    # Retry after an interrupted state commit must not duplicate the ledger row.
    assert ledger.append(obs) == first_hash
    assert len(ledger._rows()) == 1

    row = json.loads(ledger.path.read_text().splitlines()[0])
    row["actual"] = 0.9
    ledger.path.write_text(json.dumps(row) + "\n")
    assert ledger.verify() is False



@pytest.mark.parametrize(
    "legacy_fields",
    [
        {
            "provider": "Yahoo",
            "source_candle_ts": "",
            "observed_at": "",
            "data_age_seconds": 0.0,
            "freshness_limit_seconds": 90.0,
            "freshness_status": "FRESH",
        },
        {
            "provider": None,
            "source_candle_ts": None,
            "observed_at": None,
            "data_age_seconds": None,
            "freshness_limit_seconds": None,
            "freshness_status": None,
        },
    ],
)
def test_legacy_observation_without_provenance_is_quarantined(legacy_fields):
    legacy_prediction = prediction()
    for key in ("data_mode", "provider", "source_candle_ts", "freshness_status"):
        legacy_prediction.pop(key, None)
    legacy_prediction.update(legacy_fields)
    resolved = resolve(
        legacy_prediction,
        actual=0.0015,
        baseline_prediction=0.0002,
        resolved_at="2026-10-06T10:05:00Z",
    )
    observation = Observation(**resolved)
    assert observation.data_mode == "UNVERIFIED"
    assert observation.status == "INVALID"
    assert observation.provider == "UNVERIFIED"
    assert observation.freshness_status == "UNVERIFIED"


def test_arena_and_preregistered_verdict():
    rows = []
    for i in range(100):
        rows.append({
            "status": "VALID",
            "data_mode": "HISTORICAL",
            "provider": "test-historical",
            "source_candle_ts": "2026-10-06T09:55:00Z",
            "freshness_status": "NOT_APPLICABLE",
            "feature_cutoff_at": "2026-10-06T09:59:59Z",
            "issued_at": "2026-10-06T10:00:00Z",
            "target_at": "2026-10-06T10:05:00Z",
            "resolved_at": "2026-10-06T10:05:00Z",
            "actual": 1.0,
            "prediction": 1.0,
            "baseline_prediction": 0.0,
            "friction_adjusted_return": 0.9,
            "direction_hit": True,
        })
    stats = score(rows)
    assert stats["n"] == 100
    assert stats["temporal_rejected"] == 0
    assert stats["mae_delta"] == pytest.approx(1.0)
    assert verdict(stats, min_n=100) == "SURVIVES"
    assert verdict({**stats, "mae_delta_ci_lower": 0.0}, min_n=100) == "KILLED"
    assert verdict({**stats, "n": 99}, min_n=100) == "INSUFFICIENT_DATA"
    assert verdict({**stats, "effective_n": 99}, min_n=100) == "INSUFFICIENT_DATA"
    assert verdict({**stats, "effective_n": None}, min_n=100) == "INSUFFICIENT_DATA"


def test_arena_rejects_equal_cutoff_and_issue_timestamp():
    row = {
        "status": "VALID",
        "data_mode": "HISTORICAL",
        "provider": "test-historical",
        "source_candle_ts": "2026-10-06T09:55:00Z",
        "freshness_status": "NOT_APPLICABLE",
        "feature_cutoff_at": "2026-10-06T10:00:00Z",
        "issued_at": "2026-10-06T10:00:00Z",
        "target_at": "2026-10-06T10:05:00Z",
        "resolved_at": "2026-10-06T10:05:00Z",
        "actual": 1.0,
        "prediction": 1.0,
        "baseline_prediction": 0.0,
        "friction_adjusted_return": 0.9,
        "direction_hit": True,
    }
    stats = score([row])
    assert stats["n"] == 0
    assert stats["temporal_rejected"] == 1
    assert stats["status"] == "INSUFFICIENT_DATA"



def test_arena_excludes_unverified_legacy_rows():
    row = {
        "status": "VALID",
        "data_mode": "UNVERIFIED",
        "provider": "UNVERIFIED",
        "freshness_status": "UNVERIFIED",
        "actual": 1.0,
        "prediction": 1.0,
        "baseline_prediction": 0.0,
        "friction_adjusted_return": 0.9,
        "direction_hit": True,
        "feature_cutoff_at": "2026-10-06T09:59:59Z",
        "issued_at": "2026-10-06T10:00:00Z",
        "target_at": "2026-10-06T10:05:00Z",
        "resolved_at": "2026-10-06T10:05:00Z",
    }
    stats = score([row])
    assert stats["n"] == 0
    assert stats["provenance_rejected"] == 1
    assert stats["status"] == "INSUFFICIENT_DATA"


def test_live_observation_rejects_evidence_observed_after_issuance():
    live = prediction() | {
        "data_mode": "LIVE",
        "provider": "twelvedata",
        "source_candle_ts": "2026-10-06T09:59:00Z",
        "observed_at": "2026-10-06T10:00:01Z",
        "data_age_seconds": 1.0,
        "freshness_limit_seconds": 90.0,
        "freshness_status": "FRESH",
        "feature_cutoff_at": "2026-10-06T09:59:59Z",
        "issued_at": "2026-10-06T10:00:00Z",
    }
    resolved = resolve(
        live,
        actual=0.0015,
        baseline_prediction=0.0002,
        resolved_at="2026-10-06T10:05:00Z",
    )
    with pytest.raises(ValueError, match="LIVE_OBSERVED_AFTER_ISSUED"):
        Observation(**resolved)


def test_arena_rejects_live_provenance_observed_after_issuance():
    row = {
        "status": "VALID",
        "data_mode": "LIVE",
        "provider": "twelvedata",
        "source_candle_ts": "2026-10-06T09:59:00Z",
        "observed_at": "2026-10-06T10:00:01Z",
        "data_age_seconds": 1.0,
        "freshness_limit_seconds": 90.0,
        "freshness_status": "FRESH",
        "feature_cutoff_at": "2026-10-06T09:59:59Z",
        "issued_at": "2026-10-06T10:00:00Z",
        "target_at": "2026-10-06T10:05:00Z",
        "resolved_at": "2026-10-06T10:05:00Z",
        "actual": 1.0,
        "prediction": 1.0,
        "baseline_prediction": 0.0,
        "friction_adjusted_return": 0.9,
        "direction_hit": True,
    }
    stats = score([row])
    assert stats["n"] == 0
    assert stats["provenance_rejected"] == 1
    assert stats["status"] == "INSUFFICIENT_DATA"


def test_arena_uses_conservative_overlap_horizon_for_live_rows(monkeypatch):
    import claimlab.arena as arena_module

    row = {
        "status": "VALID", "data_mode": "LIVE", "provider": "yahoo",
        "source_candle_ts": "2026-10-06T09:59:00Z",
        "feature_cutoff_at": "2026-10-06T10:00:00Z",
        "observed_at": "2026-10-06T10:00:10Z",
        "issued_at": "2026-10-06T10:00:20Z",
        "target_at": "2026-10-06T10:05:59Z",
        "resolved_at": "2026-10-06T10:05:59Z",
        "freshness_status": "FRESH", "data_age_seconds": 20.0,
        "freshness_limit_seconds": 90.0, "horizon_seconds": 339,
        "actual": 0.001, "prediction": 0.001, "baseline_prediction": 0.0,
        "friction_adjusted_return": 0.0009, "direction_hit": True,
    }
    captured = {}
    def fake_summarize(rows, **kwargs):
        captured.update(kwargs)
        return {"n": len(rows)}
    monkeypatch.setattr(arena_module.StatisticalEngine, "summarize", fake_summarize)
    stats = arena_module.score([row], bootstrap_resamples=10)
    assert stats["overlap_horizon_minutes"] == 6
    assert captured["horizon"] == 6


def test_arena_rejects_rows_missing_temporal_evidence():
    row = {
        "status": "VALID", "data_mode": "HISTORICAL",
        "provider": "test-historical", "source_candle_ts": "2026-10-06T09:55:00Z",
        "freshness_status": "NOT_APPLICABLE",
        "feature_cutoff_at": "2026-10-06T09:59:59Z",
    }
    stats = score([row])
    assert stats["n"] == 0
    assert stats["status"] == "INSUFFICIENT_DATA"

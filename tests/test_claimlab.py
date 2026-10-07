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
        "schema_version": "claimlab.observation.v1",
        "prediction_id": "p-001",
        "issued_at": "2026-10-06T10:00:00Z",
        "target_at": "2026-10-06T10:05:00Z",
        "feature_cutoff_at": "2026-10-06T10:00:00Z",
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
        ("2026-10-06T10:06:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:00:00Z"),
        ("2026-10-06T10:00:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:04:00Z", "2026-10-06T10:00:00Z"),
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


def test_arena_and_preregistered_verdict():
    rows = []
    for i in range(100):
        rows.append({
            "status": "VALID",
            "actual": 1.0,
            "prediction": 1.0,
            "baseline_prediction": 0.0,
            "friction_adjusted_return": 0.9,
            "direction_hit": True,
        })
    stats = score(rows)
    assert stats["n"] == 100
    assert stats["mae_delta"] == pytest.approx(1.0)
    assert verdict(stats, min_n=100) == "SURVIVES"
    assert verdict({**stats, "mae_delta_ci_lower": 0.0}, min_n=100) == "KILLED"
    assert verdict({**stats, "n": 99}, min_n=100) == "INSUFFICIENT_DATA"

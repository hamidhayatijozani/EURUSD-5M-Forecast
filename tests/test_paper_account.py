import json
from pathlib import Path

from scripts.paper_account import evaluate


def row(pid="p1", predicted=0.001, actual=0.002, issued="2026-10-17T10:01:00+00:00",
        target="2026-10-17T10:06:00+00:00", resolved="2026-10-17T10:06:00+00:00",
        cutoff="2026-10-17T10:00:00+00:00", age=20, freshness="FRESH",
        contract="freshness-90s-v2", status="RESOLVED"):
    return {
        "prediction_id": pid, "data_contract_version": contract, "status": status,
        "prediction_ts": issued, "feature_cutoff_at": cutoff, "target_at": target,
        "resolved_at": resolved, "data_age_seconds": age, "freshness_limit_seconds": 90,
        "freshness_status": freshness, "predicted_return": predicted, "actual_return": actual,
    }


def test_paper_account_only_uses_fresh_temporally_valid_settlements():
    summary, trades = evaluate([
        row("valid"),
        row("stale", age=900),
        row("leak", cutoff="2026-10-17T10:02:00+00:00"),
        row("pending", status="PENDING"),
    ])
    assert summary["eligible_resolved_predictions"] == 1
    assert len(trades) == 1
    assert trades[0]["side"] == "LONG"
    assert summary["edge_claim_allowed"] is False
    assert summary["profitability_claim_allowed"] is False


def test_short_trade_and_cost_sensitivity_are_accounted_for():
    summary, trades = evaluate([row("short", predicted=-0.001, actual=-0.001)])
    assert trades[0]["side"] == "SHORT"
    assert trades[0]["net_return"] == 0.001 - 0.00002
    assert len(summary["scenarios"]) == 3


def test_flat_prediction_does_not_trade():
    summary, trades = evaluate([row("flat", predicted=0.00001)])
    assert trades == []
    assert summary["scenarios"]["2e-05"]["trade_count"] == 0


def test_drawdown_circuit_breaker_halts_new_trades():
    rows = []
    for i in range(10):
        rows.append(row(
            pid=f"loss-{i}", predicted=0.001, actual=-0.10,
            issued=f"2026-10-17T10:{i+1:02d}:00+00:00",
            target=f"2026-10-17T10:{i+6:02d}:00+00:00",
            resolved=f"2026-10-17T10:{i+6:02d}:00+00:00",
            cutoff=f"2026-10-17T10:{i:02d}:00+00:00",
        ))
    summary, trades = evaluate(rows)
    assert summary["scenarios"]["2e-05"]["halted_at_drawdown_limit"] is True
    assert len(trades) < len(rows)

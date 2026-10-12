import pytest

from scripts.report_cross_repo_features import build_report


def row(pid="p1", status="RESOLVED", cutoff="2026-10-12T03:00:00+00:00"):
    return {
        "prediction_id": pid,
        "prediction_ts": "2026-10-12T03:00:00+00:00",
        "target_at": "2026-10-12T03:05:00+00:00",
        "resolved_at": "2026-10-12T03:05:02+00:00",
        "status": status,
        "actual_return": 0.0002,
        "predicted_return": 0.0001,
        "baseline_prediction": 0.0,
        "experimental_feature_snapshot": {
            "schema": "cross_repo_feature_snapshot.v1",
            "status": "READY",
            "feature_version": "cross_repo_features.v1",
            "feature_cutoff_at": cutoff,
            "source_timeframe": "1m",
            "values": {
                "pressure": 0.2,
                "novelty": 0.5,
                "tenacity": 0.7,
                "realized_volatility": 0.001,
                "trend_efficiency": 0.4,
            },
        },
    }


def test_empty_data_is_insufficient_and_never_claims_performance():
    report = build_report([])
    assert report["verdict"] == "INSUFFICIENT_DATA"
    assert report["performance_claim_permitted"] is False
    assert report["counts"]["resolved_valid_joined_observations"] == 0


def test_valid_resolved_snapshot_joins_to_exact_target():
    report = build_report([row()])
    assert report["counts"]["resolved_valid_joined_observations"] == 1
    assert report["verdict"] == "INSUFFICIENT_DATA"
    assert report["descriptive_errors"]["engine_mae"] == pytest.approx(0.0001)
    assert report["performance_claim_permitted"] is False


def test_future_cutoff_is_rejected():
    report = build_report([row(cutoff="2026-10-12T03:01:00+00:00")])
    assert report["counts"]["invalid_or_temporally_unverifiable_snapshots"] == 1
    assert report["counts"]["resolved_valid_joined_observations"] == 0


def test_unavailable_snapshot_is_not_counted_as_valid():
    item = row()
    item["experimental_feature_snapshot"] = {"status": "UNAVAILABLE", "reason": "bad input"}
    report = build_report([item])
    assert report["counts"]["snapshots_unavailable_or_unknown"] == 1
    assert report["counts"]["resolved_valid_joined_observations"] == 0


def test_duplicate_prediction_ids_are_excluded_from_sample_size():
    report = build_report([row("same"), row("same")])
    assert report["counts"]["duplicate_prediction_ids"] == 1
    assert report["counts"]["resolved_valid_joined_observations"] == 1

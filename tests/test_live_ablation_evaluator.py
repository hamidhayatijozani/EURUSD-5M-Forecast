from scripts.evaluate_live_ablation import (
    CONTRACT,
    evaluate_cross_asset,
    evaluate_predictions,
    resolved_current_rows,
    score_signal,
)


def test_score_signal_respects_friction_and_abstention():
    result = score_signal([
        (0.001, 0.001),
        (-0.001, -0.001),
        (0.001, -0.001),
        (-0.001, 0.001),
        (0.00001, 0.0),
    ])
    assert result["n"] == 5
    assert result["active_n"] == 5
    assert result["hits"] == 2
    assert result["hit_rate_all"] == 0.4
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["bootstrap_status"] == "INSUFFICIENT_DATA_FOR_BLOCK_CI"


def test_resolved_rows_are_filtered_to_one_contract_and_unique_ids():
    rows = [
        {"prediction_id": "a", "data_contract_version": CONTRACT, "status": "RESOLVED",
         "actual_return": 0.1, "predicted_return": 0.2},
        {"prediction_id": "b", "data_contract_version": "legacy", "status": "RESOLVED",
         "actual_return": 0.1, "predicted_return": 0.2},
        {"prediction_id": "c", "data_contract_version": CONTRACT, "status": "PENDING",
         "actual_return": None, "predicted_return": 0.2},
    ]
    assert [row["prediction_id"] for row in resolved_current_rows(rows)] == ["a"]


def test_duplicate_current_contract_ids_are_rejected():
    row = {"prediction_id": "same", "data_contract_version": CONTRACT, "status": "RESOLVED",
           "actual_return": 0.1, "predicted_return": 0.2}
    try:
        resolved_current_rows([row, dict(row)])
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate prediction IDs must be rejected")


def test_prediction_report_marks_missing_external_context_unavailable():
    rows = []
    for i in range(12):
        rows.append({
            "prediction_id": f"p{i}",
            "target_at": f"2026-10-12T00:{i:02d}:00+00:00",
            "data_contract_version": CONTRACT,
            "status": "RESOLVED",
            "actual_return": 0.0001 if i % 2 == 0 else -0.0001,
            "predicted_return": 0.0001 if i % 3 else -0.0001,
            "baseline_prediction": 0.0001,
            "algorithms": [{"name": "MOM_2", "predicted_return": 0.0001}],
            "external_context": {"directional_sources_available": 0, "context_score": 0.0},
        })
    report = evaluate_predictions(rows)
    assert report["n"] == 12
    assert report["common_cohort"] is True
    assert report["strategies"]["ensemble"]["n"] == 12
    assert report["strategies"]["algorithm:MOM_2"]["n"] == 12
    assert report["strategies"]["context_only_proxy"]["status"] == "UNAVAILABLE_NO_DIRECTIONAL_CONTEXT"


def test_cross_asset_report_uses_recorded_net_return_and_marks_small_n():
    rows = [
        {"schema": "claimlab.live_cross_asset_observation.v1", "candidate_id": "A",
         "actual_return": 0.001, "position": 1, "net_return": 0.00098,
         "friction": 0.00002, "freshness_status": "FRESH", "target_at": "2026-10-12T00:05:00Z"},
        {"schema": "claimlab.live_cross_asset_observation.v1", "candidate_id": "A",
         "actual_return": -0.001, "position": 1, "net_return": -0.00102,
         "friction": 0.00002, "freshness_status": "FRESH", "target_at": "2026-10-12T00:06:00Z"},
    ]
    report = evaluate_cross_asset(rows)
    candidate = report["candidates"]["A"]
    assert candidate["n"] == 2
    assert candidate["active_n"] == 2
    assert abs(candidate["recorded_net_return_sum"] - (-0.00004)) < 1e-12
    assert candidate["status"] == "INSUFFICIENT_DATA"


def test_zero_signal_candidate_is_not_reported_as_scored():
    result = score_signal([(0.0, 0.001)] * 12)
    assert result["status"] == "NO_ACTIVE_SIGNALS"
    assert result["active_n"] == 0
    assert result["coverage"] == 0.0
    assert result["net_return_sum"] == 0.0
    assert result["block_bootstrap_95ci_mean_net_per_forecast"] == [0.0, 0.0]

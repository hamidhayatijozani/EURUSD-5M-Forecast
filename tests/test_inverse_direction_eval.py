from scripts.evaluate_inverse_direction import evaluate, wilson_interval


def test_inverse_complements_original_on_resolvable_nonzero_moves():
    rows = [
        {"status": "VALID", "horizon_seconds": 300, "prediction": 1.0, "actual": 0.1, "spread_cost": 0.01},
        {"status": "VALID", "horizon_seconds": 300, "prediction": -1.0, "actual": 0.1, "spread_cost": 0.01},
    ]
    result = evaluate(rows)
    assert result["rows"] == 2
    assert result["directionally_resolvable_rows"] == 2
    assert result["original"]["hits"] == 1
    assert result["inverse"]["hits"] == 1
    assert result["original"]["hits"] + result["inverse"]["hits"] == 2


def test_zero_or_friction_sized_moves_are_not_directional_hits():
    rows = [
        {"status": "VALID", "horizon_seconds": 300, "prediction": 1.0, "actual": 0.0, "spread_cost": 0.01},
        {"status": "VALID", "horizon_seconds": 300, "prediction": -1.0, "actual": -0.01, "spread_cost": 0.01},
    ]
    result = evaluate(rows)
    assert result["rows"] == 2
    assert result["directionally_resolvable_rows"] == 0
    assert result["original"]["hits"] == 0
    assert result["inverse"]["hits"] == 0


def test_non_valid_or_other_horizon_rows_are_excluded():
    rows = [
        {"status": "PENDING", "horizon_seconds": 300, "prediction": 1.0, "actual": 0.1},
        {"status": "VALID", "horizon_seconds": 60, "prediction": 1.0, "actual": 0.1},
    ]
    result = evaluate(rows)
    assert result["rows"] == 0
    assert result["original"]["hit_rate_all_rows"] is None
    assert result["inverse"]["hit_rate_all_rows"] is None


def test_wilson_interval_handles_empty_sample():
    assert wilson_interval(0, 0) is None

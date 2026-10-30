from copy import deepcopy

from claimlab.walkforward import cost_sensitivity


def _row(prediction, actual, baseline=0.0):
    return {
        "status": "VALID",
        "feature_cutoff_at": "2026-10-06T09:59:59Z",
        "issued_at": "2026-10-06T10:00:00Z",
        "target_at": "2026-10-06T10:05:00Z",
        "resolved_at": "2026-10-06T10:05:00Z",
        "prediction": prediction,
        "baseline_prediction": baseline,
        "actual": actual,
        "error_absolute": abs(actual - prediction),
        "baseline_error_absolute": abs(actual - baseline),
        "direction_hit": False,
        "gross_return": 0.0,
        "spread_cost": 0.00002,
        "slippage_cost": 0.0,
        "commission_cost": 0.0,
        "friction_adjusted_return": -0.00002,
    }


def test_cost_sensitivity_reprices_frozen_predictions_without_mutating_input():
    rows = [_row(0.0001, 0.00004), _row(-0.0001, -0.0002), _row(0.0001, -0.0001)]
    original = deepcopy(rows)

    result = cost_sensitivity(rows, bootstrap_resamples=100)

    assert rows == original
    scenarios = result["scenarios"]
    low_key = "spread_0.2pip_slippage_0.00pip"
    low_slip_key = "spread_0.2pip_slippage_0.10pip"
    medium_key = "spread_0.5pip_slippage_0.10pip"
    high_key = "spread_1.0pip_slippage_0.25pip"
    assert set(scenarios) == {low_key, low_slip_key, medium_key, high_key}
    assert scenarios[low_key]["total_round_trip_cost"] == 0.00002
    assert scenarios[low_slip_key]["total_round_trip_cost"] == 0.00003
    assert scenarios[medium_key]["total_round_trip_cost"] == 0.00006
    assert scenarios[high_key]["total_round_trip_cost"] == 0.000125
    assert scenarios[medium_key]["commission_cost"] == 0.0

    low = scenarios[low_key]["metrics"]
    low_slip = scenarios[low_slip_key]["metrics"]
    medium = scenarios[medium_key]["metrics"]
    high = scenarios[high_key]["metrics"]
    assert low["n"] == low_slip["n"] == medium["n"] == high["n"] == 3
    assert low["friction_adjusted_return"] > low_slip["friction_adjusted_return"]
    assert low_slip["friction_adjusted_return"] > medium["friction_adjusted_return"]
    assert medium["friction_adjusted_return"] > high["friction_adjusted_return"]
    assert low["hit_rate"] >= low_slip["hit_rate"] >= medium["hit_rate"] >= high["hit_rate"]


def test_cost_sensitivity_rejects_negative_costs():
    import pytest

    with pytest.raises(ValueError, match="NEGATIVE_COST_SCENARIO"):
        cost_sensitivity([_row(0.0001, 0.0002)], scenarios=((-0.1, 0.0),))

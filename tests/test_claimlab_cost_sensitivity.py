from copy import deepcopy

from claimlab.walkforward import cost_sensitivity


def _row(prediction, actual, baseline=0.0):
    return {
        "status": "VALID",
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
    assert set(scenarios) == {"0.2_pip", "0.5_pip", "1.0_pip"}
    assert scenarios["0.2_pip"]["total_round_trip_cost"] == 0.00002
    assert scenarios["0.5_pip"]["total_round_trip_cost"] == 0.00005
    assert scenarios["1.0_pip"]["total_round_trip_cost"] == 0.0001

    low = scenarios["0.2_pip"]["metrics"]
    medium = scenarios["0.5_pip"]["metrics"]
    high = scenarios["1.0_pip"]["metrics"]
    assert low["n"] == medium["n"] == high["n"] == 3
    assert low["friction_adjusted_return"] > medium["friction_adjusted_return"]
    assert medium["friction_adjusted_return"] > high["friction_adjusted_return"]
    assert low["hit_rate"] >= medium["hit_rate"] >= high["hit_rate"]


def test_cost_sensitivity_rejects_negative_costs():
    import pytest

    with pytest.raises(ValueError, match="NEGATIVE_COST_SCENARIO"):
        cost_sensitivity([_row(0.0001, 0.0002)], scenarios_pips=(-0.1,))

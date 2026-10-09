from datetime import datetime, timedelta, timezone

from scripts.live_minute_loop import LIVE_DATA_CONTRACT_VERSION, _prediction_times, _quarantine_legacy_predictions


def test_live_prediction_times_match_exact_five_minute_close_horizon():
    bar_open = datetime(2026, 10, 7, 0, 23, tzinfo=timezone.utc)
    issued, target_bar_open, target_at = _prediction_times(bar_open)
    assert issued == bar_open + timedelta(minutes=1)
    assert target_bar_open == bar_open + timedelta(minutes=5)
    assert target_at == bar_open + timedelta(minutes=6)
    assert (target_at - issued).total_seconds() == 300


def test_contract_version_is_explicit_for_clean_live_evidence():
    assert LIVE_DATA_CONTRACT_VERSION == "freshness-90s-v1"


def test_legacy_pending_predictions_are_quarantined_not_backfilled():
    rows = [
        {"prediction_id": "old-1", "status": "PENDING"},
        {"prediction_id": "new-1", "status": "PENDING", "data_contract_version": LIVE_DATA_CONTRACT_VERSION},
    ]
    changed = _quarantine_legacy_predictions(rows)
    assert changed is True
    assert rows[0]["status"] == "EXCLUDED_PRE_CONTRACT"
    assert rows[1]["status"] == "PENDING"


def test_predict_uses_pst_when_cross_asset_series_are_unavailable():
    from scripts.live_minute_loop import predict

    closes = [1.1 + (i % 7 - 3) * 0.0001 for i in range(60)]
    ohlc = [(value, value + 0.0002, value - 0.0002, value) for value in closes]
    state = {"bias": 0.0, "algorithms": {}}
    context = {"context_score": 0.0, "power_score": 0.0}
    result = predict({"EURUSD": closes}, ohlc, state, context)
    assert result[0].name == "EXP-006"


def test_claimlab_observation_requires_fresh_evidence():
    import pytest
    from claimlab.schema import Observation
    base = dict(
        schema_version="claimlab.observation.v1", prediction_id="fresh-1",
        issued_at="2026-10-07T00:37:00+00:00", target_at="2026-10-07T00:42:00+00:00",
        resolved_at="2026-10-07T00:42:00+00:00", symbol="EURUSD", horizon_seconds=300,
        prediction=0.0001, actual=0.0, baseline_prediction=0.0,
        error_absolute=0.0, baseline_error_absolute=0.0, direction_hit=False,
        gross_return=0.0, spread_cost=0.00002, slippage_cost=0.0, commission_cost=0.0,
        friction_adjusted_return=-0.00002, feature_cutoff_at="2026-10-07T00:37:00+00:00",
        code_commit="test", config_hash="cfg", claim_registry_hash="reg",
        provider="Yahoo", source_candle_ts="2026-10-07T00:38:00+00:00",
        observed_at="2026-10-07T00:38:20+00:00", data_age_seconds=20.0,
        freshness_limit_seconds=90.0, freshness_status="FRESH",
    )
    Observation(**base)
    with pytest.raises(ValueError, match="freshness limit"):
        Observation(**{**base, "data_age_seconds": 91.0})


def test_freshness_age_is_measured_from_candle_close_not_open():
    from scripts.live_minute_loop import _freshness_age_seconds

    candle_open = datetime(2026, 10, 9, 10, 3, tzinfo=timezone.utc)
    observed_at = candle_open + timedelta(seconds=145)
    assert _freshness_age_seconds(candle_open, observed_at) == 85.0
    observed_at = candle_open + timedelta(seconds=149)
    assert _freshness_age_seconds(candle_open, observed_at) == 89.0

from datetime import datetime, timedelta, timezone

from scripts.live_minute_loop import LIVE_DATA_CONTRACT_VERSION, _prediction_times


def test_live_prediction_times_match_exact_five_minute_close_horizon():
    bar_open = datetime(2026, 10, 7, 0, 23, tzinfo=timezone.utc)
    issued, target_bar_open, target_at = _prediction_times(bar_open)
    assert issued == bar_open + timedelta(minutes=1)
    assert target_bar_open == bar_open + timedelta(minutes=5)
    assert target_at == bar_open + timedelta(minutes=6)
    assert (target_at - issued).total_seconds() == 300


def test_contract_version_is_explicit_for_clean_live_evidence():
    assert LIVE_DATA_CONTRACT_VERSION == "freshness-90s-v1"

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

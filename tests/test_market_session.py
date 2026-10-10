from datetime import datetime, timezone
import pytest

from engine.market_session import expected_weekend_closure


def test_saturday_is_expected_fx_weekend_closure():
    assert expected_weekend_closure(datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc))


def test_friday_after_1700_new_york_is_closed():
    # 2026-10-09 21:30 UTC = 17:30 EDT in New York.
    assert expected_weekend_closure(datetime(2026, 10, 9, 21, 30, tzinfo=timezone.utc))


def test_sunday_before_1700_new_york_is_closed():
    # 2026-10-11 20:00 UTC = 16:00 EDT in New York.
    assert expected_weekend_closure(datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc))


def test_sunday_after_1700_new_york_is_open():
    # 2026-10-11 21:30 UTC = 17:30 EDT in New York.
    assert not expected_weekend_closure(datetime(2026, 10, 11, 21, 30, tzinfo=timezone.utc))


def test_midweek_is_not_assumed_closed():
    assert not expected_weekend_closure(datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc))


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError):
        expected_weekend_closure(datetime(2026, 10, 10, 6, 0))

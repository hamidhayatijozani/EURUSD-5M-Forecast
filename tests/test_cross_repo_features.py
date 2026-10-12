import math

import pytest

from engine.cross_repo_features import cross_repo_features, cross_repo_feature_snapshot


def test_features_are_finite_and_have_documented_keys():
    closes = [1.1000 + i * 0.0001 + (0.00003 if i % 2 else 0) for i in range(15)]
    result = cross_repo_features(closes, window=12)
    assert set(result) == {
        "pressure", "novelty", "tenacity", "realized_volatility", "trend_efficiency"
    }
    assert all(math.isfinite(value) for value in result.values())
    assert 0.0 <= result["tenacity"] <= 1.0
    assert result["novelty"] >= 0.0
    assert result["realized_volatility"] >= 0.0
    assert 0.0 <= result["trend_efficiency"] <= 1.0


def test_feature_values_ignore_prices_older_than_requested_window():
    recent = [1.1000 + i * 0.0001 + (0.00002 if i % 2 else 0) for i in range(13)]
    a = cross_repo_features([0.5, 0.7, *recent], window=12)
    b = cross_repo_features([9.0, 8.0, *recent], window=12)
    assert a == b


def test_rejects_insufficient_observations():
    with pytest.raises(ValueError, match="at least 13 closes"):
        cross_repo_features([1.1] * 12, window=12)


@pytest.mark.parametrize("bad", [0, -1.0, float("nan"), float("inf")])
def test_rejects_non_positive_or_non_finite_prices(bad):
    closes = [1.1 + i * 0.0001 for i in range(13)]
    closes[-1] = bad
    with pytest.raises(ValueError, match="finite positive"):
        cross_repo_features(closes, window=12)


def test_rejects_constant_price_window_instead_of_inventing_normalized_values():
    with pytest.raises(ValueError, match="zero-return window"):
        cross_repo_features([1.1] * 13, window=12)


@pytest.mark.parametrize("window", [0, 3, True, 4.5])
def test_rejects_invalid_window(window):
    with pytest.raises(ValueError, match="window must be an integer"):
        cross_repo_features([1.1 + i * 0.0001 for i in range(13)], window=window)


def test_snapshot_records_cutoff_and_feature_version():
    closes = [1.1000 + i * 0.0001 + (0.00003 if i % 2 else 0) for i in range(13)]
    snapshot = cross_repo_feature_snapshot(closes, issued_at="2026-10-12T03:00:00+00:00")
    assert snapshot["status"] == "READY"
    assert snapshot["feature_cutoff_at"] == "2026-10-12T03:00:00+00:00"
    assert snapshot["source_timeframe"] == "1m"
    assert snapshot["feature_version"] == "cross_repo_features.v1"


def test_snapshot_is_failure_isolated_for_degenerate_prices():
    snapshot = cross_repo_feature_snapshot([1.1] * 13, issued_at="2026-10-12T03:00:00+00:00")
    assert snapshot == {
        "schema": "cross_repo_feature_snapshot.v1",
        "status": "UNAVAILABLE",
        "reason": "INVALID_OR_DEGENERATE_INPUT",
    }


def test_snapshot_is_failure_isolated_for_missing_timestamp():
    snapshot = cross_repo_feature_snapshot([1.1] * 13, issued_at="")
    assert snapshot["status"] == "UNAVAILABLE"
    assert snapshot["reason"] == "INVALID_ISSUED_AT"

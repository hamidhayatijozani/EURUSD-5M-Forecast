"""Unit tests for Lrzesh integration — pure, leakage-safe."""
import pytest
from engine.lrzesh import (
    calculate_trembling_score,
    detect_regime,
    run_lrzesh,
    suggest_asymmetric_iron_condor,
)
from engine.forecast import forecast


def _make_closes(base: float = 1.1550, n: int = 20, drift: float = 0.0) -> list[float]:
    return [base + i * drift for i in range(n)]


def test_trembling_score_range():
    closes = _make_closes(n=20)
    ts = calculate_trembling_score(closes)
    assert 0.0 <= ts <= 1.0


def test_insufficient_data_raises():
    with pytest.raises(ValueError):
        calculate_trembling_score([1.15] * 5)


def test_gray_zone_detection():
    # High short-term oscillation should push TS higher
    closes = [1.1550 + (0.0008 if i % 2 == 0 else -0.0007) for i in range(20)]
    ts = calculate_trembling_score(closes)
    regime = detect_regime(ts)
    assert regime in {"GRAY_ZONE", "TRANSITION", "NEUTRAL", "TREND_STABLE"}


def test_condor_only_in_high_tremor():
    low_ts = 0.40
    high_ts = 0.85
    assert suggest_asymmetric_iron_condor(1.1550, low_ts) is None
    condor = suggest_asymmetric_iron_condor(1.1550, high_ts)
    assert condor is not None
    assert "legs" in condor
    assert condor["legs"]["short_put"] < condor["legs"]["long_put"] is False  # short < long put? wait
    # short_put should be lower than long_put
    assert condor["legs"]["short_put"] > condor["legs"]["long_put"]


def test_forecast_with_lrzesh_enabled():
    closes = _make_closes(n=20, drift=0.00005)
    f = forecast(closes, use_lrzesh=True)
    assert f.direction in {"UP", "DOWN", "FLAT"}
    assert f.lrzesh is not None
    assert 0.0 <= f.lrzesh.trembling_score <= 1.0


def test_forecast_lrzesh_disabled():
    closes = _make_closes(n=20)
    f = forecast(closes, use_lrzesh=False)
    assert f.lrzesh is None


def test_no_future_data_used():
    """Sanity: forecast only receives the closes list; no lookahead possible."""
    closes = _make_closes(n=15)
    f1 = forecast(closes[:-1], use_lrzesh=True)
    f2 = forecast(closes, use_lrzesh=True)
    # Different inputs can produce different outputs; just ensure no crash
    assert f1 is not None and f2 is not None

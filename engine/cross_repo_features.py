"""Deterministic experimental market features inspired by cross-repo concepts.

These are descriptive features, not validated signals or a trading strategy.
Callers are responsible for passing only closed candles available at issue time.
"""
from math import isfinite, sqrt
from typing import Sequence


def cross_repo_features(closes: Sequence[float], *, window: int = 12) -> dict[str, float]:
    """Compute P/S/T-inspired descriptors from a past-only close-price window.

    Requires at least window + 1 positive, finite closes. No I/O, timestamps,
    model fitting, or future-data access occurs in this function.
    """
    if not isinstance(window, int) or isinstance(window, bool) or window < 4:
        raise ValueError("window must be an integer >= 4")
    if len(closes) < window + 1:
        raise ValueError(f"at least {window + 1} closes are required")
    values = [float(value) for value in closes[-(window + 1):]]
    if any(not isfinite(value) or value <= 0 for value in values):
        raise ValueError("closes must be finite positive prices")

    returns = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    if any(not isfinite(value) for value in returns):
        raise ValueError("returns must be finite")

    prior = returns[:-1]
    prior_scale = sum(abs(value) for value in prior) / len(prior)
    all_scale = sum(abs(value) for value in returns) / len(returns)
    if prior_scale == 0 or all_scale == 0:
        raise ValueError("zero-return window cannot support normalized features")

    recent_three = returns[-3:]
    pressure = sum(recent_three) / prior_scale
    novelty = abs(returns[-1]) / prior_scale
    net_return = values[-1] / values[0] - 1.0
    trend_efficiency = abs(net_return) / sum(abs(value) for value in returns)

    nonzero_signs = [1 if value > 0 else -1 for value in returns if value != 0]
    if not nonzero_signs:
        raise ValueError("tenacity is undefined without non-zero returns")
    signed_sum = sum(nonzero_signs)
    dominant_sign = 1 if signed_sum >= 0 else -1
    tenacity = sum(sign == dominant_sign for sign in nonzero_signs) / len(nonzero_signs)
    realized_volatility = sqrt(sum(value * value for value in returns) / len(returns))

    result = {
        "pressure": pressure,
        "novelty": novelty,
        "tenacity": tenacity,
        "realized_volatility": realized_volatility,
        "trend_efficiency": trend_efficiency,
    }
    if any(not isfinite(value) for value in result.values()):
        raise ValueError("computed features must be finite")
    return result

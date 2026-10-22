"""Lrzesh (لرزش) — Trembling Score, Gray Zone detection, and asymmetric range strategy.

Pure, leakage-safe module. No future data, no network calls, no side effects.
Designed to plug into the existing temporal-validity contract of EURUSD-5M-Forecast.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class LrzeshResult:
    trembling_score: float          # 0.0 – 1.0
    regime: str                     # GRAY_ZONE | TREND_STABLE | TRANSITION | NEUTRAL
    direction_bias: str             # UP | DOWN | FLAT
    confidence: float
    asymmetric_condor: dict | None  # suggested legs when in high-tremor regime
    notes: str


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def calculate_trembling_score(
    closes: Sequence[float],
    news_sentiment: float = 0.0,
    trader_sentiment: float = 0.0,
    expected_vol: float | None = None,
) -> float:
    """Compute Trembling Score from recent closes + optional external sentiments.

    High score means two opposing forces are nearly balanced (Gray Zone).
    """
    if len(closes) < 12:
        raise ValueError("at least 12 closes required for Lrzesh")

    # Realized volatility proxy (last 12 bars)
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    recent = rets[-12:]
    vol = sum(abs(r) for r in recent) / len(recent)
    if expected_vol is None:
        expected_vol = vol

    # Short vs medium momentum divergence
    short_mom = (closes[-1] - closes[-4]) / closes[-4]
    med_mom = (closes[-1] - closes[-10]) / closes[-10]
    mom_divergence = abs(short_mom - med_mom)

    # Sentiment divergence (if provided)
    sent_div = abs(news_sentiment - trader_sentiment)

    # Combine: higher divergence + higher vol → higher trembling
    raw = 0.45 * _clip(mom_divergence * 800) + 0.35 * _clip(vol * 1200) + 0.20 * _clip(sent_div)
    return _clip(raw)


def detect_regime(ts: float) -> str:
    if ts >= 0.78:
        return "GRAY_ZONE"
    if ts >= 0.55:
        return "TRANSITION"
    if ts < 0.35:
        return "TREND_STABLE"
    return "NEUTRAL"


def suggest_asymmetric_iron_condor(
    price: float,
    ts: float,
    base_width: float = 0.0075,
) -> dict | None:
    """Return suggested Iron Condor legs only in high-tremor regimes.

    Wider put wing to respect typical EUR/USD downside skew.
    Pure suggestion — never executes trades.
    """
    if ts < 0.75:
        return None

    put_width = base_width * 1.25
    call_width = base_width * 0.90

    short_put = round(price - put_width, 5)
    long_put = round(short_put - 0.0035, 5)
    short_call = round(price + call_width, 5)
    long_call = round(short_call + 0.0025, 5)

    return {
        "strategy": "ASYMMETRIC_IRON_CONDOR",
        "legs": {
            "short_put": short_put,
            "long_put": long_put,
            "short_call": short_call,
            "long_call": long_call,
        },
        "rationale": "High Trembling Score → sell range volatility with stronger downside protection",
        "max_profit_est_pips": 48,
        "max_loss_est_pips": 85,
        "note": "Research suggestion only. No live order is placed.",
    }


def run_lrzesh(
    closes: Sequence[float],
    news_sentiment: float = 0.0,
    trader_sentiment: float = 0.0,
) -> LrzeshResult:
    """Full Lrzesh evaluation. Pure function."""
    ts = calculate_trembling_score(closes, news_sentiment, trader_sentiment)
    regime = detect_regime(ts)

    # Direction bias from recent structure (still pure)
    short = (closes[-1] - closes[-4]) / closes[-4]
    if short > 0.00015:
        bias = "UP"
    elif short < -0.00015:
        bias = "DOWN"
    else:
        bias = "FLAT"

    confidence = min(0.92, 0.45 + abs(short) * 1600)
    if regime == "GRAY_ZONE":
        confidence = min(confidence, 0.62)  # deliberately lower in high tremor

    condor = suggest_asymmetric_iron_condor(closes[-1], ts)

    notes = (
        f"TS={ts:.3f} → {regime}. "
        "Gray Zone prioritizes range strategies over directional bets."
        if regime == "GRAY_ZONE"
        else f"TS={ts:.3f} → {regime}."
    )

    return LrzeshResult(
        trembling_score=round(ts, 4),
        regime=regime,
        direction_bias=bias,
        confidence=round(confidence, 4),
        asymmetric_condor=condor,
        notes=notes,
    )

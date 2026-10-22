"""Transparent EUR/USD 5M baseline forecast engine. Future candles are forbidden."""
from dataclasses import dataclass
from typing import Sequence, Optional

from engine.lrzesh import run_lrzesh, LrzeshResult


@dataclass(frozen=True)
class Forecast:
    direction: str
    confidence: float
    regime: str
    score: float
    # Optional Lrzesh enrichment (None when disabled)
    lrzesh: Optional[LrzeshResult] = None


def forecast(
    closes: Sequence[float],
    *,
    use_lrzesh: bool = True,
    news_sentiment: float = 0.0,
    trader_sentiment: float = 0.0,
) -> Forecast:
    """Baseline forecast with optional Lrzesh overlay.

    Temporal contract remains strict: only past closes are accepted.
    """
    if len(closes) < 12:
        raise ValueError("at least 12 closes are required")

    a = (closes[-1] - closes[-4]) / closes[-4]
    b = (closes[-1] - closes[-10]) / closes[-10]
    score = 0.6 * a + 0.4 * b
    direction = "UP" if score > 0.00015 else "DOWN" if score < -0.00015 else "FLAT"
    confidence = min(0.97, 0.5 + abs(score) * 1800)
    regime = (
        ("TREND_UP" if b > 0 else "TREND_DOWN")
        if abs(b) > 0.001
        else ("RANGE" if abs(b) < 0.00025 else "VOLATILE")
    )

    lrzesh_result: Optional[LrzeshResult] = None
    if use_lrzesh:
        try:
            lrzesh_result = run_lrzesh(
                closes,
                news_sentiment=news_sentiment,
                trader_sentiment=trader_sentiment,
            )
            # In Gray Zone we deliberately lower directional confidence
            if lrzesh_result.regime == "GRAY_ZONE":
                confidence = min(confidence, lrzesh_result.confidence)
                # Prefer FLAT when tremor is extreme and baseline score is weak
                if abs(score) < 0.00025:
                    direction = "FLAT"
                    regime = "GRAY_ZONE"
            else:
                # Light blend of Lrzesh regime label when not in Gray Zone
                if lrzesh_result.regime == "TREND_STABLE" and regime.startswith("TREND"):
                    pass  # keep original
                elif lrzesh_result.regime == "TRANSITION":
                    regime = "TRANSITION"
        except ValueError:
            # Not enough data for Lrzesh — keep pure baseline
            lrzesh_result = None

    return Forecast(
        direction=direction,
        confidence=confidence,
        regime=regime,
        score=score,
        lrzesh=lrzesh_result,
    )

"""Transparent EUR/USD 5M baseline forecast engine. No future data may be supplied."""
from dataclasses import dataclass
from typing import Sequence

@dataclass(frozen=True)
class Forecast:
    direction: str
    confidence: float
    regime: str
    score: float

def forecast(closes: Sequence[float]) -> Forecast:
    if len(closes) < 12:
        raise ValueError("at least 12 closes are required")
    a=(closes[-1]-closes[-4])/closes[-4]
    b=(closes[-1]-closes[-10])/closes[-10]
    score=.6*a+.4*b
    direction="UP" if score>.00015 else "DOWN" if score<-.00015 else "FLAT"
    confidence=min(.97,.5+abs(score)*1800)
    regime=("TREND_UP" if b>0 else "TREND_DOWN") if abs(b)>.001 else ("RANGE" if abs(b)<.00025 else "VOLATILE")
    return Forecast(direction,confidence,regime,score)

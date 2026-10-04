"""Consensus aggregation kept separate from market ground truth."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Consensus:
    bullish: float
    bearish: float
    neutral: float

def aggregate(signals: list[str]) -> Consensus:
    if not signals:
        return Consensus(0.0, 0.0, 1.0)
    n=len(signals)
    b=sum(s == "UP" for s in signals)/n
    d=sum(s == "DOWN" for s in signals)/n
    return Consensus(b,d,1.0-b-d)

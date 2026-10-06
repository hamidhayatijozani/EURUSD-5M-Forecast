"""Deterministic claim lifecycle with fail-closed statistical gates."""
from __future__ import annotations
from enum import Enum
from math import isfinite
from typing import Any, Dict

class ClaimState(Enum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_READY = "DATA_READY"
    STATISTICALLY_TESTABLE = "STATISTICALLY_TESTABLE"
    SUPPORTED = "SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    REFUTED = "REFUTED"
    KILLED = "KILLED"

class ClaimStateMachine:
    def __init__(self, claim_id: str, min_effective_n: int = 30):
        if min_effective_n < 1:
            raise ValueError("MIN_EFFECTIVE_N_MUST_BE_POSITIVE")
        self.claim_id = claim_id
        self.min_effective_n = min_effective_n
        self.state = ClaimState.INSUFFICIENT_DATA

    def evaluate(self, n_eff: float, test_result: Dict[str, Any]) -> ClaimState:
        if self.state is ClaimState.KILLED:
            return self.state
        if not isfinite(float(n_eff)) or n_eff < self.min_effective_n:
            self.state = ClaimState.INSUFFICIENT_DATA
            return self.state
        self.state = ClaimState.DATA_READY

        p = test_result.get("p_value")
        lower = test_result.get("ci_lower")
        if p is None or lower is None:
            self.state = ClaimState.INCONCLUSIVE
            return self.state
        try:
            p, lower = float(p), float(lower)
        except (TypeError, ValueError):
            self.state = ClaimState.INCONCLUSIVE
            return self.state
        if not (isfinite(p) and isfinite(lower)) or not 0 <= p <= 1:
            self.state = ClaimState.INCONCLUSIVE
            return self.state

        self.state = ClaimState.STATISTICALLY_TESTABLE
        significant = bool(test_result.get("bh_significant", False))
        if lower > 0 and significant:
            self.state = ClaimState.SUPPORTED
        elif lower < 0:
            self.state = ClaimState.REFUTED
        else:
            self.state = ClaimState.INCONCLUSIVE
        return self.state

    def kill(self) -> ClaimState:
        self.state = ClaimState.KILLED
        return self.state

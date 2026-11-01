"""Immutable ClaimLab observation contract with explicit live/historical provenance modes."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import math


def _dt(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _aware_dt(value, error_code):
    if not isinstance(value, str) or not value:
        raise ValueError(error_code)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(error_code)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Observation:
    schema_version: str
    prediction_id: str
    issued_at: str
    target_at: str
    resolved_at: str
    symbol: str
    horizon_seconds: int
    prediction: float
    actual: float
    baseline_prediction: float
    error_absolute: float
    baseline_error_absolute: float
    direction_hit: bool
    gross_return: float
    spread_cost: float
    slippage_cost: float
    commission_cost: float
    friction_adjusted_return: float
    feature_cutoff_at: str
    code_commit: str
    config_hash: str
    claim_registry_hash: str
    status: str = "VALID"
    provider: str | None = None
    source_candle_ts: str | None = None
    observed_at: str | None = None
    data_age_seconds: float | None = None
    freshness_limit_seconds: float | None = None
    freshness_status: str | None = None
    data_mode: str = ""

    def __post_init__(self):
        mode = self.data_mode
        if not mode:
            live_fields = (
                self.provider,
                self.source_candle_ts,
                self.observed_at,
                self.data_age_seconds,
                self.freshness_limit_seconds,
                self.freshness_status,
            )
            mode = (
                "LIVE"
                if all(value is not None and value != "" for value in live_fields)
                and self.freshness_status == "FRESH"
                else "UNVERIFIED"
            )
            object.__setattr__(self, "data_mode", mode)

        if mode not in {"LIVE", "HISTORICAL", "UNVERIFIED"}:
            raise ValueError("INVALID data mode")

        # Backward-compatible ledger reads must not turn absent provenance into
        # Yahoo/FRESH/age=0. Preserve the record identity but quarantine it.
        if mode == "UNVERIFIED":
            object.__setattr__(self, "status", "INVALID")
            object.__setattr__(self, "provider", "UNVERIFIED")
            object.__setattr__(self, "source_candle_ts", None)
            object.__setattr__(self, "observed_at", None)
            object.__setattr__(self, "data_age_seconds", None)
            object.__setattr__(self, "freshness_limit_seconds", None)
            object.__setattr__(self, "freshness_status", "UNVERIFIED")

        if self.status not in {"VALID", "INVALID"}:
            raise ValueError("INVALID observation status")
        if not self.prediction_id or not self.symbol:
            raise ValueError("missing immutable identity")

        f, i, t, r = map(
            _dt, (self.feature_cutoff_at, self.issued_at, self.target_at, self.resolved_at)
        )
        # Strict inequality prevents features stamped at issuance from being
        # treated as demonstrably available before the forecast was emitted.
        if not (f < i < t <= r):
            raise ValueError("INVALID temporal ordering")
        horizon = (t - i).total_seconds()
        if int(self.horizon_seconds) != int(horizon):
            raise ValueError("horizon_seconds mismatch")

        if mode == "LIVE":
            required = (
                self.provider,
                self.source_candle_ts,
                self.observed_at,
                self.data_age_seconds,
                self.freshness_limit_seconds,
                self.freshness_status,
            )
            if any(value is None or value == "" for value in required):
                raise ValueError("LIVE_PROVENANCE_REQUIRED")
            if not isinstance(self.provider, str) or not self.provider.strip():
                raise ValueError("LIVE_PROVIDER_INVALID")
            if self.freshness_status != "FRESH":
                raise ValueError("LIVE_FRESHNESS_STATUS_NOT_FRESH")
            source = _aware_dt(self.source_candle_ts, "LIVE_SOURCE_TIMESTAMP_INVALID")
            observed = _aware_dt(self.observed_at, "LIVE_OBSERVED_TIMESTAMP_INVALID")
            if source > observed:
                raise ValueError("source candle is from the future")
            if source > f:
                raise ValueError("source candle is after feature cutoff")
            age = float(self.data_age_seconds)
            limit = float(self.freshness_limit_seconds)
            if not math.isfinite(age) or not math.isfinite(limit) or age < 0 or limit <= 0:
                raise ValueError("invalid freshness values")
            if age > limit:
                raise ValueError("freshness limit exceeded")

        elif mode == "HISTORICAL":
            if not isinstance(self.provider, str) or not self.provider.strip():
                raise ValueError("HISTORICAL_PROVIDER_REQUIRED")
            source = _aware_dt(self.source_candle_ts, "HISTORICAL_SOURCE_TIMESTAMP_INVALID")
            if source > f:
                raise ValueError("historical source candle is after feature cutoff")
            if self.freshness_status != "NOT_APPLICABLE":
                raise ValueError("HISTORICAL_FRESHNESS_MUST_BE_NOT_APPLICABLE")
            if self.observed_at not in (None, ""):
                raise ValueError("HISTORICAL_OBSERVED_AT_NOT_APPLICABLE")
            if self.data_age_seconds is not None or self.freshness_limit_seconds is not None:
                raise ValueError("HISTORICAL_AGE_NOT_APPLICABLE")

        for name in (
            "prediction", "actual", "baseline_prediction", "error_absolute",
            "baseline_error_absolute", "gross_return", "spread_cost",
            "slippage_cost", "commission_cost", "friction_adjusted_return",
        ):
            if not math.isfinite(float(getattr(self, name))):
                raise ValueError(f"non-finite {name}")
        if min(self.spread_cost, self.slippage_cost, self.commission_cost) < 0:
            raise ValueError("negative transaction cost")

    def canonical(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def digest(self):
        return hashlib.sha256(self.canonical().encode()).hexdigest()

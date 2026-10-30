"""Leakage-safe walk-forward evaluation on EUR/USD 5-minute OHLCV data.

The evaluator issues a forecast only after a bar has closed, uses only returns
strictly before the issued timestamp, resolves against the next bar close, and
records complete provenance for replay.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Iterable, Sequence

from .arena import score
from .registry import assert_locked, load_registry, registry_hash
from .resolver import resolve
from .schema import Observation
from .verdict import verdict


DATASET_URL = (
    "https://raw.githubusercontent.com/getdata-finance/"
    "eurusd-5m-ohlcv-forex-historical-data/main/EURUSD_5m.csv"
)


def parse_csv(text: str) -> list[dict]:
    """Normalize candle timestamps, sort deterministically, and reject bad rows."""
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    required = {"datetime", "open", "high", "low", "close", "volume"}
    if not required.issubset(reader.fieldnames or set()):
        raise ValueError("HISTORICAL_DATA_SCHEMA_MISMATCH")

    for row in reader:
        try:
            ts = datetime.fromisoformat(row["datetime"].replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("HISTORICAL_DATA_INVALID_TIMESTAMP") from exc
        if ts.tzinfo is None:
            # The canonical source CSV is UTC-labelled by contract but omits
            # an explicit offset. Do not infer local machine timezone.
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone.utc)

        try:
            open_price = float(row["open"])
            high_price = float(row["high"])
            low_price = float(row["low"])
            close_price = float(row["close"])
            volume = float(row.get("volume") or 0.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("HISTORICAL_DATA_NON_NUMERIC_VALUE") from exc

        values = (open_price, high_price, low_price, close_price, volume)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("HISTORICAL_DATA_NONFINITE_VALUE")
        if min(open_price, high_price, low_price, close_price) <= 0:
            raise ValueError("HISTORICAL_DATA_NON_POSITIVE_PRICE")
        if low_price > min(open_price, close_price) or high_price < max(open_price, close_price) or low_price > high_price:
            raise ValueError("HISTORICAL_DATA_OHLC_INCONSISTENT")
        if volume < 0:
            raise ValueError("HISTORICAL_DATA_NEGATIVE_VOLUME")

        rows.append(
            {
                "timestamp": ts,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
        )

    if not rows:
        raise ValueError("HISTORICAL_DATA_EMPTY")
    # The immutable dataset hash covers the original source bytes. Evaluation
    # uses a deterministic UTC sort, while duplicate candle labels fail closed.
    rows.sort(key=lambda item: item["timestamp"])
    if any(rows[i]["timestamp"] <= rows[i - 1]["timestamp"] for i in range(1, len(rows))):
        raise ValueError("HISTORICAL_DATA_DUPLICATE_TIMESTAMP")
    return rows


def dataset_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _return(prev_close: float, close: float) -> float:
    if prev_close <= 0 or close <= 0:
        raise ValueError("NON_POSITIVE_CLOSE")
    return close / prev_close - 1.0


def walk_forward(
    rows: Sequence[dict],
    *,
    code_commit: str,
    config: dict | None = None,
    lookback: int = 12,
    friction: tuple[float, float, float] = (0.00002, 0.0, 0.0),
) -> tuple[list[Observation], dict]:
    """Generate one-step forecasts with strict information-set separation."""
    if lookback < 2:
        raise ValueError("LOOKBACK_TOO_SMALL")
    if len(rows) <= lookback + 1:
        raise ValueError("INSUFFICIENT_BARS")

    cfg = config or {
        "model": "rolling_mean_return",
        "lookback_bars": lookback,
        "target_horizon_seconds": 300,
        "baseline": "zero_return",
        "friction": list(friction),
    }
    config_hash = hashlib.sha256(
        json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    reg_hash = assert_locked()

    returns = [_return(rows[i - 1]["close"], rows[i]["close"]) for i in range(1, len(rows))]
    observations: list[Observation] = []

    # Timestamps in the source identify candle opens. A forecast is issued at
    # the close of bar i, and resolves at the close of the next 5-minute bar.
    # Skip gaps rather than pretending the next available candle is a 5m target.
    for i in range(lookback, len(rows) - 1):
        window_start = i - lookback
        contiguous = all(
            rows[j]["timestamp"] - rows[j - 1]["timestamp"] == timedelta(minutes=5)
            for j in range(window_start + 1, i + 2)
        )
        if not contiguous:
            continue
        issued = rows[i]["timestamp"] + timedelta(minutes=5, seconds=1)
        target = rows[i + 1]["timestamp"] + timedelta(minutes=5, seconds=1)
        # returns[j - 1] ends at bar j; these features end at the issued bar.
        feature_returns = returns[i - lookback : i]
        prediction = mean(feature_returns)
        baseline = 0.0
        actual = returns[i]
        pred = {
            "schema_version": "claimlab.observation.v1",
            "prediction_id": f"eurusd-m5-{i:08d}",
            "issued_at": _iso(issued),
            "target_at": _iso(target),
            "feature_cutoff_at": _iso(issued - timedelta(seconds=1)),
            "symbol": "EURUSD",
            "horizon_seconds": int((target - issued).total_seconds()),
            "prediction": prediction,
            "code_commit": code_commit,
            "config_hash": config_hash,
            "claim_registry_hash": reg_hash,
        }
        resolved = resolve(
            pred,
            actual=actual,
            baseline_prediction=baseline,
            resolved_at=_iso(target),
            friction=friction,
        )
        observations.append(Observation(**resolved))

    return observations, {
        "model": cfg["model"],
        "lookback_bars": lookback,
        "target_horizon_seconds": 300,
        "baseline": cfg["baseline"],
        "friction": list(friction),
        "config_hash": config_hash,
        "claim_registry_hash": reg_hash,
    }


def regime_robustness(
    market_rows: Sequence[dict],
    observation_rows: Sequence[dict],
    *,
    lookback: int = 12,
    bootstrap_resamples: int = 500,
) -> dict:
    """Past-only volatility regimes for sequential out-of-sample observations.

    Thresholds are estimated from previously observed rolling volatilities only.
    The current observation's volatility is added to history after classification.
    """
    from .arena import score

    if lookback < 2:
        raise ValueError("LOOKBACK_TOO_SMALL")
    returns = [
        _return(market_rows[i - 1]["close"], market_rows[i]["close"])
        for i in range(1, len(market_rows))
    ]
    history: list[float] = []
    thresholds = None
    grouped = {"LOW": [], "MEDIUM": [], "HIGH": []}
    warmup = 0

    index_by_issue = {
        _iso(row["timestamp"] + timedelta(minutes=5, seconds=1)): i
        for i, row in enumerate(market_rows)
    }
    for row in observation_rows:
        i = index_by_issue.get(row.get("issued_at"))
        if i is None or i < lookback or i >= len(market_rows) - 1:
            continue
        feature_returns = returns[i - lookback : i]
        volatility = pstdev(feature_returns) if len(feature_returns) > 1 else 0.0

        # Re-estimate on a bounded, past-only sample every 25 observations.
        if len(history) >= 50 and len(history) % 25 == 0:
            sample = sorted(history[-500:])
            thresholds = (
                sample[int(0.33 * (len(sample) - 1))],
                sample[int(0.67 * (len(sample) - 1))],
            )

        if thresholds is None:
            regime = "WARMUP"
            warmup += 1
        elif volatility <= thresholds[0]:
            regime = "LOW"
        elif volatility >= thresholds[1]:
            regime = "HIGH"
        else:
            regime = "MEDIUM"

        history.append(volatility)
        if regime != "WARMUP" and row.get("status") == "VALID":
            grouped[regime].append(row)

    metrics = {}
    for regime, group in grouped.items():
        if not group:
            metrics[regime] = {"n": 0, "status": "INSUFFICIENT_DATA"}
        else:
            metrics[regime] = score(
                group, horizon=5, bootstrap_resamples=bootstrap_resamples
            )
    return {
        "method": "past-only expanding warmup + rolling 500-volatility quantiles",
        "threshold_lookback_max": 500,
        "threshold_refresh_every": 25,
        "warmup_observations_excluded": warmup,
        "metrics": metrics,
        "scientific_boundary": (
            "Historical sequential out-of-sample regimes; not evidence of live "
            "predictive superiority or profitability."
        ),
    }



DEFAULT_COST_SCENARIOS_PIPS = (
    (0.2, 0.0),
    (0.2, 0.1),
    (0.5, 0.1),
    (1.0, 0.25),
)


def cost_sensitivity(
    observation_rows: Sequence[dict],
    *,
    scenarios: Sequence[tuple[float, float]] = DEFAULT_COST_SCENARIOS_PIPS,
    bootstrap_resamples: int = 2000,
) -> dict:
    """Reprice frozen forecasts with separately declared spread and slippage.

    Each tuple is (round-trip spread pips, round-trip slippage pips). The
    scenarios are sensitivities, not observed broker quotes. Commission is
    explicitly left unpriced until a broker/venue schedule is supplied.
    """
    results = {}
    for spread_pips, slippage_pips in scenarios:
        spread_pips = float(spread_pips)
        slippage_pips = float(slippage_pips)
        if not math.isfinite(spread_pips) or not math.isfinite(slippage_pips):
            raise ValueError("INVALID_COST_SCENARIO")
        if spread_pips < 0 or slippage_pips < 0:
            raise ValueError("NEGATIVE_COST_SCENARIO")

        spread_cost = spread_pips * 0.0001
        slippage_cost = slippage_pips * 0.0001
        commission_cost = 0.0
        total_cost = spread_cost + slippage_cost + commission_cost
        scenario_rows = []
        for source in observation_rows:
            row = dict(source)
            prediction = float(row["prediction"])
            actual = float(row["actual"])
            direction = 1 if prediction > 0 else -1 if prediction < 0 else 0
            gross = direction * actual
            row["gross_return"] = gross
            row["spread_cost"] = spread_cost
            row["slippage_cost"] = slippage_cost
            row["commission_cost"] = commission_cost
            row["friction_adjusted_return"] = gross - total_cost
            row["direction_hit"] = (
                (direction == 1 and actual > total_cost)
                or (direction == -1 and actual < -total_cost)
            )
            scenario_rows.append(row)

        metrics = score(
            scenario_rows,
            horizon=5,
            bootstrap_resamples=bootstrap_resamples,
            alpha=0.05,
        )
        key = f"spread_{spread_pips:.1f}pip_slippage_{slippage_pips:.2f}pip"
        results[key] = {
            "spread_pips": spread_pips,
            "slippage_pips": slippage_pips,
            "spread_cost": spread_cost,
            "slippage_cost": slippage_cost,
            "commission_cost": commission_cost,
            "total_round_trip_cost": total_cost,
            "cost_source": "declared_scenario_not_broker_quote",
            "metrics": metrics,
        }
    return {
        "method": "reprice frozen forecast direction and actual return by cost component",
        "pip_size": 0.0001,
        "scenario_units": "round-trip pips",
        "commission_boundary": (
            "Commission is not priced: no broker/venue commission schedule was supplied."
        ),
        "scenarios": results,
        "scientific_boundary": (
            "Sensitivity analysis only; not executable broker-cost evidence."
        ),
    }


def build_capsule(
    observations: Sequence[Observation],
    *,
    dataset_text: str,
    dataset_ref: str,
    code_commit: str,
    config: dict,
    source_url: str = DATASET_URL,
) -> dict:
    rows = [json.loads(o.canonical()) for o in observations]
    stats = score(
        rows,
        horizon=5,
        bootstrap_resamples=2000,
        alpha=0.05,
    )
    stats["regime_robustness"] = regime_robustness(
        parse_csv(dataset_text),
        rows,
        lookback=int(config.get("lookback_bars", 12)),
        bootstrap_resamples=500,
    )
    stats["cost_sensitivity"] = cost_sensitivity(
        rows,
        scenarios=DEFAULT_COST_SCENARIOS_PIPS,
        bootstrap_resamples=2000,
    )
    registry = load_registry()
    duplicate_count = len(rows) - len({r["prediction_id"] for r in rows})
    temporal_valid = 0
    for r in rows:
        try:
            from .resolver import validate_window
            validate_window(
                r["issued_at"], r["target_at"], r["resolved_at"], r["feature_cutoff_at"]
            )
            temporal_valid += 1
        except ValueError:
            pass
    stats["temporal_validity_rate"] = (
        temporal_valid / len(rows) if rows else 0.0
    )
    stats["duplicate_prediction_rate"] = (
        duplicate_count / len(rows) if rows else 0.0
    )
    # Ledger integrity is verified by the caller after materializing the ledger.
    stats["ledger_integrity"] = None

    return {
        "capsule_schema": "claimlab.evidence_capsule.v1",
        "status": "COMPUTED_RESEARCH_EVIDENCE",
        "claim_registry": {
            "registry_id": registry["registry_id"],
            "registry_hash": registry_hash(),
            "status": registry["status"],
        },
        "data": {
            "source_url": source_url,
            "source_ref": dataset_ref,
            "source_type": "historical_real",
            "synthetic_demo": False,
            "dataset_sha256": dataset_sha256(dataset_text),
            "row_count": len(parse_csv(dataset_text)),
            "first_timestamp": _iso(parse_csv(dataset_text)[0]["timestamp"]),
            "last_timestamp": _iso(parse_csv(dataset_text)[-1]["timestamp"]),
            "timestamp_contract": "datetime identifies candle open; timezone-aware values normalize to UTC; naive source timestamps are interpreted as UTC",
            "source_order_normalization": "stable ascending sort by UTC candle-open timestamp; duplicate timestamps rejected",
            "row_validation": "unique increasing timestamps; finite positive OHLC; consistent high/low; nonnegative volume",
        },
        "execution": {
            "code_commit": code_commit,
            "config": config,
            "observation_count": len(rows),
            "valid_observation_count": len(rows),
            "invalid_observation_count": 0,
        },
        "statistics": stats,
        "verdict": verdict(stats),
        "scientific_boundary": {
            "predictive_edge_established": False,
            "profitability_established": False,
            "live_feed_verified": False,
            "interpretation": "Historical research result only; no live-performance claim.",
        },
    }

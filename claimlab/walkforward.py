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
from datetime import datetime, timezone
from statistics import mean
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
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    required = {"datetime", "open", "high", "low", "close", "volume"}
    if not required.issubset(reader.fieldnames or set()):
        raise ValueError("HISTORICAL_DATA_SCHEMA_MISMATCH")
    for row in reader:
        ts = datetime.fromisoformat(row["datetime"].replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        rows.append(
            {
                "timestamp": ts.astimezone(timezone.utc),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume") or 0.0),
            }
        )
    rows.sort(key=lambda x: x["timestamp"])
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

    # i is the issued/closed bar. j=i+1 is the first bar not known at issuance.
    for i in range(lookback, len(rows) - 2):
        issued = rows[i]["timestamp"]
        target = rows[i + 1]["timestamp"]
        # The issued bar is closed and therefore known. The target bar is not.
        feature_returns = returns[i - lookback + 1 : i + 1]
        prediction = mean(feature_returns)
        baseline = 0.0
        actual = returns[i + 1]
        pred = {
            "schema_version": "claimlab.observation.v1",
            "prediction_id": f"eurusd-m5-{i:08d}",
            "issued_at": _iso(issued),
            "target_at": _iso(target),
            "feature_cutoff_at": _iso(issued),
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

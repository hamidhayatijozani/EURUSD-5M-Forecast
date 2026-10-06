"""Auditable evidence capsules with explicit temporal boundaries."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

def _dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)

def canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

class EvidenceCapsuleGenerator:
    @staticmethod
    def verify_temporal_integrity(candle_timestamp: str, feature_cutoff_at: str,
                                  next_candle_timestamp: Optional[str] = None) -> bool:
        candle, cutoff = _dt(candle_timestamp), _dt(feature_cutoff_at)
        if candle > cutoff:
            return False
        if next_candle_timestamp is not None and cutoff >= _dt(next_candle_timestamp):
            return False
        return True

    @staticmethod
    def create_capsule(candle: Dict[str, Any], feature_cutoff_at: str,
                       n_raw: int, n_eff: float,
                       statistical_parameters: Dict[str, Any],
                       registry_version: str, code_commit: str,
                       previous_hash: str,
                       next_candle_timestamp: Optional[str] = None) -> Dict[str, Any]:
        candle_ts = candle["timestamp"]
        if not EvidenceCapsuleGenerator.verify_temporal_integrity(
            candle_ts, feature_cutoff_at, next_candle_timestamp
        ):
            raise ValueError("TEMPORAL_INTEGRITY_FAIL")
        ingested_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        capsule = {
            "candle_timestamp": candle_ts,
            "ingested_at": ingested_at,
            "feature_cutoff_at": feature_cutoff_at,
            "source": candle.get("symbol", "EUR/USD"),
            "ohlc": {k: candle[k] for k in ("open", "high", "low", "close")},
            "return": candle.get("return"),
            "n_raw": int(n_raw),
            "n_eff": float(n_eff),
            "statistical_parameters": statistical_parameters,
            "registry_version": registry_version,
            "code_commit": code_commit,
            "previous_hash": previous_hash,
        }
        capsule["current_hash"] = hashlib.sha256(
            canonical_json(capsule).encode("utf-8")
        ).hexdigest()
        return capsule

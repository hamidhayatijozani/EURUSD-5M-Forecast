"""Immutable, timestamp-aligned evidence for each live forecast decision."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence


def _parse_time(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("EVIDENCE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _iso(value):
    return _parse_time(value).isoformat()


def build_decision_evidence(
    *,
    candle_times: Sequence,
    series: Mapping[str, Sequence[float]],
    ohlc: Mapping[str, Sequence[float]],
    source_candle_ts,
    issued_at,
    config_hash: str,
    model_components: Mapping,
    external_context: Mapping,
):
    """Capture only inputs available by the forecast cutoff and hash the snapshot.

    Candle timestamps label candle opens. The latest included candle must not
    be later than source_candle_ts; issued_at must be at/after that candle close.
    """
    if not candle_times:
        raise ValueError("EVIDENCE_REQUIRES_CANDLES")
    times = [_parse_time(value) for value in candle_times]
    if times != sorted(times) or len(set(times)) != len(times):
        raise ValueError("EVIDENCE_CANDLE_TIMES_MUST_BE_UNIQUE_AND_SORTED")
    source_open = _parse_time(source_candle_ts)
    issue_time = _parse_time(issued_at)
    if times[-1] != source_open:
        raise ValueError("EVIDENCE_SOURCE_CANDLE_MUST_MATCH_LAST_CANDLE")
    if any(value > source_open for value in times):
        raise ValueError("EVIDENCE_FUTURE_CANDLE_DETECTED")
    if issue_time < source_open + timedelta(minutes=1):
        raise ValueError("EVIDENCE_ISSUED_BEFORE_SOURCE_CANDLE_CLOSE")
    if not config_hash:
        raise ValueError("EVIDENCE_CONFIG_HASH_REQUIRED")

    expected = len(times)
    inputs = {}
    for symbol, values in sorted(series.items()):
        if len(values) != expected:
            raise ValueError(f"EVIDENCE_SERIES_LENGTH_MISMATCH:{symbol}")
        inputs[symbol] = [
            {"candle_open_at": timestamp.isoformat(), "close": float(value)}
            for timestamp, value in zip(times, values)
        ]

    ohlc_rows = []
    for field, values in sorted(ohlc.items()):
        if len(values) != expected:
            raise ValueError(f"EVIDENCE_OHLC_LENGTH_MISMATCH:{field}")
        normalized = []
        for value in values:
            if isinstance(value, (list, tuple)):
                normalized.append([float(component) for component in value])
            else:
                normalized.append(float(value))
        ohlc_rows.append({
            "symbol_or_field": field,
            "values": normalized,
        })

    payload = {
        "schema": "claimlab.forecast_decision_evidence.v1",
        "source_candle_ts": source_open.isoformat(),
        "feature_cutoff_at": issue_time.isoformat(),
        "issued_at": issue_time.isoformat(),
        "candle_open_times": [value.isoformat() for value in times],
        "series_close_inputs": inputs,
        "eurusd_ohlc_inputs": ohlc_rows,
        "config_hash": str(config_hash),
        "model_components": dict(model_components),
        "external_context": dict(external_context),
        "future_input_excluded": True,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    payload["snapshot_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def verify_decision_evidence(evidence):
    """Verify the content hash before evidence is merged or analyzed."""
    if not isinstance(evidence, dict):
        return False
    supplied = evidence.get("snapshot_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64:
        return False
    payload = {key: value for key, value in evidence.items() if key != "snapshot_sha256"}
    try:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return False
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest() == supplied

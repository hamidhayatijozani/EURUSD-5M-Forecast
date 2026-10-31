"""Optional Coinversa Hyperliquid market-risk context.

This adapter is supplemental context only. It never emits or normalizes EUR/USD
OHLC candles and must not affect the primary market-data provider failover.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASE_URL = "https://api.coinversa.ai/api/public/v1"
USER_AGENT = "EURUSD-5M-Forecast/1.0"
_TIMEOUT_SECONDS = 5
_BLOCKED_KEY_PARTS = ("api_key", "apikey", "token", "secret", "authorization", "password")


def _fetch_json(url: str, api_key: str, timeout: int = _TIMEOUT_SECONDS):
    request = Request(
        url,
        headers={
            "X-API-Key": api_key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _safe_payload(value, depth: int = 0):
    """Bound and redact provider JSON before attaching it to forecast context."""
    if depth > 4:
        return None
    if isinstance(value, dict):
        safe = {}
        for key, item in list(value.items())[:50]:
            name = str(key)
            if any(part in name.lower() for part in _BLOCKED_KEY_PARTS):
                continue
            if isinstance(item, (dict, list, str, int, float, bool)) or item is None:
                safe[name[:100]] = _safe_payload(item, depth + 1)
        return safe
    if isinstance(value, list):
        return [_safe_payload(item, depth + 1) for item in value[:50]]
    if isinstance(value, str):
        return value[:256]
    if isinstance(value, float):
        return value if item_is_finite(value) else None
    if isinstance(value, (int, bool)) or value is None:
        return value
    return None


def item_is_finite(value: float) -> bool:
    # Avoid non-standard NaN/Infinity values entering serialized context.
    return value == value and value not in (float("inf"), float("-inf"))


def fetch_coinversa_context(api_key: str | None = None, now=None) -> dict:
    """Fetch pulse statistics and aggregate risk overview without breaking callers."""
    now = now or datetime.now(timezone.utc)
    key = (api_key if api_key is not None else os.getenv("COINVERSAA_API_KEY", "")).strip()
    base = {
        "source": "coinversa_hyperliquid",
        "retrieved_at": now.astimezone(timezone.utc).isoformat(),
        "directional_signal": False,
        "eurusd_ohlc": False,
        "pulse_status": "UNAVAILABLE:NO_API_KEY",
        "risk_status": "UNAVAILABLE:NO_API_KEY",
        "pulse": None,
        "risk": None,
    }
    if not key:
        base["status"] = "UNAVAILABLE:NO_API_KEY"
        return base

    endpoints = (
        ("pulse", "/pulse/stats"),
        ("risk", "/live/risk/overview"),
    )
    for name, path in endpoints:
        try:
            payload = _fetch_json(BASE_URL + path, key)
            if not isinstance(payload, (dict, list)):
                raise ValueError("unexpected response shape")
            base[name] = _safe_payload(payload)
            base[name + "_status"] = "OK"
        except Exception as exc:
            # Never log exception text: request diagnostics may contain secrets.
            base[name + "_status"] = "UNAVAILABLE:" + type(exc).__name__

    base["status"] = "OK" if any(base[name + "_status"] == "OK" for name, _ in endpoints) else "UNAVAILABLE"
    return base

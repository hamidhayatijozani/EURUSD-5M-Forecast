"""Optional Coinversa on-chain context; never an EUR/USD candle provider.

This adapter is intentionally read-only and isolated from engine.market_providers.
It returns an opaque context snapshot until the upstream response schema is
validated. It does not manufacture directional scores or alter forecast inputs.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen

COINVERSA_PULSE_URL = "https://api.coinversa.ai/api/public/v1/pulse/stats"
_MAX_RESPONSE_BYTES = 1_000_000


def _enabled() -> bool:
    return os.environ.get("COINVERSA_CONTEXT_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def fetch_coinversa_context(*, timeout: float = 5.0) -> dict:
    """Return optional Coinversa context without ever failing the caller.

    Requires COINVERSA_CONTEXT_ENABLED=true and COINVERSAA_API_KEY. No trading
    endpoints are called. Failures return status metadata and never expose the
    URL, response body, headers, or secret.
    """
    if not _enabled():
        return {"source": "coinversa", "status": "DISABLED", "data": None}
    key = os.environ.get("COINVERSAA_API_KEY", "").strip()
    if not key:
        return {"source": "coinversa", "status": "UNAVAILABLE:NO_API_KEY", "data": None}

    request = Request(
        COINVERSA_PULSE_URL,
        headers={
            "X-API-Key": key,
            "Accept": "application/json",
            "User-Agent": "EURUSD-5M-Forecast/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            return {"source": "coinversa", "status": "UNAVAILABLE:RESPONSE_TOO_LARGE", "data": None}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return {"source": "coinversa", "status": "UNAVAILABLE:INVALID_SCHEMA", "data": None}
        # Keep the upstream snapshot separate and opaque. Do not map its values
        # to EUR/USD prices or directional scores without a reviewed schema.
        return {
            "source": "coinversa",
            "status": "OK",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "data": payload,
        }
    except Exception as exc:
        # Never log or return exception text: it may contain request details.
        return {
            "source": "coinversa",
            "status": "UNAVAILABLE:" + type(exc).__name__,
            "data": None,
        }

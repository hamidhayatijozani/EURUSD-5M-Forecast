"""Failover market-data adapters normalized to Yahoo chart response shape.

Provider order is configured with LIVE_FEED_PROVIDERS. Secrets are read only
from the process environment and are never included in diagnostics.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

YAHOO_SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "DXY": "DX-Y.NYB",
}
OANDA_SYMBOLS = {"EURUSD": "EUR_USD", "GBPUSD": "GBP_USD", "USDJPY": "USD_JPY"}
TWELVEDATA_SYMBOLS = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    # DXY is not assumed available on every Twelve Data plan.
    "DXY": "DXY",
}
LAST_PROVIDER_BY_SYMBOL: dict[str, str] = {}


def _chart_result(rows):
    rows = sorted(rows, key=lambda row: row[0])
    if not rows:
        raise ValueError("provider returned no complete candles")
    return {
        "timestamp": [int(row[0]) for row in rows],
        "indicators": {"quote": [{
            "open": [row[1] for row in rows],
            "high": [row[2] for row in rows],
            "low": [row[3] for row in rows],
            "close": [row[4] for row in rows],
            "volume": [row[5] for row in rows],
        }]},
    }


def _parse_oanda(payload):
    rows = []
    for candle in payload.get("candles", []):
        if not candle.get("complete"):
            continue
        mid = candle.get("mid") or {}
        if not all(mid.get(k) is not None for k in ("o", "h", "l", "c")):
            continue
        stamp = datetime.fromisoformat(candle["time"].replace("Z", "+00:00"))
        rows.append((stamp.timestamp(), float(mid["o"]), float(mid["h"]),
                     float(mid["l"]), float(mid["c"]), float(candle.get("volume", 0))))
    return _chart_result(rows)


def _parse_twelvedata(payload):
    if payload.get("status") == "error":
        raise ValueError("Twelve Data returned provider error")
    rows = []
    for candle in payload.get("values", []):
        stamp = datetime.strptime(candle["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        rows.append((stamp.timestamp(), float(candle["open"]), float(candle["high"]),
                     float(candle["low"]), float(candle["close"]), float(candle.get("volume") or 0)))
    return _chart_result(rows)


def _get_json(url, headers=None, timeout=8):
    request = Request(url, headers=headers or {"User-Agent": "EURUSD-5M-Forecast/4.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _fetch_yahoo(symbol, interval):
    ticker = YAHOO_SYMBOLS.get(symbol)
    if not ticker:
        raise ValueError("unsupported Yahoo symbol")
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker + "?" + urlencode({
        "interval": interval, "range": "1d"
    })
    payload = _get_json(url)
    result = payload["chart"]["result"][0]
    # Filter out incomplete OHLC rows before passing data downstream.
    quote = result["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(result["timestamp"]):
        vals = [quote.get(k, [None] * len(result["timestamp"]))[i] for k in ("open", "high", "low", "close")]
        if all(value is not None for value in vals):
            rows.append((ts, *map(float, vals), float((quote.get("volume") or [0] * len(result["timestamp"]))[i] or 0)))
    return _chart_result(rows)


def _fetch_oanda(symbol, interval):
    token = os.environ.get("OANDA_API_TOKEN", "").strip()
    instrument = OANDA_SYMBOLS.get(symbol)
    if not token or not instrument:
        raise RuntimeError("OANDA_NOT_CONFIGURED_FOR_SYMBOL")
    granularity = {"1min": "M1", "5min": "M5"}.get(interval)
    if not granularity:
        raise ValueError("unsupported OANDA interval")
    base = os.environ.get("OANDA_API_BASE", "").strip()
    if not base:
        environment = os.environ.get("OANDA_ENVIRONMENT", "practice").lower()
        base = "https://api-fxtrade.oanda.com" if environment == "live" else "https://api-fxpractice.oanda.com"
    url = base.rstrip("/") + "/v3/instruments/" + instrument + "/candles?" + urlencode({
        "granularity": granularity, "count": 120 if granularity == "M1" else 288, "price": "M"
    })
    payload = _get_json(url, {"Authorization": "Bearer " + token, "Accept-Datetime-Format": "RFC3339"})
    return _parse_oanda(payload)


def _fetch_twelvedata(symbol, interval):
    key = os.environ.get("TWELVEDATA_API_KEY", "").strip()
    provider_symbol = TWELVEDATA_SYMBOLS.get(symbol)
    if not key or not provider_symbol:
        raise RuntimeError("TWELVEDATA_NOT_CONFIGURED_FOR_SYMBOL")
    url = "https://api.twelvedata.com/time_series?" + urlencode({
        "symbol": provider_symbol, "interval": interval, "outputsize": 120 if interval == "1min" else 288,
        "timezone": "UTC", "include_ohlc": "true",
        "apikey": key, "format": "JSON"
    })
    return _parse_twelvedata(_get_json(url))


_SAFE_FAILURE_MESSAGES = {
    "OANDA_NOT_CONFIGURED_FOR_SYMBOL": "NOT_CONFIGURED",
    "TWELVEDATA_NOT_CONFIGURED_FOR_SYMBOL": "NOT_CONFIGURED",
    "Twelve Data returned provider error": "PROVIDER_REJECTED",
    "provider returned no complete candles": "NO_COMPLETE_CANDLES",
    "invalid or unordered candle timestamps": "INVALID_CANDLE_TIMESTAMPS",
    "missing one-minute OHLC payload": "MISSING_OHLC_PAYLOAD",
    "incomplete one-minute OHLC arrays": "INCOMPLETE_OHLC_ARRAYS",
    "no closed one-minute OHLC candles": "NO_CLOSED_CANDLES",
    "stale one-minute OHLC candles": "STALE_CANDLES",
    "insufficient contiguous closed one-minute OHLC candles": "INSUFFICIENT_CONTIGUOUS_CANDLES",
    "unsupported OANDA interval": "UNSUPPORTED_INTERVAL",
    "unsupported Yahoo symbol": "UNSUPPORTED_SYMBOL",
}


def _safe_failure_code(exc: Exception) -> str:
    """Return a bounded diagnostic code; never expose provider URLs or payload text."""
    if isinstance(exc, HTTPError):
        return f"HTTP_{int(exc.code)}"
    if isinstance(exc, URLError):
        return "NETWORK_ERROR"
    if isinstance(exc, TimeoutError):
        return "TIMEOUT"
    known = _SAFE_FAILURE_MESSAGES.get(str(exc))
    if known:
        return known
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return "UNCLASSIFIED_VALUE_ERROR"
    return type(exc).__name__.upper()


def fetch_chart_result(
    symbol: str,
    interval: str,
    yahoo_symbol: str | None = None,
    *,
    result_validator: Callable[[dict], None] | None = None,
):
    """Return normalized candle data from the first configured, healthy provider."""
    interval = "1min" if interval in ("1m", "1min") else "5min"
    configured = os.environ.get("LIVE_FEED_PROVIDERS", "").strip()
    if configured:
        providers = [item.strip().lower() for item in configured.split(",") if item.strip()]
    else:
        providers = []
        if os.environ.get("OANDA_API_TOKEN", "").strip():
            providers.append("oanda")
        if os.environ.get("TWELVEDATA_API_KEY", "").strip():
            providers.append("twelvedata")
        providers.append("yahoo")
    fetchers = {
        "oanda": lambda: _fetch_oanda(symbol, interval),
        "twelvedata": lambda: _fetch_twelvedata(symbol, interval),
        "yahoo": lambda: _fetch_yahoo(symbol, "1m" if interval == "1min" else "5m"),
    }
    failures = []
    for provider in providers:
        fetcher = fetchers.get(provider)
        if fetcher is None:
            failures.append(provider + ":unsupported")
            continue
        try:
            result = fetcher()
            # Basic integrity check. Freshness and closed-candle checks remain
            # enforced by engine.live_feed and the forecast loop.
            timestamps = result.get("timestamp", [])
            if len(timestamps) < 1 or timestamps != sorted(timestamps):
                raise ValueError("invalid or unordered candle timestamps")
            # Live consumers can reject stale/incomplete data here so a
            # reachable-but-unusable provider does not block provider failover.
            if result_validator is not None:
                result_validator(result)
            LAST_PROVIDER_BY_SYMBOL[symbol] = provider
            if failures:
                print("LIVE_FEED_PROVIDER_FAILOVER:" + json.dumps({
                    "symbol": symbol, "selected": provider, "prior_failures": failures
                }, sort_keys=True))
            print("LIVE_FEED_PROVIDER_SELECTED:" + json.dumps({
                "symbol": symbol, "provider": provider, "interval": interval,
                "candles": len(timestamps)
            }, sort_keys=True))
            return result
        except Exception as exc:
            # Deliberately do not log exception text: provider URLs/errors can
            # echo query parameters, including a Twelve Data API key.
            failures.append(provider + ":" + _safe_failure_code(exc))
    raise RuntimeError("ALL_MARKET_PROVIDERS_FAILED:" + ",".join(failures))

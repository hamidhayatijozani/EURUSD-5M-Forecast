"""Twelve Data adapter for real EUR/USD five-minute research candles.

This is a market-data ingestion adapter only. It does not forecast or trade.
The provider key is read from TWELVE_DATA_API_KEY and is never logged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from typing import Any

import requests


class TwelveDataError(RuntimeError):
    """Sanitized provider, configuration, or response error."""


class TwelveDataEURUSD5mClient:
    """Fetch the most recent completed EUR/USD 5-minute candle from Twelve Data."""

    ENDPOINT = "https://api.twelvedata.com/time_series"
    INTERVAL = timedelta(minutes=5)

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 12.0,
        session: Any = None,
        max_age_seconds: int = 900,
    ) -> None:
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY")
        if not self.api_key:
            raise TwelveDataError("TWELVE_DATA_API_KEY is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds must be non-negative")
        self.timeout = timeout
        self.session = session or requests
        self.max_age_seconds = max_age_seconds

    @staticmethod
    def _timestamp(value: str) -> datetime:
        # Twelve Data returns naive timestamps when timezone=UTC is requested.
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _number(value: Any, field: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise TwelveDataError(f"Invalid candle field: {field}") from exc
        if not (number > 0 and number < float("inf")):
            raise TwelveDataError(f"Invalid candle field: {field}")
        return number

    def fetch_latest_eurusd_candle(self, now: datetime | None = None) -> dict[str, Any]:
        """Return a validated, completed candle plus provenance/freshness metadata."""
        received_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        response = self.session.get(
            self.ENDPOINT,
            params={
                "symbol": "EUR/USD",
                "interval": "5min",
                "outputsize": 5,
                "timezone": "UTC",
                "apikey": self.api_key,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TwelveDataError("Unexpected provider response")
        if payload.get("status") == "error" or "code" in payload and "message" in payload:
            # Do not echo provider messages; they can contain request details.
            raise TwelveDataError("Twelve Data rejected the market-data request")
        values = payload.get("values")
        if not isinstance(values, list) or not values:
            raise TwelveDataError("No EUR/USD candle values returned")
        candles = []
        for row in values:
            if not isinstance(row, dict) or "datetime" not in row:
                continue
            start = self._timestamp(row["datetime"])
            closed_at = start + self.INTERVAL
            if closed_at <= received_at:
                candles.append((start, closed_at, row))
        if not candles:
            raise TwelveDataError("No completed EUR/USD 5-minute candle returned")
        start, closed_at, row = max(candles, key=lambda item: item[0])
        open_ = self._number(row.get("open"), "open")
        high = self._number(row.get("high"), "high")
        low = self._number(row.get("low"), "low")
        close = self._number(row.get("close"), "close")
        if high < low or not (low <= open_ <= high and low <= close <= high):
            raise TwelveDataError("Invalid EUR/USD OHLC candle")
        age_seconds = max(0.0, (received_at - closed_at).total_seconds())
        raw_hash = sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {
            "symbol": "EURUSD",
            "provider": "twelve_data",
            "interval": "5min",
            "timestamp": start.isoformat(),
            "candle_closed_at": closed_at.isoformat(),
            "observed_at": received_at.isoformat(),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 0.0,
            "data_age_seconds": round(age_seconds, 3),
            "freshness_limit_seconds": self.max_age_seconds,
            "freshness_status": "FRESH" if age_seconds <= self.max_age_seconds else "STALE",
            "raw_payload_hash": raw_hash,
        }
